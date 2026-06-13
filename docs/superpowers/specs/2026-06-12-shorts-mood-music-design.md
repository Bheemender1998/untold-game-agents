# Shorts mood-matched background music — design

**Date:** 2026-06-12
**Status:** approved approach (A), pending spec review
**Scope:** YouTube Shorts only (`UntoldShort.tsx` / `--format short`). Long-form
(`UntoldVideo.tsx`) is unchanged.

## Problem

51 music tracks were dropped unsorted into `engine/video/music/music_all/`. The four
mood folders (`tense/`, `triumphant/`, `somber/`, `hype/`) are empty, and **no code selects
or mixes music** — `props.json` has no music field, `UntoldShort.tsx` has no background
`<Audio>`, and there is no `manifest.json` generator. The README describes the intended
system; this spec implements it. End state: each rendered Short carries a mood-matched
background bed mixed low under the narration, with license attribution tracked.

## Mood vocabulary (fixed)

The four moods are already canonical across the engine (`config._SHORT_MOODS`,
`NARRATION_VOICE_BY_MOOD`, `PILLAR_MOOD`): **`tense`, `triumphant`, `somber`, `hype`**.
The music folders reuse exactly these names. Every produced idea already carries a `mood`
(set in `run_produce` from the script `MOOD:` line, else derived from the pillar).

## Architecture (Approach A — manifest-driven)

Three small, isolated units:

### 1. `engine/video/music.py` (new)

Pure-Python selection module. No Remotion/Node dependency.

- `build_manifest() -> dict` — scan `music/<mood>/*.{mp3,wav}`, write `music/manifest.json`
  as `{mood: [{"file": "<mood>/<name>.mp3", "attribution": "<str or empty>"}]}`. Attribution
  is read from an optional `music/attribution.json` (`{filename: credit}`); files not listed
  default to `""` (assumed royalty-free / CC0). Idempotent — safe to regenerate any time.
- `pick_track(mood: str, seed: str) -> dict | None` — return a deterministic
  `{"path": <abs>, "attribution": <str>}` for `mood`, chosen by hashing `seed` (the idea id)
  over the sorted track list so a given idea always gets the same bed and the library rotates
  across ideas. Returns `None` when the mood is unknown/empty (caller renders silent).
  Reads the manifest, regenerating it if missing.

**Why a manifest, not a raw glob:** it carries per-track `attribution`, which several tracks
legally require (CC-BY). A glob would lose that and risk uncredited use.

### 2. `engine/video/remotion_build.py` (edit `build_props`)

- Read `idea.get("mood")` (already on the idea).
- Call `music.pick_track(mood, seed=idea["id"])`. Only wire music for shorts
  (`portrait=True`); long-form passes no music.
- On a hit: add `props["musicSrc"] = os.path.basename(path)`, `props["musicVolume"] = 0.12`,
  append `path` to `assets` (staged into `public/` by the existing `_stage_assets`, which
  already clears stale `*.mp3`). `build_props` changes its return from `(props, assets)` to
  `(props, assets, music_credit)`, where `music_credit` is the chosen track's attribution
  string (`""` when none). The caller writes it — see §4.
- On `None`: omit the music props entirely → composition renders silent. No crash
  (self-stub rule).

### 3. `engine/video/remotion/src/UntoldShort.tsx` (+ `types.ts`)

- Add optional `musicSrc?: string` and `musicVolume?: number` to `ShortProps` (`types.ts`).
- When `musicSrc` is present, render a background bed:
  `<Audio src={staticFile(props.musicSrc)} volume={fade} loop />` mixed under the existing
  narration `<Audio>`. `fade` ramps 0 → `musicVolume` over the first ~1.5 s and
  `musicVolume` → 0 over the last ~2.5 s (interpolate on `useCurrentFrame()`), so the bed
  lifts in under the intro and ducks out under the outro. Narration volume is unchanged.
- `loop` covers the (unlikely) case of a bed shorter than a 30–50 s short. The existing
  impact-SFX `<Audio>` layer is untouched.

### 4. Attribution surfacing

