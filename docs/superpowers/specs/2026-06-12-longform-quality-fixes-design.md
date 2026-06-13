# Long-form Render Quality Fixes — Design

**Date:** 2026-06-12
**Status:** Approved (pending spec review)
**Author:** session 11

## Problem

The first long-form render (Senna, `0c76c4c4`, ~10.5 min) was reviewed and shipped
to YouTube as-is, but the user flagged five template-quality issues that recur in
every long render. They must be fixed before producing/rendering the other four
longs (World Cup `46dbfcda`, O.J. `0eaa1b66`, Barry `5b98b1fc`, Sachin `a31759e2`),
so those four come out clean the first time.

Observed issues (root-caused in the pipeline):

1. **B-roll loops one clip** — the video repeats one clip instead of cycling the
   12 distinct downloaded clips.
2. **Years spoken/spelled wrong** — "1984" is narrated as "nineteen hundred eighty
   four" (should be "nineteen eighty-four") and captions show the spelled-out words
   instead of digits.
3. **Player-name mispronunciation** — foreign names are guessed by espeak.
4. **Caption desync at chapter titles** — captions are suppressed for the ~3.6 s
   title-card window, so words spoken then are skipped, then "catch up".
5. **Music too loud** relative to the narrator.

Liked (do not change): the watermark and the ending.

## Goal

Fix all five in the video pipeline so the other four longs render cleanly. Senna is
**not** re-rendered.

## Non-goals

- Re-rendering the Senna long (it shipped as-is by user decision).
- Full forced-alignment / script-aligned captions (a more robust caption-text
  architecture). Deferred — we take the minimal targeted approach now and iterate
  later if the post-processors prove fragile.
- Changing the watermark or ending.

## Decisions (locked during brainstorming)

- **Caption sync (Bug 4):** show captions *during* the title card; reposition the
  card so it doesn't collide with the bottom caption band. No audio re-timing.
- **Number display (Bug 2):** captions show **digits** ("1984"), via a caption
  post-processor (not full alignment).
- **Approach:** minimal, targeted fixes now ("make changes and improve as we go").

## Root causes (from investigation)

| Bug | Root cause | File |
|-----|-----------|------|
| 1 b-roll | Pexels `per_page=12`; dedup fallback (`footage.py` ~119-122) reuses clips once the small pool is exhausted; `used_clips.json` poisons the pool across renders | `engine/video/footage.py` |
| 2 years | `_spell_grouped_numbers` only matches comma-grouped numbers; bare `1984` passes to espeak → "nineteen hundred…"; captions inherit it (whisper transcribes the audio) | `engine/video/tts.py`, `engine/video/captions.py` |
| 3 names | No pronunciation map; espeak guesses foreign names | `engine/video/tts.py` |
| 4 caption sync | `Captions.tsx` returns `null` while `nowMs` is within `CHAPTER_HEADLINE_MS` (3600 ms) of a chapter start → words skipped | `engine/video/remotion/src/components/Captions.tsx`, `ChapterCard.tsx` |
| 5 music | `MUSIC_VOLUME = 0.12` (and TSX `?? 0.12` fallback) | `engine/video/music.py`, `engine/video/remotion/src/UntoldVideo.tsx` |

## Design

### Fix 1 — B-roll variety (`engine/video/footage.py`)
- Raise the Pexels `per_page` from 12 to ~40 so each query returns a larger unique
  pool.
- Change the dedup fallback so that when the per-video pool is thin, it issues a
  **broader/alternate query** before ever repeating a clip, and prioritizes
  **within-video distinctness** (every chapter a different clip) over cross-video
  dedup.
- Ensure `used_clips.json` cross-render accumulation cannot force within-video
  repeats (e.g., the within-video exclusion set is authoritative for distinctness;
  if the global set blocks all candidates, fall back to "unused in THIS video"
  rather than repeating a clip already used in this video).
