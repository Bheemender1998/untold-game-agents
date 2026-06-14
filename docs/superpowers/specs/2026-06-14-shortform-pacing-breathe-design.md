# Short-form pacing — "let it breathe"

**Date:** 2026-06-14
**Status:** Approved (design)
**Branch:** `feat/shortform-pacing-breathe`

## Problem

Reviewing the two freshly-rendered shorts (`050d8550`, `9bbd24cd`), the human
note was: *"everything is good but it seemed very hurried, the narration is very
fast on the short, and the video came to a conclusion abruptly."*

Root causes, confirmed in code:

1. **Narration is fast.** `SHORT_NARRATION_SPEED = 1.12` (12% faster than the
   long-form 0.9) with `SHORT_NARRATION_GAP_S = 0.12` (vs 0.5 long-form) — almost
   no pause between sentences.
2. **The payoff blurs into the facts.** The inter-sentence gap is uniform, so the
   closing line gets the same 0.12s lead-in as every rapid-fire fact.
3. **Abrupt ending.** In `UntoldShort.tsx`, the subscribe EndCTA card starts at
   `from={narrationMs}` — the instant the last word ends, the story b-roll cuts
   straight to the subscribe card. There is no beat where the final shot + music
   hold.

## Goal

Make shorts feel less hurried and end on a beat that lands, **without** touching
long-form. Every change is gated to `format == short`; long-form
(`UntoldVideo`, `NARRATION_SPEED`, default `endHoldMs`) is byte-for-byte
unchanged.

## Non-goals

- No change to long-form pacing or the long-form composition.
- No change to the short word-count target (110–135 stays).
- No new facts in the payoff (the ADR-0005 integrity rule is untouched).

## Design

All four changes are coordinated and small. Long-form is the default path
everywhere, so each new knob defaults to its current behavior.

### 1. Slow the read — `engine/config.py`

| Knob | From | To |
|------|------|----|
| `SHORT_NARRATION_SPEED` | `1.12` | `1.05` |
| `SHORT_NARRATION_GAP_S` | `0.12` | `0.20` |

### 2. Set the payoff apart — `engine/config.py` + `engine/video/tts.py`

- New `SHORT_END_GAP_S = 0.6` in config.
- `_synth_kokoro` gains an optional `end_gap_s: float | None = None` parameter.
  When set, the silence inserted **before the final sentence** uses `end_gap_s`
  instead of the uniform `gap_s`. When `None` (long-form), behavior is identical
  to today.
- Threading: `tts.narration_pace(fmt)` returns the end-gap alongside speed/gap
  (e.g. `(speed, gap_s, end_gap_s)` where `end_gap_s` is `SHORT_END_GAP_S` for
  short, `None` otherwise). `synthesize()` / `_synth_kokoro` accept and forward
  `end_gap_s`. `run_video.py` passes it through.
- Implementation note: the gap is appended *after* each sentence today
  (`chunks.append(sent); chunks.append(gap)`). To make a larger gap land *before*
  the last sentence, insert the larger silence ahead of the final chunk (i.e.,
  before synthesizing the last sentence, swap the trailing gap of the
  second-to-last sentence for `end_gap_s`). The last sentence keeps the normal
  trailing gap.

### 3. End breath before the CTA — render layer

Files: `engine/config.py`, `engine/video/remotion_build.py`,
`engine/video/remotion/src/types.ts`, `engine/video/remotion/src/Root.tsx`,
`engine/video/remotion/src/UntoldShort.tsx` (and `shortDefaultProps.ts`).

- New `SHORT_END_HOLD_MS = 1000` in config.
- New prop `endHoldMs: number` (default `0`) on the Remotion props type.
- `build_props` accepts `end_hold_ms` and sets `props["endHoldMs"]`.
  `run_video.py` passes `config.SHORT_END_HOLD_MS` for shorts, `0` otherwise.
- `Root.tsx` total frame count for the short: `introMs + narrationMs + endHoldMs
  + outroMs` (long-form `UntoldVideo` total is unchanged; its `endHoldMs`
  defaults to 0).
- `UntoldShort.tsx`: the EndCTA `<Sequence>` starts at
  `introF + ms2f(narrationMs + endHoldMs)` instead of `introF + ms2f(narrationMs)`.
  The background/b-roll track already covers the full composition length, so it
  holds (freeze-on-last-frame) during the breath; music continues.

### 4. Stronger payoff line — `engine/pipeline/script.py`

- In **both** short writers' system prompts (the primary short writer ~L100–155
  and `DERIVE_TEASE_SYSTEM` ~L212–235), change the PAYOFF beat instruction from a
  single closing line to **1–2 sentences that resolve the story** — a conclusion
  that feels earned, not clipped. Keep "nods that the full story is bigger" and
  the hard integrity rule (no new name/date/number/quote not already present).

## Impact

- Duration: ~+5–7s vs current → shorts land ~58–63s, within Shorts limits.
- Only future shorts change. The two already-rendered shorts will be re-rendered
  after merge:
  ```
  python3 -m engine.run_video --id 050d8550 --format short --render   # or run_produce + run_thumbnail as the pipeline dictates
  python3 -m engine.run_video --id 9bbd24cd --format short --render
  ```
  (Exact re-render entrypoint confirmed during implementation; payoff-line change
  requires re-running the short script step, the others are render-only.)

## Testing

- `python3 -m pytest tests/ -q` — the contract (PostToolUse hook runs it too).
- New/updated unit tests:
  - `narration_pace("short")` returns the new speed/gap and `SHORT_END_GAP_S`;
    `narration_pace("long")`/default returns `None` end-gap.
  - `_synth_kokoro` places the larger gap before the final sentence when
    `end_gap_s` is set, and is unchanged when `None` (assert on the concatenated
    sample length / gap positions, mocking `Kokoro.create`).
  - `build_props` sets `endHoldMs` from its argument; defaults to 0.
- Render verification is **not** a gate (per CLAUDE.md): use the still-preview /
  one short re-render to eyeball the breath + pace.

## Rollout

Ships via the `ship-video-change` rail (multi-file engine change): feature
branch, pytest, dual adversarial review (Codex + Claude), PR with
`Adversarial-Reviewed:` trailer, squash-merge. Docs updated in the same PR
(`CLAUDE.md`/config comments already self-describe the knobs).