The caller of `build_props` (the narrated-Remotion short branch in `run_video.py`) receives
`music_credit`. When it is non-empty, it writes the credit to
`produced/<id>/video/music_credit.txt` and appends a `Music: <attribution>` line to the idea's
`metadata.json` description (idempotent — guarded so re-renders don't duplicate it). This keeps
CC-BY credit attached to the video for the Stage 2 publish step. Empty credit writes nothing.
`build_manifest`/`pick_track` themselves never touch metadata — selection and surfacing stay
separated.

## Track triage (sorting the 51)

Sorting is **curation, not a bulk move** — the library mixes cinematic beds with comedic /
kids / relaxation tracks that do not fit a serious sports-history doc. Off-tone tracks stay
out of the mood folders (moved to `music/_unused/`) so `pick_track` never surfaces them.

Proposed mapping (best-effort by filename/known source — **for your review; I can't hear them,
so correct any you disagree with before I move files**):

**somber/** — loss, aftermath, walking away
- paulyudin-sad-sad-music-508961, paulyudin-sad-sad-music-485935
- leberch-sad-piano-music-501447, leberch-sad-piano-501483, mondamusic-sad-piano-529575
- Evening, Southern Gothic

**tense/** — investigation, scandal, dark build-up
- universfield-dark-wave-cinematic-background-30s, alexgrohl-dark-mystery-trailer-taking-our-time
- leberch-dark-cinematic-thriller-249485, leberch-dark-510496, leberch-dark-cinematic-509801
- tunetank-cinematic-dark-mysterious-music-412770, alexzavesa-cinematic-dramatic-11120

**triumphant/** — vindication, redemption, emotional payoff
- joyinsound-inspiring-inspirational, leberch-inspiring-516867, leberch-inspiring-511351
- tunetank-inspiring-cinematic-music, jonasblakewood-inspiring, the_mountain-inspiring-483307
- music_for_videos-inspiring-emotional-uplifting-piano, stereo_color-inspiring-cinematic-trailer

**hype/** — fast montage intros, high-energy reveals, what-ifs
- paulyudin-epic-epic-music, the_mountain-epic-483805, good_b_music-epic-hollywood-trailer
- nastelbom-trailer-cinematic, the_mountain-cinematic-489998, lexin_music-cinematic-time-lapse

**_unused/** — off-tone for the channel (comedic, kids/dino, relaxation, sci-fi novelty)
- Lord of the Rangs, Goblin_Tinker_Soldier_Spy, Sergio's Magic Dustbin, Galactic Rap,
  Adventures in Adventureland, Boogie Party, I Got a Stick (x2), Magic Escape Room,
  That Zen Moment, Ethereal Relaxation, Vibing Over Venus, Paradise_Found, Morning,
  Mesmerizing Galaxy Loop, Brain Dance, Cloud Dancer, Journey To Ascend, Sauropod Spotting,
  Equatorial Complex, Cretaceous Dawn, Dentaneosuchus Hunt,
  vasilyatsevich-brain-implant-cyberpunk-sci-fi-trailer

The top-level empty `engine/music_all/` directory (separate from `engine/video/music/music_all/`)
is removed.

## Error handling

- Empty/missing mood folder, unknown mood, or missing manifest → `pick_track` returns `None`
  → silent render, no error (self-stub rule, like missing b-roll).
- A staged file that fails to copy is caught and treated as no-music for that render.

## Testing (`python3 -m pytest tests/`, main env)

- `build_manifest` produces the expected `{mood: [...]}` shape from a temp folder tree;
  attribution map is applied; files outside the four moods are ignored.
- `pick_track` is deterministic for a fixed seed, rotates across distinct seeds, and returns
  `None` for an empty/unknown mood.
- `build_props` adds `musicSrc`/`musicVolume` + the staged asset for a short with a mood, and
  omits all music props for long-form (`portrait=False`) and for a mood with no tracks.
- Attribution append to `metadata.json` is idempotent across repeated renders.
- Remotion TSX change is verified via a still-preview render (no audio) + one real short render
  out-of-band; the 45-min render is never a CI gate.

## Out of scope (YAGNI)

- Long-form background music, per-chapter music changes, crossfades between beds, loudness
  normalization, a music-picker UI, and auto-downloading more tracks. None are needed to make
  mood-matched Shorts music work.
