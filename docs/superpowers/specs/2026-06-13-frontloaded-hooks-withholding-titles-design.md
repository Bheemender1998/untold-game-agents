# Front-loaded hooks + withholding titles (text layer)

**Date:** 2026-06-13
**Status:** Approved — ready for implementation plan
**Slice:** 1 of N from the cross-platform packaging feedback (text layer only)

## Problem

External review of the channel's videos and Shorts found the scripts are elite but
*packaged* like audio dramas, not viral video. Two text-layer defects:

1. **Hooks bury the payoff.** Shorts open with a slow, atmosphere-building cadence
   ("He is 1,457 yards from the record. He is 31. He is healthy…") instead of
   front-loading the central mystery in sentence one. On TikTok/Reels you have ~2
   seconds, not 15.
2. **Titles give away the premise.** The metadata prompt already says
   "curiosity-driven," but titles still state the whole story rather than opening a
   curiosity *gap*. Shorts are worse: they reuse the long-form title verbatim
   (`metadata.py:140` — `title = idea["title_variants"][0]`), so they get zero
   short-form packaging.

The review's own "optimized" examples quietly break integrity (rounded `1,457`→`1,500`,
unverifiable superlatives, editorial framing like "The Lie America Believed"). The fix
must NOT reopen the door ADR-0005's fact-gate closed.

## Scope

**In scope (this slice):**
- Front-load the hook (long cold-open, original Shorts, companion-tease Shorts).
- Open titles via withholding, not editorializing.
- Give Shorts a dedicated title pass instead of reusing the long title verbatim.
- A deterministic integrity backstop on the new Short title.
- Retitle the existing rendered/queued queue (metadata-only, no re-render).

**Explicitly out of scope (deferred slices):**
- Long-form render pacing (chapter cards, music swells, holding on silence).
- Shorts visual cadence (pattern interrupts, animated on-screen text, TTS speed).
- Thumbnails (`thumbnail.py` is a 7-line stub) and channel branding/positioning.
- Re-rendering existing videos' baked-in hooks.

## The integrity rule (the spine)

One rule, derived from the approved decisions, stated in every place that writes a
hook or a title:

### Hook rule
> Front-load the **mystery**, not the data. The strongest hook carries **no** specific
> number, name, or date — it opens on the emotional stakes and the unanswered question
> (*"He was one season from immortality. Then he walked away."*). Specifics arrive in
> the FACT beat, not the hook. This mystery-first hook is **the goal, not a safe
> fallback** — it is the scroll-stopper. If a specific *does* survive into the hook, it
> must be the **exact verified value**: never round (`1,457`, never `~1,500`), never
> assert a superlative as fact (*"the greatest … in history"*).

### Title rule
> Open the curiosity gap by **withholding the resolution**, never by editorializing.
> Make the unanswered question irresistible (*"Ten days after this own goal, he was
> dead."*) without giving away the payoff and without asserting framing not literally
> supported by the script (*"The Lie America Believed"* is banned — that's spin, not
> withholding). Same specifics rule as the hook: exact verified values or none.

## Components

### 1. `engine/pipeline/script.py` — hook rule into three prompts
- `SHORT_SYSTEM` — rewrite the HOOK beat with the hook rule.
- `DERIVE_TEASE_SYSTEM` — rewrite the HOOK beat with the hook rule (companion tease).
- `SCRIPT_SYSTEM` — extend the cold-open bullet with the hook rule.

These are prompt-string edits only. No behavioral code change.

### 2. `engine/pipeline/metadata.py` — title rule + dedicated Short title pass
- `METADATA_SYSTEM` — add the title rule to the TITLE bullet (long-form titles).
- **New `_short_title_llm(idea, script) -> str`** — a small structured-output LLM call
  (mirrors `_short_desc_llm`) that writes a punchy, front-loaded, gap-opening Short
  title (≤ ~70 chars, mobile-legible), using only facts in the (already fact-gated)
  script. System prompt carries the title rule.
- **`generate_short_metadata`** — replace the verbatim `title = idea["title_variants"][0]`
  with the result of `_short_title_llm`, guarded by the §3 backstop. **Self-stub to
  `title_variants[0]`** if the LLM call fails OR the backstop rejects the title (matches
  the existing self-stub discipline in this function — an agent/stage must never crash
  the run).

### 3. Short-title integrity backstop — digit-group containment only
- **New helper** (next to `tease_within_long` in `script.py`, reusing `_TEASE_NUM_RE`),
  e.g. `title_numbers_within(title, script) -> tuple[bool, list[str]]`: returns whether
  every digit group in the title appears as a digit group in the script, plus the list
  of novel numbers.
- `generate_short_metadata` calls it; a non-empty novel-number list → reject the LLM
  title and self-stub to `title_variants[0]`.
- **Digit groups only — not the proper-noun half of `tease_within_long`.** Rationale:
  `_TEASE_NAME_RE` selects proper-noun candidates *by capitalization*, but titles are
  Title Case, so every content word ("Tournament", "Supposed") becomes a candidate and
  inflected/reworded title words ("walked"→"Walks") false-flag — triggering needless
  fallbacks. Lowercasing before comparison does not fix candidate selection. Numbers do
  not inflect or get title-cased, so digit containment is surgical (near-zero false
  positives) and catches the real risk: a fabricated stat in a title going live
  unchecked during mass retitling. Name-swap detection in titles is intentionally not
  attempted here.

### 4. Rollout — no new orchestration code
- **New content:** automatic via `run_produce` / `run_auto` once the prompts change.
- **Retitle existing queue (5 unlisted Shorts + queued longs):** the existing
  `--metadata-only` path already regenerates `metadata.json` from the on-disk script
  without touching the render. Because the new Short-title pass lives *inside*
  `generate_short_metadata`, re-running picks it up for free:
  - Long:  `python3 -m engine.run_produce --id <id> --metadata-only`
  - Short: `python3 -m engine.run_produce --id <id> --format short --metadata-only`
- Baked-in hooks on already-rendered videos are left untouched (scope decision: titles
  are metadata, hooks are baked into TTS+captions and would require a re-render).

## Testing (`python3 -m pytest tests/` under `python3`, the contract)

1. **Short title — happy path:** `generate_short_metadata` returns the `_short_title_llm`
   title when the (mocked) call succeeds and the title's numbers are all in the script.
2. **Short title — LLM failure fallback:** call raises → title falls back to
   `title_variants[0]`.
3. **Short title — backstop fallback:** a generated title containing a number absent
   from the script → falls back to `title_variants[0]`; a title whose numbers are all in
   the script is kept.
4. **`title_numbers_within` unit:** novel digit group detected; matching numbers pass;
   title with no numbers passes.
5. **Integrity-rule regression guards:** assert the hook-rule / title-rule marker text
   is present in `SHORT_SYSTEM`, `DERIVE_TEASE_SYSTEM`, `SCRIPT_SYSTEM`, and
   `METADATA_SYSTEM`, so a future conversational prompt tweak can't silently delete the
   moat language.

## Risks & mitigations
- **Mass retitle goes live unchecked** → §3 digit backstop + the script is already
  fact-gated; titles are derived from verified scripts only.
- **Prompt drift erasing the rule** → §5 regression guards.
- **Over-rounding/superlatives sneaking back** → the rule bans them explicitly; the
  existing fact-gate still runs on every produced script.

## Open questions
None — design approved.
