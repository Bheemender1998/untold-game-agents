# Short-form pacing + mood-driven b-roll variety — design

**Date:** 2026-06-13
**Status:** approved (brainstorm) → writing-plans next
**Slice:** 1 of 2 (SFX layer is Slice 2, out of scope here)

## Problem

After a full end-to-end re-test of the post-changes pipeline (Cantona short, idea
`25051da8`), the rendered short still reads like a slow audiobook over a near-static
background, not a scroll-stopping vertical clip:

- **Hook is atmosphere, not conflict.** It opens *"He was a king in exile — and the
  throne was supposed to go cold…"* The viewer has ~2 seconds on TikTok / Reels before a
  swipe; the payoff/mystery must land in the first line, not after a mood-setting clause.
- **Pacing is calm.** Narration runs at the long-form `NARRATION_SPEED = 0.9` with
  `NARRATION_GAP_S = 0.5` dramatic pauses — correct for a 30-for-30 long, wrong for a short.
- **One clip per chapter loops.** `Background.tsx` renders a single b-roll clip per chapter
  (~7 clips over ~52s, ~7s each, static cover + loop). It feels like one repeating clip
  under a voiceover — the "audiobook" feel — on **both** shorts and longs.

This builds on `2026-06-13-frontloaded-hooks-withholding-titles-design.md` (shipped) and
revises `2026-06-12-sport-relevant-broll-design.md` (the per-chapter symbolic-query model).

## Decisions (locked in brainstorm)

1. **Integrity held.** The punch comes from *structure* (conflict-first, withhold specifics),
   *pacing*, and *visual rhythm* — NOT from loosening the fact gate. Exact numbers only (never
   round), no unverified superlatives (attributed/"of his generation" is allowed). Preserves the
   channel's "every claim verified" differentiator (ADR-0005).
2. **Two slices.** Slice 1 (this spec): hook + pacing + visual rhythm + clip variety, no new
   assets. Slice 2 (later): SFX / whoosh / impact layer (needs a licensed sound library).
3. **Mood-driven atmospheric clips.** Broad atmospheric footage (nature / sky / space / weather /
   texture) selected by the story's **mood**, so it stays emotionally coherent while being varied.
   Purely abstract → zero integrity risk (no implication of real event footage).
4. **No single-clip loop, on BOTH formats.** A *new* deduped clip every beat.
5. **Cadence differs by format.** Short → a new clip every **~2.5s** (TikTok energy).
   Long → every **~7s** (cinematic; rapid cuts would fight the documentary tone). The
   no-single-loop variety applies to both; the fast rhythm is shorts-only.

## Scope

In scope (Slice 1):

| # | Surface | Change |
|---|---------|--------|
| A | `engine/pipeline/script.py` | Sharpen `SHORT_SYSTEM` + `DERIVE_TEASE_SYSTEM` hook rules |
| B | `engine/config.py`, `engine/video/tts.py` | Short-only narration speed + sentence gap |
| C | `engine/config.py`, `engine/video/footage.py`, `engine/video/remotion_build.py`, `engine/video/remotion/src/components/Background.tsx`, `types.ts` | Mood pool + beat track + Ken-Burns zoom |
| D | `engine/video/remotion/src/components/ShortCaptions.tsx` | Caption punch-in (shorts only) |

Out of scope: SFX/audio-mix (Slice 2); changing long-form narration pace; changing the
fact gate; topical/literal b-roll; long-form caption animation.

## Design

### A. Hook (script prompt)

`SHORT_SYSTEM` and `DERIVE_TEASE_SYSTEM` HOOK beat, tightened:

- The **first line** must establish the central conflict or mystery in **≤ 8 words**,
  payoff-forward (e.g. *"The greatest runner of his generation just vanished."*).
