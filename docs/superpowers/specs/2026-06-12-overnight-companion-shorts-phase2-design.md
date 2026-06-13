# Overnight 3-Long-3-Short Companion Automation (Phase 2) — Design

**Date:** 2026-06-12
**Status:** Approved (pending spec review)
**Author:** session 11

## Problem

The nightly overnight job (`scripts/overnight.sh` → `run_auto --count 3`) produces and
renders **3 long-form videos** only. The desired strategy is **3 long + 3 short**:
each nightly long also gets a companion **teaser short** that points viewers to the
long. This is Phase 2 of the long+companion-short pipeline (Phase 1 — the artifact
split, queue `long`/`short` URL fields, YouTube description-patch, and `--backlink` —
already shipped).

## Goal

Extend the overnight automation so each of the 3 nightly longs spawns a cross-linked
companion teaser short: 3 long + 3 short produced → rendered → `awaiting_approval`,
and one approval uploads both (long first, short's description linking the long).

## Non-goals

- New companion shorts for the 5 already-published shorts. Those stay as-is; Phase 1
  back-links them to their longs. This generator is for **new** longs only.
- A standalone short pipeline. The companion short is always **derived from a long**.
- Changing `cadence.yaml` (that drives the Stage-2 publish scheduler, not production).
- A second web fact-gate on the short (see Decisions).

## Decisions (locked during brainstorming)

- **Companion short stays on the approved Senna/World Cup short template** — same visual
  render (vertical, mood voice, whisper captions, mood music, sport b-roll, branding) AND
  the same punchy short-writer style. We do NOT introduce a new/divergent short format.
  The only net-new element is an added "Full story on our channel" CTA pointer. Its
  *content* is derived from (and constrained to) the verified long via
  `derive_short_tease(long_script, idea)` — a condensed Senna-style short of the long
  story, not a withholding-cliffhanger.
- **No redundant web fact-gate on the short.** The long is already fact-gated; the tease
  uses only the long's verified content, so it is verified by construction. Integrity is
  kept honest by a **deterministic containment guard** (no network): the short must not
  introduce any name/date/number absent from the long. If it does, that short is marked
  `needs_review` instead of auto-published.
- **On-screen CTA only; URL in description.** The short's `EndCTA` shows "Full story on
  our channel — link in description"; the long's URL is appended to the short's YouTube
  **description** at upload (never rendered into pixels).
- **One approval, long-first.** `run_auto --approve <id>` uploads the long (unlisted) →
  captures `long_youtube_url` → uploads the companion short (unlisted) with
  `▶ Full story: <long_url>` appended to its description. Unlisted only; never `--public`
  without explicit say-so.
- **Count stays `--count 3`** (3 ideas → 3 long + 3 short). `caffeinate` (already in
  `overnight.sh`) keeps the M2 awake for the ~6 renders.

## Architecture

### Component 1 — `derive_short_tease` (`engine/pipeline/script.py`)

```python
def derive_short_tease(long_script: str, idea: dict) -> dict   # {"script": str, "mood": str}
```
Reuses the **same approved short-writer style** as `generate_short_script` (the prompt
that produced the Senna/World Cup shorts: MOOD header, write-for-the-ear, high-retention,
within `config.SHORT_SCRIPT_WORDS_MIN..MAX`) — the only difference is the **source**: it
is seeded with the full fact-gated long script and constrained to **use only facts already
in the long — no new names, dates, numbers, or claims**. Output is a condensed Senna-style
short of the long story (it may end on a hook, but it is NOT a divergent withholding
format). Returns `{script, mood}` via the existing `_parse_short`; short metadata via the
existing `generate_short_metadata`. Keep the prompt as close to `generate_short_script`'s
as possible so we don't stray from the approved base.

### Component 2 — Containment guard (`engine/pipeline/factcheck.py` or `script.py`)

```python
def tease_within_long(short_script: str, long_script: str) -> tuple[bool, list[str]]
```
Deterministic, no network. Extracts factual specifics from the short — proper nouns
(reuse `captions.proper_nouns`-style capitalized-token extraction) and numbers/years
(digits and spelled forms) — and returns `(ok, new_tokens)` where `ok` is False if any
specific is absent from the long. A failed check marks the short `needs_review` (the
long is unaffected).

### Component 3 — Short "Full story" CTA (Remotion `EndCTA.tsx`)

Add an optional `fullStory?: boolean` prop. When set (companion short renders), the
EndCTA shows a "Full story on our channel — link in description" line beneath the
subscribe card. Wired from `remotion_build` short props (a `fullStory: true` flag).

### Component 4 — Overnight orchestration (`engine/run_auto.py`)

Extend the pipeline so each produced+rendered+QC'd long also spawns its companion short:
- After a long reaches a render-cleared state and renders to `awaiting_approval`, run a
  companion-short sub-step: `derive_short_tease(long_script)` → containment guard →
  short metadata → `run_video --format short --render` → `qc_video(id, "short")`.
- The idea now carries both `long/` and `short/` artifacts (Phase-1 split). Track the
  short's state (e.g. `short_status`: `awaiting_approval` / `needs_review` /
  `render_failed`) without disturbing the long's `status`.
