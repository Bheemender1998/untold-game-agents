# Pre-flight QC Lint — design

**Date:** 2026-06-15
**Status:** approved (brainstorm → spec)
**Branch:** `feat/preflight-qc-lint`

## Problem

The 45-minute Remotion render is the most expensive step in the pipeline, yet
caption/headline/TTS defects are only discovered *after* it completes — by watching
the finished MP4. Recent long-form renders (Len Bias, 1972 Olympics) shipped with
visible defects that were present in `props.json` **before** the render ran:

- **Split-number captions** — `$1,000,000` tokenized into three caption words
  `"$1"`, `",000"`, `",000."` (Len Bias `props.json` caption tokens 263–265), so a
  stray `,000` flashes on screen.
- **Zero-duration caption** — token 265 (`",000."`) has `startMs == endMs`, so it
  renders for 0 frames / flickers.

These are "looks fine in code, ugly on screen" defects. They are fully detectable on
the artifacts that already exist before render time, so a pre-flight lint can catch
(and in most cases auto-correct) them without burning a render.

The existing `engine/pipeline/qc.py` is **post-render** — it ffprobes the finished
`video.mp4` for stream/duration/brightness/caption-coverage. It cannot catch these
because they are content defects in `props.json`, not render-output defects.

## Goal

A **pre-flight lint** that runs on `props.json` (and `captions.srt`) *after* props are
built but *before* the render starts. It auto-fixes deterministically-fixable defects,
re-verifies once, and **blocks the render** (marking the idea `needs_review`) if any
CRITICAL defect remains. Mirrors the existing fact-gate pattern (auto-correct once →
re-verify → gate).

Non-goal for this PR: post-render audio mastering checks (CH5 — loudness/ducking, CFR).
Deferred to a separate follow-up that extends `qc.py`. CH3/CH4 typography (block
chunking, safe-zones, descenders, karaoke highlight) are decided by the Remotion
component at render time and are out of pre-flight scope (see Boundaries).

## Source material

The defect taxonomy is mapped from a "Core Production Engineering Specification
Playbook" the user supplied (`~/Desktop/build.py`, a python-docx generator whose
`manifest` payload is the spec). The playbook is written for a *generic* stack
(Node.js / FFmpeg `drawtext` / HTML Canvas / Docker), so it is treated as an **idea
source, not gospel** — rules are mapped onto TUG's real architecture (Remotion/React +
Kokoro TTS + faster-whisper, captions in `props.json`) and stack-specific items are
dropped.

## Data flow (verified)

`engine/run_video.py` (narrated + `--engine remotion`, the LIVE path):

1. TTS → `narration.wav`; faster-whisper → word timings; `captions.align_to_script`
   projects script words onto whisper timing.
2. `remotion_build.build_props(...)` → `props` dict, written to
   `produced/<id>/<fmt>/video/props.json` (run_video.py:122-123).
3. `captions.to_srt(...)` → `captions.srt` (run_video.py:124-126).
4. **Render kicks off (run_video.py:140-144).** ← the 45-minute step.

