# Title-card impact SFX — design

**Date:** 2026-06-12
**Status:** approved (design); pending implementation plan
**Scope:** Add a single soft low-end "impact" sound that lands as each title card springs in.

## Problem

Our videos (faceless sports-history documentaries rendered in Remotion) mix a **single
narration track** — `UntoldVideo.tsx` plays `<Audio src={staticFile(props.audioSrc)} />` and
nothing else. The title cards (intro title + per-chapter headlines) spring in silently. A
restrained low boom under each title gives those beats weight, the way a documentary punctuates
a chapter card. This is explicitly **not** the fast-cut whoosh/swish style (ruled out as wrong
for a slow documentary tone) — it is one felt, sub-heavy hit.

We evaluated a paid DaVinci Resolve transitions pack (Envato, $33) and rejected it: it is a
Resolve/Fusion template that cannot run in our Remotion (code) render path, and its bundled
SFX are licensed as part of the template, not as standalone assets.

## Goal / success criteria

- A single low impact plays as the **intro title** lands and as **each chapter headline** lands.
- It sits *under* the narration — felt, not distracting; never masks a spoken word.
- Fully owned / CC0: synthesized, no external sample to license.
- Reproducible: the synthesis is a committed script, not a one-off binary of unknown origin.
- Renders deterministically (Remotion mixes the audio at render; previews in Studio too).

## Non-goals (YAGNI)

- No per-chapter different sounds; one impact, reused everywhere.
- No per-mood SFX variants (the TTS mood config is separate; revisit only if it earns it).
- No music bed (the empty `engine/video/music/` scaffold is a separate future project).
- No whoosh/transition SFX, no caption-level hits.

## Decisions

- **Chosen sound:** the **`weighty`** variant — ~110→40 Hz down-sweep + a sub-octave for body
  and a subtle echo tail, ~1.0s, slow decay. (Auditioned against `soft` and `tight`.) It is
  intentionally lower-peak than the others because the sub + echo spread the energy, so it is
  **level-matched (peak-normalized) on install** before being wired in.
- **Placement:** intro title card + every chapter card. (Not the outro/subscribe card — keeping
  it to title reveals, not the closer.)
- **Mixing location:** inside Remotion via `<Audio>` per card, not a post-render ffmpeg overlay.
  Declarative, frame-synced to the existing card sequences, and avoids recomputing chapter
  timings in a brittle second step.

## Design

### 1. Synthesis — `engine/video/make_impact_sfx.sh` (already written)

ffmpeg `aevalsrc` chirp with an exponential-decay envelope:

- `phase(t) = 2*PI*(f0*t + (f1-f0)/(2*d) * t^2)` → instantaneous freq glides `f0 → f1` over `d`.
- `amp(t) = exp(-k*t)` → the boom tail. A short `afade` out kills the end click.
- `weighty` adds a sub octave term and an `aecho` tail; output stereo, 48 kHz, `pcm_s16le`.

The script writes auditions to `engine/video/sfx_auditions/impact_{soft,weighty,tight}.wav`, and
`make_impact_sfx.sh weighty` installs the chosen variant to the composition's public dir.

**Open refinement:** on install, the chosen variant is peak-normalized (e.g. to ≈ −1 dBFS) so
its loudness is predictable relative to the narration. (The raw `weighty` peaks ≈ −10 dB.)

### 2. Asset location

Install the chosen sound to `engine/video/remotion/public/sfx/impact.wav` and **commit it** as a
permanent asset (like the fonts), so it is referenced via `staticFile('sfx/impact.wav')`.

**Risk to verify in the plan:** confirm the produce pipeline does not wipe/regenerate
`public/` per render (which would delete `sfx/impact.wav`). If it does, the impact must be copied
in alongside `narration.wav`/b-roll during build, or live in a preserved location.

### 3. Wiring — `engine/video/remotion/src/UntoldVideo.tsx`

- Add a tunable constant `IMPACT_VOL` (start ≈ `0.4`).
- Intro hit: a `<Sequence from={0}>` containing `<Audio src={staticFile('sfx/impact.wav')}
  volume={IMPACT_VOL} />` so the boom lands as the intro title springs in.
- Chapter hits: for each chapter, a `<Sequence from={introF + ms2f(c.startMs, fps)}>` with the
  same `<Audio>` — the existing `ChapterCard` already starts on that same frame, so the hit is
  synced to the headline reveal (and the gold accent rule).
- No `types.ts` change — the path is constant across all videos.

### 4. Verification

- `bash -n make_impact_sfx.sh` and a regenerate run produce three non-clipping wavs (done).
- After wiring, render a short segment covering intro + first chapter
  (`remotion render … --frames=0-270`, ≈ 9 s) using the real `narration.wav` in `public/`.
- `ffprobe` confirms the output has an audio stream; **the user plays the clip** to judge whether
  the impact sits right under the voice, then we tune `IMPACT_VOL`.
- `python3 -m pytest tests/ -q` must stay green (no Python touched, but the contract holds).

## Files touched

- **New:** `engine/video/make_impact_sfx.sh` (synth + install; already written).
- **New:** `engine/video/remotion/public/sfx/impact.wav` (committed asset).
- **Edit:** `engine/video/remotion/src/UntoldVideo.tsx` (IMPACT_VOL + intro/chapter `<Audio>`).
- Auditions in `engine/video/sfx_auditions/` are throwaway previews — left untracked (not
  committed); regenerate with `make_impact_sfx.sh` when needed.

## Ship

`engine/video/**` change → ship via the `ship-video-change` rail (branch, pytest, dual
adversarial review, PR with review trailer). The 45-min full render is never a gate; the short
audio segment + the user's ear are the check.