- A companion-short failure (derivation, guard, or render) must **never** fail the long
  — self-stub: the long still reaches `awaiting_approval`; the short is flagged.

### Component 5 — Paired upload (`engine/run_auto.py` `cmd_approve`)

`--approve <id>` (long is `awaiting_approval`):
1. Upload the long unlisted → `long_youtube_url` (existing).
2. If a companion short artifact exists and is clean: build its description
   = `<short metadata description>\n\n▶ Full story on our channel: <long_youtube_url>`,
   upload the short unlisted → `short_youtube_url`.
3. A short-upload failure does not roll back the long; it's reported for retry.

## Data flow

```
overnight: run_auto --count 3
  per pending idea:
    produce long → fact-gate → render long → qc(long) → awaiting_approval
    derive_short_tease(long) → containment guard
      → short metadata → render short → qc(short) → short awaiting_approval | needs_review
AM: run_auto --approve <id>
    upload long (unlisted) → long_youtube_url
    upload short (unlisted), desc += "▶ Full story: <long_url>" → short_youtube_url
```

## Error handling / conventions
- Self-stub everywhere: a companion-short failure never aborts the long or the batch.
- Integrity (ADR-0005): the long keeps its web fact-gate; the short is verified by
  derivation + the containment guard. A guard failure → short `needs_review`, not
  published.
- Render is never a gate (CLAUDE.md): proven via `pytest tests/` + QC + still-preview.
- Unlisted only; `--public` never added without explicit say-so.

## Testing (`pytest tests/`, python3 main env)
- `derive_short_tease` (mocked model): returns `{script, mood}`, length within the short
  band, MOOD parsed; prompt includes the long script + the "no new facts" constraint.
- `tease_within_long`: passes when the short's names/numbers ⊆ long's; fails and lists the
  offending token when the short adds a new name/date/number.
- `run_auto` orchestration (mocked produce/render/qc): a long success spawns a companion
  short sub-step; a short-substep failure leaves the long `awaiting_approval` and flags
  the short (batch continues).
- `cmd_approve` paired upload (mocked uploader): long uploaded first, short uploaded with
  the long URL appended to its description; short failure doesn't roll back the long.
- `EndCTA` renders the "Full story" line only when `fullStory` is set (tsc compile).

## Out of scope / follow-ups
- The 4 backfill longs (World Cup/O.J./Barry/Sachin) are produced+rendered separately and
  their existing shorts are back-linked (Phase 1) — not via this generator.
- Per-format QC thresholds tuning, and any cadence/count config knob, are future work;
  the count stays `--count 3`.