- Remotion `Background.tsx` already renders a distinct clip per chapter — no TSX
  change needed; the fix is purely in clip selection.

### Fix 5 — Music level (`engine/video/music.py` + TSX)
- Lower `MUSIC_VOLUME` 0.12 → **0.08** in `music.py` (the single source of truth).
- Update the `UntoldVideo.tsx` fallback `props.musicVolume ?? 0.12` → `?? 0.08` so
  a missing prop can't revert to the louder level.

### Fix 4 — Captions during title cards (Remotion)
- In `Captions.tsx`, remove the `inHeadline` suppression so caption pages render
  during the title-card window (narration and captions stay in sync; no words
  skipped).
- In `ChapterCard.tsx` (and/or `UntoldVideo.tsx` layout), position the title card in
  the **upper third** so it does not overlap the bottom caption band. Verify via a
  still-frame preview at a chapter boundary (`npx remotion still ... --frame=N`).

### Fix 2 — Years/numbers: correct audio + digit captions
- **Audio (`tts.py`):** add a year/number normalizer that converts bare 4-digit
  years (range ~1000–2099) to the paired-decades word form ("nineteen eighty-four",
  "twenty oh-three"/"two thousand three" as appropriate) **before** the text reaches
  kokoro/espeak, so the narration says them correctly. Keep the existing
  comma-grouped handling.
- **Captions (`captions.py`):** add a conservative `digitize_number_words(words)`
  post-processor that runs on the Whisper word list and collapses recognized
  spoken-number runs (years and common forms) back into a single **digit** token,
  merging the run's start/end timings. Conservative: only collapse high-confidence
  patterns; leave anything ambiguous as words (graceful fallback). Result: captions
  display "1984".

### Fix 3 — Name pronunciation (`engine/video/tts.py`)
- Add a seedable pronunciation map (name → phonetic respelling) applied to the
  **narration text only** (the text fed to TTS), seeded with the foreign names in
  the current scripts (e.g., Senna, Prost, Ickx, Balestre, Bellof, Lauda, Mansell,
  Tendulkar — extended per topic).
- Do **not** apply the respelling to the caption glossary: `captions.proper_nouns`
  continues to feed the **canonical** names as the Whisper `initial_prompt`, so
  correct audio + glossary bias yields correct caption spelling without a brittle
  restore step.

## Error handling / conventions
- Self-stub / never crash the render (existing convention). A name not in the map
  simply isn't respelled; an unparseable number run stays as words.
- Render is never a gate (CLAUDE.md); verify via `pytest tests/` + still-frame
  preview + the QC gate.
- Integrity gate: these are presentation/pronunciation fixes; they do not introduce
  unverified claims or fabricate footage.

## Testing (`pytest tests/`, python3 main env)
- `tts.py`: year normalizer — `1984`→"nineteen eighty-four", `2003`→correct form,
  `1973`→"nineteen seventy-three"; non-years (scores, counts) unaffected; existing
  comma-grouped tests still pass.
- `tts.py`: pronunciation map applied to narration text; canonical names untouched
  in the glossary path.
- `captions.py`: `digitize_number_words` collapses "nineteen eighty-four"→"1984"
  (timing merged), "two thousand three"→"2003"; leaves ambiguous runs as words;
  preserves token timing contract.
- `footage.py`: within-video distinctness — given a small Pexels pool, selection
  does not repeat a clip already used in the same video while distinct candidates
  remain (mock the Pexels search).
- `music.py`: `MUSIC_VOLUME == 0.08`.
- Remotion `Captions.tsx`: existing TSX type-checks compile (`tsc`); manual still
  preview for the title-card layout (not a pytest gate).

## The four longs to render after the fixes ship
World Cup `46dbfcda` · O.J. `0eaa1b66` · Barry `5b98b1fc` · Sachin `a31759e2`
(produce `--format long` → fact-review → render → upload unlisted → back-link the
five shorts). This is the resumption of the Phase-1 runbook, now on the fixed
template.