- Explicit ban on atmosphere / scene-setting openers ("He was a king in exile…", "It was a
  cold night…"). No throat-clearing, no "in this video".
- Specifics (the exact number, the full name, the date) land in the **FACT** beat, 1–2s later
  — never in the hook.
- Integrity rules unchanged: exact verified values only, never round; superlatives must be
  attributed or defensibly true.

No code/structure change beyond prompt text; the existing `_parse_short` / `_trim_preamble`
path is untouched.

### B. Pacing (short-only)

New config knobs, long-form values untouched:

```python
SHORT_NARRATION_SPEED = 1.12   # brisk but still clear (vs long-form 0.9)
SHORT_NARRATION_GAP_S  = 0.12  # near-eliminate dramatic pauses (vs 0.5)
```

`tts.py` narrate-path for shorts passes these through (the call site already accepts
`speed` / `gap_s` overrides — `synth(..., speed=, gap_s=)`). The short render path
(`run_video --format short` and the companion-short path in `run_auto`) selects the
short values; the long path keeps `NARRATION_SPEED` / `NARRATION_GAP_S`.

1.12 is a deliberate first value — clear over chipmunky. We eyeball the re-render and can
push toward 1.2+ if it reads too slow. Captions are whisper-synced to the *rendered*
narration, so they stay aligned automatically.

### C. Visual rhythm — mood pool + beat track + zoom

**C1. Mood → atmospheric pool (`config.py`).** A curated, deterministic table:

```python
MOOD_BROLL_POOL = {
    "somber":     ["rain window", "grey ocean", "dusk fog", "empty road night",
                   "falling snow", "still lake mist", ...],
    "triumphant": ["sunrise clouds", "light rays forest", "open sky", "mountain summit",
                   "golden hour ocean", "soaring birds", ...],
    "tense":      ["storm clouds timelapse", "lightning", "crashing waves", "dark smoke",
                   "fast clouds", "flickering light", ...],
    "hype":       ["city lights night", "neon motion", "fireworks", "traffic timelapse",
                   "fast highway", "energy abstract", ...],
}
```

Each pool has enough terms (≥ 6) that beat-level selection + the existing global
`used_clips.json` dedup yields a fresh clip per beat without immediate repeats.
Determinism (no per-beat LLM call) makes renders repeatable and cheaper — consistent with
the project's determinism preference (e.g. banner). This **replaces** the per-chapter
Claude-written symbolic query for b-roll selection; the sport-keyword prepend
(`_sport_query`) is dropped for the atmospheric pool (we are intentionally generic now).

**C2. Beat track (`remotion_build.py`).** Compute a b-roll beat track from the narration
duration, independent of chapter cards:

- `beat_len = SHORT_BROLL_BEAT_S (2.5)` for short, `LONG_BROLL_BEAT_S (7.0)` for long.
- `n_beats = ceil(narrationMs / beat_len)`; each beat gets `{startMs, endMs}`.
- For each beat, select a mood-pool term (mood from the short's `MOOD:` line; for long,
  the pillar-derived mood) and fetch one deduped clip via `footage.fetch_clips`.
- Emit a new props field `bBeats: [{src, startMs, endMs, zoomDir}]` where `zoomDir`
  alternates `in`/`out` per beat.

Chapter cards (long) and captions are **unchanged** in timing — only the background track
gets finer. Back-compat (resolved): the per-chapter `bClip` field stays in the schema, and
`Background` **prefers `bBeats` when present and non-empty, else falls back to the per-chapter
`bClip` path**. The new `remotion_build` path populates `bBeats`; nothing else needs to change
at once.

**C3. Ken-Burns zoom + hard cut (`Background.tsx`, `types.ts`).** Background renders the
`bBeats` track: each beat is a `Sequence(from=startMs, dur=beatLen)` with a hard cut at the
boundary (a very short ~3-frame crossfade to avoid a black flash, not the current 12-frame
fade), and a slow scale interpolation `1.0 → 1.08` (or `1.08 → 1.0` when `zoomDir==="out"`)
across the beat. The gradient field + scrim/vignette layers are untouched.

### D. Caption punch-in (shorts only)

`ShortCaptions.tsx`: each caption group enters with a spring scale (≈ `0.92 → 1.0`) + quick
opacity ramp over ~6 frames, so the *text itself* is a pattern interrupt on every change.
Long-form `Captions.tsx` is untouched (keeps the calm documentary feel).

## Data flow

```
idea ──run_produce──> script.md (sharper hook)  +  MOOD
                          │
run_video --format short  ▼
   tts.synth(speed=SHORT_NARRATION_SPEED, gap_s=SHORT_NARRATION_GAP_S) ──> narration.wav
   whisper ──> word-synced captions
   remotion_build:
       beats = beat_track(narrationMs, beat_len=2.5)        # long: 7.0
       for beat: term = pick(MOOD_BROLL_POOL[mood]); clip = fetch_clips(...)  # deduped
       props.bBeats = [{src,startMs,endMs,zoomDir}, ...]
                          │
   Remotion render ▼
       Background: bBeats → hard-cut + Ken-Burns zoom
       ShortCaptions: punch-in
   ──> video.mp4  ──> QC
```

## Error handling / self-stub (unchanged discipline)

- `footage.fetch_clips` already self-stubs: a beat with no available clip → the gradient
  field shows through (never black, never a crash). Pexels rate-limit / no-key → fewer beats
  have footage, render still succeeds.
- If `MOOD` is missing/invalid, fall back to the pillar-derived mood (existing
  `mood_for_pillar`); if that's empty, default pool = `"tense"`.
- A beat track that exceeds available unique clips falls back to the dedup's "broaden query /
  allow repeat" path already in `_fetch_one`.

## Testing

`python3 -m pytest tests/ -q` is the contract (PostToolUse hook runs it). New/updated tests:

- `script.py`: hook-prompt unit — the system prompt contains the ≤8-word / no-atmosphere
  / specifics-in-FACT rules (string assertions on the constant, as existing prompt tests do).
- `config.py`/`tts.py`: short path uses `SHORT_NARRATION_SPEED`/`SHORT_NARRATION_GAP_S`;
  long path unchanged — assert the resolved values per format.
- `remotion_build.py`: `beat_track` produces `ceil(dur/beat_len)` beats with contiguous
  non-overlapping `[startMs,endMs)` covering the narration; short uses 2.5s, long 7.0s;
  `zoomDir` alternates; each beat has a clip src or is gracefully empty.
- `footage.py`: mood-pool selection returns a term from the right pool; missing/invalid mood
  falls back; dedup still honored.
- Render is **never** a test gate (45-min Remotion). Proof = re-render Cantona + QC + eyeball.

## Proof of value

Re-produce + re-render the Cantona short (`25051da8`) as a short, run QC, and eyeball it
against the current baseline render. Expected: conflict-first hook in ~2s, brisk delivery,
a new atmospheric clip every ~2.5s with motion, punch-in captions. The b-roll-variety code
path is shared with long-form, so a long re-render is optional (covered by the same code).

## Slice 2 (noted, not built here)

SFX layer: a licensed/royalty-free sound library (whoosh on cut, impact on hook), an audio
mix track in the Remotion composition, and config for SFX volume. Separate spec when Slice 1
is proven. (Supersedes the older `2026-06-12-title-impact-sfx-design.md` framing.)
