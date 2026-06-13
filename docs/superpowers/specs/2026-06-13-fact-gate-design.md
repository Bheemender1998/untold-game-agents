# fact_gate.py — design spec

**Status:** Approved for planning (2026-06-13)
**Supersedes the internals of:** `engine/pipeline/factcheck.py` (kept as a thin shim)
**Related:** ADR-0003 (free web search), ADR-0005 (mandatory fact-verification gate)

## Context — what's wrong with the current gate

The current `factcheck.py` runs one verify call **per claim** (≤25), each fed
`web_search(claim)` (DuckDuckGo) **plus** `wikipedia.lookup(claim)`. Two failures
make it noisy and expensive on well-documented topics:

1. **Wikipedia lands on the wrong page / wrong depth.** `wikipedia.lookup()` searches
   the *raw claim string*, takes the top hit (usually a person's bio, not the event),
   and returns only the **intro (6 sentences)**. The granular fact being checked — a
   goal minute, a lap number, a job title — lives deep in the article body, never in
   the intro. So the authoritative channel whiffs and the judge falls back on noisy
   DDG snippets → **false "contradicted"**.
2. **Token waste on auto-correction.** The gate then "auto-corrects" flagged claims
   using those same noisy results — rewriting claims that were actually correct, and
   in one observed case (Senna 2026-06-13) **shortening the script 1842→1382 words**
   chasing false positives.

Net effect, observed on the 2026-06-13 overnight run: across 3 scripts the gate
flagged **21 claims; ~17 were false-positives**. Everything dumps to `needs_review`,
so a human must re-verify every script by hand. The gate is doing its job (it never
*missed* a real error) but at a high false-positive and token cost.

This is by design — ADR-0005 was built reactively the day after a video shipped a
fabricated fact, prioritising "never ship a fabrication" over precision, with human
review as the safety net. This spec keeps that safety guarantee while removing the
false-positive tax.

## Goals

- Cut false positives on encyclopedic (well-documented historical) claims so clean
  scripts can pass without hand-review.
- Cut LLM cost from ~27 calls/script to **2 typical** (extract+classify, batched
  judge) — **+1 per overflow chunk** on unusually long scripts (see Stage 3).
- Compound savings across videos via an entity cache (a sports channel reuses
  "Ayrton Senna", "1994 San Marino GP", etc. constantly).
- **Never** auto-pass a claim that isn't genuinely confirmed (confidence floor), and
  **never** auto-pass a current/recent claim MediaWiki can't vouch for.
- Roll out behind **shadow mode** so the loosening is measured, not assumed.

## Non-goals (explicitly not building)

No vector DB / embeddings / RAG over a knowledge base. No multi-source consensus
voting. No fine-tuned claim classifier. A judge prompt does claim-typing fine at
one-video-a-day volume; targeted MediaWiki queries beat semantic search and cost
nothing. Revisit only at thousands-of-scripts scale.

## Decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Integration | **New engine + thin shim.** `fact_gate.py` holds all logic; `factcheck.py` becomes a thin shim re-exporting it, **preserving the `factcheck.json` schema**. `run_auto`, `run_factcheck`, the fact-review skill — all keep working. |
| 2 | Entity cache | **Persistent JSON file** keyed by resolved article title, long TTL. |
| 3 | Auto-correct | **Dropped — human-only.** The gate emits verdicts; genuine issues route to human review. No automated script rewriting. |
| 4 | Rollout | **Shadow mode is the mandatory first stage** (see Rollout). The auto-pass loosening flips on only after a written threshold is met. |

## Architecture

A claim flows through four stages. **Two** of them are LLM calls; the rest is free
HTTP.

```
script.md
   │
   ▼  (LLM call #1)
extract_and_classify ──► [Claim{text, entity, fact, era}]   (uncheckable claims dropped here)
   │
   ▼  (free HTTP, tiered, cache-backed)
gather_evidence ─────►  encyclopedic → MediaWiki (targeted + section window)
                        recent / MediaWiki-thin → DDG fallback
   │
   ▼  (LLM call #2)
judge (batched) ─────►  [Verdict{status, correction, source, evidence_kind}]
   │
   ▼  (pure Python)
aggregate ───────────►  {checked, supported, issues, complete, max_claims, passed}
                        + would_auto_pass  (shadow telemetry)
```

### Stage 1 — `extract_and_classify(script_md, max_claims) -> list[Claim]`  *(LLM call #1)*

One structured call that does extraction **and** classification together (the biggest
lever — it shrinks the problem before any routing):

- Returns only **checkable** claims (date, score, name, quantity, sequence, location).
  Opinion / framing / narration ("a gifted driver", "two codes, one track") are
  dropped and never enter the pipeline. Typically halves claim volume.
- Each claim is tagged:
  - `entity` — the subject to look up (e.g. `"1998 FIFA World Cup Group F"`), not the
    whole sentence.
  - `fact` — the specific assertion to confirm (e.g. `"Mahdavikia scored in the 84th
    minute"`).
  - `era` — `encyclopedic` | `recent`. Model tag **plus a deterministic heuristic
    backstop**: any year ≥ the current year, or phrases like "this year / last week /
    currently / as of <recent date>", force `recent` regardless of the model tag.
    (The heuristic can only make a claim *more* cautious, never less.)

`Claim` is a small typed dict: `{text, entity, fact, era}`.

### Stage 2 — `gather_evidence(claim) -> Evidence`  *(free HTTP, tiered)*

- **`encyclopedic` → MediaWiki first:**
  1. **Resolve:** MediaWiki search using `entity + fact` keywords (not the raw
     sentence) → best article title. (Cache: `resolutions[query] -> title`.)
  2. **Fetch full plaintext** of that title (`prop=extracts&explaintext`, **not**
     `exintro`). (Cache: `extracts[title] -> {text, fetched_at}`.)
  3. **Window:** select the paragraphs/sentences containing the `fact` key terms, cap
     to a token budget. This is what gets the deep fact (lap number, goal minute) to
     the judge.
- **`recent`, or `encyclopedic` where MediaWiki returned thin/empty evidence → DDG
  fallback** (`web_search`, the existing free client). This is the minority of claims.
- `Evidence` carries `{kind: encyclopedic|web|none, text, source_url}`.

Never raises — any lookup failure yields `kind="none"`. A `kind="none"` claim is **not
dropped**: it still goes to the judge (with empty evidence) and comes back `unverified`
(an issue → human), never silently removed from coverage (see Stage 4, item 1).

### Stage 3 — `judge(claims_with_evidence) -> list[Verdict]`  *(LLM call #2, batched)*

All claims + their gathered evidence in **one** structured call → JSON array of
verdicts. Prompt rules:

- **Confidence floor:** return `supported` **only** if the evidence confirms the
  **same entity and the same specific fact** — not fuzzy keyword overlap. Ambiguous,
  partial, wrong-entity, **or empty (`kind="none"`)** evidence → `unverified`. (Trading
  DDG's false-flags for MediaWiki false-*passes* would be worse — a false pass ships an
  error.)
- **Source weighting:** encyclopedic confirmation outranks web snippets. A
  MediaWiki-confirmed fact is **not** second-guessed by a weak DDG snippet.
- Verdict: `{claim, status: supported|contradicted|unverified, correction, source,
  evidence_kind}`. **`correction` is human-facing guidance only — nothing consumes it
  programmatically** (auto-correct is gone; do not rewire it into a rewrite).
- **Chunk fallback:** if total evidence exceeds a token budget, split into ≤K-claim
  chunks and concatenate verdicts (rare after windowing). This is **+1 LLM call per
  overflow chunk** — so the cost figure is **"2 calls typical, +1 per overflow chunk,"**
  not a hard 2.
- **Judge failure → fail closed, loudly.** If the judge call fails after retries,
  every claim becomes `unverified`, `complete=False`, `passed=False` — the whole script
  routes to human review. A broken judge never produces an auto-pass.

### Stage 4 — `factcheck(script_md, max_claims) -> dict`  *(orchestrator)*

Runs stages 1–3 and aggregates into the **exact existing schema** so downstream is
untouched:

```json
{
  "checked":  <int>,            "supported": <int>,
  "issues":   [ {"claim","status","correction","source"} , ... ],
  "complete": <bool>,           "max_claims": <int>,
  "passed":   <bool>,
  "would_auto_pass": <bool>     // NEW — shadow telemetry (see Rollout)
}
```

**Invariant (item 1 — closes the fail-open seam): every checkable claim terminates in
exactly one of `{supported, contradicted, unverified}`. A claim is NEVER silently
dropped.** A claim whose evidence-gathering failed (`kind="none"`) is still sent to the
judge (with empty evidence) and MUST return `unverified`. `unverified` is always an
issue. So a claim can never vanish from *both* `issues` and the coverage denominator —
the only way to "disappear" is to be `supported`, which requires the confidence floor.

- `issues` = every `contradicted` verdict **+ every `unverified` verdict** (no
  exceptions; a `kind="none"` claim is therefore always an issue → human review).
- `complete` = **extraction was not truncated** — every checkable claim in the script
  was extracted *and* adjudicated, i.e. the `max_claims` cap did not force any claim to
  be skipped. It is **not** a fraction and never reduces the denominator by dropping a
  claim. (If the script has more checkable claims than `max_claims`, `complete=False`
  → cannot auto-pass.)
- `passed` = `complete and not issues` → in practice, **passes only if every checkable
  claim came back `supported`** with nothing truncated.
- `would_auto_pass` = the gate's *real* verdict (== `passed`), recorded even in shadow
  mode where the produce flow ignores it.

## Entity cache (persistent JSON)

- Path: `config.FACTCACHE_PATH`, default `<root>/.factcache.json`, **gitignored in the
  same commit that introduces it** (a cache committed once is annoying to purge and
  leaks processed-entity history).
- Shape: `{"resolutions": {query: title}, "extracts": {title: {text, fetched_at}}}`.
- Keyed by **resolved article title** so the 2nd Senna video reuses
  "Ayrton Senna" / "1994 San Marino Grand Prix" for free.
- TTL: **30 days** (`config.FACTCACHE_TTL_DAYS`). Historical facts are stable, but
  **living entities have moving tails** — "Verstappen has won four titles" goes stale
  the day he wins a fifth. 30 days bounds that staleness while still giving a
  daily-cadence channel heavy intra-month reuse; expired entries are re-fetched. This
  does **not** fully close the living-entity gap (see Risks) — a count that changes
  *within* the TTL against a cached extract can still false-pass; that residual is what
  shadow mode is there to catch.
- Concurrency: overnight `run_auto` produces sequentially (count=3, one at a time), so
  read-modify-write of the JSON file is safe. Writes are atomic (temp file + rename).
- Per-machine: if produce runs on Railway and a second machine elsewhere, each builds
  its own cache. Acceptable — the cache is an optimisation, not a source of truth.

## Rollout — shadow mode (mandatory first stage)

The change removes the **only human checkpoint before compute is spent**. Today a bad
script is caught at review, *before* the 45-min render. After the loosening, a
false-pass renders overnight and arrives as a **polished, persuasive video** — harder
to fact-check by eye than a bare script. `awaiting_approval` still gates YouTube, but
your eye there is reviewing a finished artifact whose production polish lends false
claims credibility. So the loosening is real and must be measured, not assumed.

- **`config.FACT_GATE_SHADOW: bool`** — `True` on launch.
- **In shadow mode:** the gate computes its real verdict and records `would_auto_pass`
  (+ the full verdict set) into `factcheck.json` and appends one line per script to a
  gitignored **`.factgate-shadow.jsonl`** (`{id, would_auto_pass, would_pass_claims,
  issues, ts}`). **`run_produce` behaviour is unchanged** — every script still routes
  to `needs_review`/human exactly as today. **Zero safety lost.**
- **The oracle proves it works on the known; shadow mode proves it works on the
  unknown.** Three hand-verified scripts can't tell you the false-pass rate on the
  unseen scripts the gate will actually face. Shadow mode measures that at zero risk.

### Written flip threshold (defined now, not "when it feels right")

Flip `FACT_GATE_SHADOW = False` only when **all** hold over a contiguous shadow window:

1. **≥ 10 consecutive real scripts** recorded in shadow.
2. **Zero false-passes:** no claim the gate `would_auto_pass` was later marked by the
   human reviewer as a genuine error. *Any* false-pass **resets the counter to 0** and
   triggers a gate fix.
3. **≥ 3 true auto-passes:** at least three of those scripts were ones the gate
   `would_auto_pass` whole **and** the human confirmed clean — proving the gate isn't
   just flagging everything to stay safe.

**Measurement integrity (item 4) — the threshold is only as honest as the review
behind it.** The "zero false-passes" criterion holds only if human review stays at
full rigor during shadow. There's a real drift risk: as confidence grows, attention
slackens, and you record zero false-passes because you stopped looking hard, not
because there are none — crossing the threshold on degraded evidence. **Protocol:
during shadow, review each script at constant rigor and BLIND to the gate's
`would_auto_pass`** — verdict the script first, *then* reveal what the gate decided and
compare. `would_auto_pass`/`would_pass_claims` must not be visible (or must be ignored)
until your own verdict is recorded, so the gate can't anchor you.

When met, flipping the flag is the only change: `passed → in_production` (render
overnight, no script-stage human review); `recent`/`unverified` scripts still →
`needs_review` → human. The publish gate (`awaiting_approval` → human `--approve`)
remains regardless.

## Changes outside the new file (consequences of dropping auto-correct)

- **`engine/pipeline/factcheck.py`** → thin shim re-exporting `fact_gate`'s
  `extract_*`, `factcheck`, etc. `correct_script` **removed**.
- **`engine/run_produce.py`** → drop the auto-correct chain. Flow becomes
  produce → verify → (shadow: always `needs_review`) / (live: `in_production` if
  `passed`, else `needs_review`).
- **`engine/run_factcheck.py`** → `--fix` **removed/deprecated** (human-only).
- **`.claude/skills/fact-review/SKILL.md`** → drop the `--fix` mention; the human
  override is hand-edit + `--review`, as already practised.
- **`engine/config.py`** → add `FACTCACHE_PATH`, `FACTCACHE_TTL_DAYS=30`,
  `FACT_GATE_SHADOW=True`.
- **`engine/ideate/wikipedia.py`** → gains dumb primitives `search_title(query)` and
  `extract(title, full=True)`; resolution/windowing/cache smarts live in
  `fact_gate.py`. (Keeps `wikipedia.py` a thin client.)
- **`.gitignore`** → add `.factcache.json` and `.factgate-shadow.jsonl` **in the same
  commit** that introduces them.

## Testing (TDD; mock the LLM `_structured` and HTTP)

**Known-answer oracle (regression against my 2026-06-13 hand review):**
- Senna (`f058733a`) → `passed=True` (≈ clean; the 9 gate flags were false-positives).
- World Cup (`4ef3fc89`) → flags the **Lalas "played that day"** error; does **not**
  false-pass it; the 2026 strike/boycott/Tijuana/group claims are `recent` → not
  auto-passed.
- Massa (`648d57e6`) → flags **Symonds title** and **Briatore 2022/ambassador**; does
  not false-pass them; lap-15 / lap-12 / Nov-2025-ruling claims `supported`.

The hand-fixes were applied to the live scripts in place (no pre-fix backup), so the
oracle does **not** depend on recovering the original scripts. Instead it uses small,
**hand-authored claim fixtures** that capture the exact known-wrong claims —
`"Alexi Lalas … who played that day"`, `"Technical director Pat Symonds"`,
`"returns to Formula 1 in 2022 as an ambassador"` — alongside a sample of the
confirmed-correct ones (lap 15 / Turn 17, Mahdavikia 84', Massa proceedings March
2024). Each fixture pairs the claim with the **authoritative evidence already fetched**
during the 2026-06-13 review (Wikipedia extracts), mocked offline and deterministic.
The test asserts the gate flags the three errors (and never `supported`s them) and
`supported`s the correct ones — reproducing the human verdicts at claim granularity.

**Honest scope of the oracle (item 3):** it mocks stages 1 and 2 (extraction and
evidence-gathering) and exercises only the **judge** with clean claims + correct
evidence. But the original false positives came *from* stages 1–2 (wrong-page
Wikipedia, intro-only depth) — the very stages the oracle mocks past. **So a green
oracle proves the judge prompt is sound; it does NOT prove the pipeline fixes the
false-positive problem.** That proof comes only from shadow mode. A passing oracle is
**not** license to shorten the shadow window or lower the flip threshold.

**Stage 1–2 resolution test (covers what the oracle can't):** run the *real*
`gather_evidence` resolution + windowing against **recorded MediaWiki API JSON
fixtures** (the actual responses for "1998 FIFA World Cup Group F", "Renault Formula
One crash controversy", "Ayrton Senna"). Assert it (a) resolves to the correct article
title from an `entity+fact` query, and (b) the windowed extract **contains the deep
fact** (the 84' minute, the lap-15 Turn-17 line, the steering-column ruling) — i.e. it
no longer returns intro-only. Deterministic, offline, and it tests the actual bug fix.

**Unit:**
- Uncheckable claims (opinion/framing) dropped at stage 1.
- Era heuristic forces `recent` on a future year even if the model tags it
  encyclopedic.
- Encyclopedic + strong MediaWiki evidence → `supported`, **no DDG call made**.
- MediaWiki thin/empty → DDG fallback invoked.
- `recent` claim → never auto-passes on MediaWiki; routes to DDG + stays an issue if
  unconfirmed.
- Confidence floor: wrong-entity / fuzzy evidence → `unverified`, not `supported`.
- Batched judge maps array → `issues` correctly.
- Cache hit skips the 2nd MediaWiki fetch (persistent JSON round-trip).
- Schema compatibility: `factcheck()` returns all existing keys + `would_auto_pass`.
- Shim: `factcheck.py.factcheck()` returns identical schema.
- Never raises — any LLM/HTTP failure self-stubs (gate must not crash the run).
- Shadow mode: `run_produce` routes to `needs_review` even when `would_auto_pass` is
  True; a shadow line is appended.

## Risks / impact (honest)

- **Removes the pre-render human checkpoint** once live — the single real impact.
  Mitigated by: shadow mode + written flip threshold + the oracle + the unchanged
  `awaiting_approval` publish gate.
- **Rewriting a safety-critical component** can fail open (ship misinformation) or
  closed (nothing passes). Mitigated by TDD + oracle + dual adversarial review.
- **MediaWiki false-pass** (the dangerous direction) — guarded by the confidence floor
  (`supported` requires same-entity-same-fact) and shadow measurement.
- **Living-entity staleness gap (item 2, known + accepted).** A genuinely-recent claim
  with no year or temporal phrase ("Verstappen has won four titles") can be tagged
  `encyclopedic`, hit a cached extract that's stale *within* the 30-day TTL, and
  false-pass against out-of-date evidence. The era heuristic only triggers on explicit
  temporal cues, so it won't catch this. Partially mitigated by the 30-day TTL (vs
  180); a per-entity "volatile/active" shorter TTL is a **deferred option**, not built
  now. Named here so it's a decision, not an accident — and shadow mode is the net that
  surfaces it before flip.
- **Oracle scope (item 3).** The known-answer oracle mocks stages 1–2, so it validates
  the judge, not the end-to-end false-positive fix (see Testing). A green oracle is not
  evidence the pipeline works on unseen scripts — only shadow mode is. Do not let a
  passing oracle shorten the shadow window.
- **Contained elsewhere:** schema preserved → most consumers untouched; only 3 small
  caller edits; new gitignored cache; more (free, cached) MediaWiki calls; render and
  the 3 in-flight videos unaffected.