`props.json` shape (the lint's input):

- `captions`: `[{text, startMs, endMs}]` — word-level.
- `chapters`: `[{headline, startMs, endMs}]`.
- `bBeats`: b-roll beats (not linted in this PR).
- scalars: `fps`, `narrationMs`, `introMs`, `outroMs`, `endHoldMs`, `audioSrc`.

The pre-flight lint slots between step 3 and step 4.

## Architecture

New pure-stdlib module **`engine/video/preflight.py`** — no ffmpeg, no network, no API.
Lives render-side (next to `captions.py`/`compose.py`) so `run_video.py` can call it,
but stdlib-only so it imports cleanly under `python3` for tests and the CLI.

### Public interface

```python
def lint_props(props: dict, fps: int, narration_ms: int) -> tuple[dict, dict]:
    """Run every check on a copy of props. Safe-fixers mutate the copy.
    Returns (fixed_props, report). Never raises — malformed input fails a check."""
```

- `report` shape:
  ```json
  {
    "passed": true,
    "blocked": false,
    "checks": [
      {"name": "split_number_caption", "severity": "critical",
       "passed": true, "detail": "merged 2 orphan-punct tokens", "fixed": 2}
    ],
    "mutations": [
      {"type": "merge", "from": [",000", ",000."], "into": "$1,000,000."},
      {"type": "drop", "token": "the", "reason": "ghost_after_audio",
       "at_ms": 62000},
      {"type": "retime", "token": "basketball", "from": [104960, 104960],
       "to": [104960, 104993], "reason": "min_frame_duration"}
    ]
  }
  ```
  The summary `fixed` integer per check is for metrics; the top-level `mutations`
  array is for **debuggability** — when a creator notices a caption shifted from what
  they wrote, this is the audit trail of exactly what the linter touched and why. Every
  fixer appends a structured entry (`merge` / `drop` / `retime` / `clamp` / `snap`)
  rather than only bumping a counter.
- Severities:
  - **CRITICAL** — blocks the render if it still fails *after* auto-fix.
  - **WARN** — reported in `qc_lint.json`, never blocks.
- `blocked == any CRITICAL check failing after the single auto-fix pass`.

### Auto-fix discipline

One fix pass, then re-verify (fact-gate parity):

1. Run all checks on the input → collect fixes.
2. Apply safe fixers to a copy of `props`.
3. Re-run all checks on the fixed copy.
4. `blocked` = any CRITICAL still failing. Report records `fixed` counts and the
   post-fix pass/fail per check.

Fixers operate on `props["captions"]` and `props["chapters"]` only. **The linter never
writes files and never imports the SRT pipeline** — it returns the mutated `props` dict
and lets the orchestrator (`run_video.py`) regenerate `captions.srt` from the fixed
caption words. This keeps `preflight.py` a pure, side-effect-free, easily-tested
transform and avoids coupling the linter to the caption-chunking code (see
Integration → SRT regeneration).

### Token-merge mechanics (the space dilemma)

When Rule 1/Rule 2 swallows a token into its predecessor, the join must **not** insert
a space for orphan-punctuation fragments, or the Len Bias defect just becomes
`"$1 ,000 ,000."` — still wrong on screen. The rule:

- If the swallowed token **starts with** closing/joining punctuation (`,` `.` `;` `:`
  `)` `]` `%` `'` `’` `"` `”` `!` `?`) **or the predecessor ends with an opening token**
  (e.g. `$`), join with **no space**: `"$1" + ",000" + ",000."` → `"$1,000,000."`.
- Otherwise (a normal word fragment), join with a **single space**.

`endMs` of the merged result = the swallowed token's `endMs` (extend forward); the
swallowed entry is removed from the array.

## Rule catalog

| # | Defect (playbook ref) | Severity | Detect | Auto-fix |
|---|---|---|---|---|
| 1 | Split-number / orphan-punct caption (CH1.1) | CRITICAL | token matches `^[,.]` or is `[,.]?\d+[,.]?` fragment with no letters and a leading/trailing comma/period that belongs to a neighbour | merge text into previous caption word, extend its `endMs` |
| 2 | Stray standalone punctuation token (`,` `.` `—`) | CRITICAL | token is punctuation-only | merge into previous |
| 3 | Filler token `um/uh/ah` (CH1.3) | WARN | normalized token in filler set | drop, close the gap |
| 4 | Non-monotonic / overlapping captions (CH2.1) | CRITICAL | `caps[i].startMs < caps[i-1].endMs` | clamp `start = prev.end` |
| 5 | Zero / negative-duration caption | CRITICAL | `endMs <= startMs` | give min 1-frame duration (`round(1000/fps)`); merge if it is an orphan-punct from #1/#2 |
| 6 | Off-frame-grid timestamps (CH2.2) | WARN | `startMs`/`endMs` not a multiple of `1000/fps` | snap to nearest frame |
| 7 | Caption past audio end (Whisper ghost token) | CRITICAL | `endMs > narrationMs + tol` | **drop** if fully after audio (`startMs > narrationMs + tol`); **clamp** `endMs = narrationMs` only if it straddles the boundary (`startMs <= narrationMs`) |
| 8 | Headline overlap | CRITICAL | `chapters[i].startMs < chapters[i-1].endMs` | clamp |
| 9 | Stuck headline ("dead-air ghosting", CH2.3) | WARN | duration > `QC_MAX_HEADLINE_S` | flag only |
| 10 | Duplicate adjacent headline text | CRITICAL | normalized text equal to previous | merge spans |
| 11 | Glued / oversize caption token | WARN | token length > `QC_MAX_CAPTION_TOKEN_CHARS` (~25) | flag only |
| 12 | Structural | CRITICAL | empty `captions`/`chapters`, missing `audioSrc`/`narrationMs` | none — block |

### Fixer ordering

The single fix pass applies fixers in a fixed order so they compose without creating
new defects: **(7) drop ghost tokens → (1,2) merge orphan-punct → (5) min-duration →
(4) monotonic clamp → (6) frame-snap** for captions, then **(10) dedup → (8) clamp** for
headlines. Rationale: dropping fully-after-audio ghost tokens *before* any clamp avoids
manufacturing a negative-duration token (the exact trap in gap #2); frame-snap runs last
so its rounding can't re-introduce a sub-millisecond overlap. The re-verify pass is the
backstop — if any ordering interaction still leaves a CRITICAL defect, it blocks.

### Boundaries (explicitly NOT pre-flight-linted)

- **CH3** (3-words/18-char Shorts blocks, 7-words/line long-form, orphan-wrap) — the
  Remotion component groups word-level caption tokens into on-screen blocks at render
  time. `props.json` holds individual words, so block-level rules are not checkable
  here beyond the single oversize-token check (#11). Documented as a known limit.
- **CH4** (safe-zones, descender padding, karaoke active-word highlight) — Remotion
  layout/render concerns.
- **CH5** (sidechain ducking, EBU R128 loudnorm, CFR transcoding) — post-render audio
  mastering. Deferred to a `qc.py` follow-up.
- **CH6** (FFmpeg `drawtext` escaping, Docker font sandboxing) — not our stack.

## Config (new constants in `engine/config.py`)

Follow existing `QC_*` naming:

- `QC_MAX_HEADLINE_S` — stuck-headline threshold (default e.g. `70.0`; Len Bias chapters
  run ~40–55s, so the default flags only genuine outliers).
- `QC_MAX_CAPTION_TOKEN_CHARS` — oversize-token threshold (default `25`).
- `QC_CAPTION_END_TOL_MS` — past-audio-end tolerance (default e.g. `500`).
- `QC_FILLER_WORDS` — filler set (`um`, `uh`, `ah`, `er`).

Frame duration is derived from `props["fps"]`, not a constant.

## Integration

### `run_video.py` (the gate)

Between props.json write (line 123) and render (line 140):

1. `fixed, report = preflight.lint_props(props, fps, narration_ms)`.
2. Write `fixed` back to `props.json`; write `report` to
   `produced/<id>/<fmt>/qc_lint.json`.
3. If `report["blocked"]`: set idea status `needs_review` (`q.update_idea`), print the
   failing CRITICAL checks, and **return without rendering**.
4. Otherwise: print a one-line summary (`✓ pre-flight QC: N auto-fixed, M warnings`),
   render proceeds with the corrected props.

#### SRT regeneration (orchestrator, not linter)

The linter does **not** touch `captions.srt`. After step 2, `run_video.py` regenerates
the SRT from `fixed["captions"]` so the two artifacts can't diverge — using the existing
caption pipeline, not new code in `preflight.py`. Because `props["captions"]` is
word-level `{text, startMs, endMs}` and the SRT helpers expect `{word, start, end}` (in
seconds), `run_video.py` applies a tiny adapter, then reuses
`captions.chunk_words_to_captions(...)` → `captions.to_srt(...)`. This keeps the
word→line grouping in one place and preserves the "linter is a pure transform"
constraint.

### New CLI `python3 -m engine.run_preflight --id <id> [--format long|short] [--fix]`

Parallels `run_factcheck`. Operates on an existing `props.json` (build it without
`--render`): lints, prints the report, writes `qc_lint.json`. With `--fix`, rewrites
`props.json` + `captions.srt`. **Exits non-zero unless clean** (no unfixed CRITICAL).
Pure stdlib → runs under `python3` (main env), no render venv needed.

### Skill + docs

- New `.claude/skills/preflight-qc/` wrapping `run_preflight`.
- CLAUDE.md: add `run_preflight` to **Entrypoints**, add the skill to the **Skills**
  table, and add a one-line rule under **Gate discipline** ("a render is blocked if the
  pre-flight QC lint finds an unfixed CRITICAL defect").

## Testing (TDD)

- One unit test per fixer with synthetic props: split-number, stray-punct, overlap,
  zero/negative duration, frame-snap, headline overlap, duplicate headline, stuck
  headline, past-audio-end, structural-empty.
- **Golden regression fixture from Len Bias's real `props.json`**
  (`produced/af86c186/long/video/props.json`, captured as a trimmed test fixture):
  feed it through `lint_props` and assert the `,000`/`,000.` tokens merge into a single
  `$1,000,000` caption word and the zero-duration token is gone.
- **No-space merge** — `["$1", ",000", ",000."]` → single `"$1,000,000."` token (not
  `"$1 ,000 ,000."`); a normal-word merge case asserts a space *is* inserted.
- **Ghost-token drop vs clamp** — a token fully after `narrationMs+tol` is dropped (and
  does not become negative-duration); a token straddling the boundary is clamped to
  `narrationMs`.
- **Mutations log** — assert the report's `mutations` array records the merge with
  `from`/`into`, the drop with `reason`, and a retime with `from`/`to` ms.
- Re-verify pass: a synthetic case where the first fix creates a new overlap proves the
  re-verify catches/fixes or blocks correctly.
- The PostToolUse hook runs `python3 -m pytest tests/ -q` automatically after engine
  edits (the contract).

## Out of scope / follow-ups

- Post-render audio QC (CH5: loudness band, ducking sanity, CFR) — separate PR on
  `qc.py`.
- Linting `bBeats` (b-roll beat coverage/gaps) — possible later addition.
- Wiring the lint into `run_auto`'s status reporting beyond the `needs_review` flag.
