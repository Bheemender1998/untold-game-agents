# Branding & profile polish — design

**Date:** 2026-06-12
**Status:** approved, pending spec review
**Scope:** future renders of **both** formats (short + long). The 5 already-published shorts
are NOT reworked. Three parts: a persistent watermark, a like/comment/subscribe end card, and
description polish (subscribe CTA + music credit).

## Goal

Every future video carries consistent channel branding: a corner watermark (logo + handle), a
branded end card driving Like/Comment/Subscribe, and a description that credits the music and
asks for the subscribe — all to strengthen the channel's profile.

## Brand constants

- Handle: `@untoldgamemedia` (from the channel's customUrl).
- Logo: `engine/video/remotion/public/brand/logo.png`, **committed**, seeded from the channel
  avatar (800×800). In a `public/` subfolder, so the per-render asset cleanup (top-level
  `*.mp4/.wav/.mp3` only) never deletes it — same pattern as `public/sfx/impact.wav`. The user
  can overwrite it with a custom transparent PNG anytime.
- A small `src/brand.ts` exporting `HANDLE = "@untoldgamemedia"` and `LOGO = "brand/logo.png"`
  so both new components share one source of truth.

## Part 1 — Watermark (`src/components/Watermark.tsx`, new)

A persistent overlay: the logo (small, rounded) + `@untoldgamemedia` text, **bottom-right**,
**opacity ~0.6**. Prop `vertical: boolean` scales size/padding:
- vertical (Short 1080×1920): logo ~64px, lifted ~140px from the bottom to clear the caption
  zone + YouTube Shorts UI.
- landscape (Long 1920×1080): logo ~56px, standard ~48px padding.

Rendered as a top layer in **both** `UntoldShort.tsx` and `UntoldVideo.tsx` (after captions, so
it sits above everything but only occupies the corner). Pure presentational — no Python props.

## Part 2 — End CTA card (`src/components/EndCTA.tsx`, new)

Replaces the bare long-form `Outro`. Content: the **logo**, **"LIKE · COMMENT · SUBSCRIBE"**,
the handle **@untoldgamemedia**, and a line *"for more untold stories."* Spring-in animation
(reuse the Outro's appear pattern). Prop `vertical` scales type.

- **Long-form (`UntoldVideo.tsx`):** swap `<Outro kicker=…/>` for `<EndCTA vertical={false}/>`
  in the existing outro Sequence. `Outro.tsx` is left in place but unused (no longer imported);
  removing it is a follow-up, not this change.
- **Short (`UntoldShort.tsx`):** add a closing Sequence `<EndCTA vertical/>` running for
  `outroMs`. `build_props` sets `outro_ms = 2500` for shorts (was 0) so the composition's
  duration (`introMs+narrationMs+outroMs`) includes the card. The narration `<Audio>` stays
  bounded to the narration; the **music bed** is extended to cover the outro and fades out over
  its final ~1.5s (currently it fades against `narrationMs`; switch the fade window to the full
  composition length so it carries under the card).

## Part 3 — Description polish (Python)

### 3a. Subscribe CTA — `metadata.generate_short_metadata`

Append after the hashtags:
`"\n\n👍 Like · 💬 Comment · 🔔 Subscribe → @untoldgamemedia"`. A `CHANNEL_HANDLE`
constant in `engine/config.py` (`"@untoldgamemedia"`) is the single source. Long-form metadata
already emits a subscribe CTA via `METADATA_SYSTEM`; add the handle to that prompt so it names
the channel too.

### 3b. Music credit — `engine/video/music.py` + render-time `write_credit`

Every video that uses a bed gets a credit line in its description, even CC0 tracks (courtesy +
good practice). Mechanism:
- `pick_track`/`short_music_props` return a **credit** that is the track's `attribution` if set,
  else a default `config.MUSIC_CREDIT_DEFAULT` (e.g. `"Music from Pixabay (royalty-free)"`).
- `write_credit` already appends `"Music: <credit>"` to `metadata.json` at render time; it now
  always receives a non-empty credit, so it always writes one.
- **Accuracy caveat:** the default claims Pixabay; the two titled tracks (`Evening`,
  `Southern Gothic`) may be from elsewhere. The user can set their real credit in
  `attribution.json` (which overrides the default per track). Documented, not guessed.

## Data flow

logo.png (committed) + brand.ts → Watermark/EndCTA overlays in both compositions. `build_props`
sets shorts `outro_ms=2500`. Description = hook + hashtags + subscribe CTA (produce time) +
`Music: …` (render time).

## Error handling

- Missing `logo.png` → committed asset, so it's present; if a user deletes it, Remotion's
  `<Img>` would error — mitigate by wrapping the logo in a try/`continueRender`-free optional:
  render the handle text always, the `<Img>` only when the file is expected (it's committed, so
  this is belt-and-suspenders; document that the file must stay).
- Music with no track (empty mood folder) → no credit line (unchanged self-stub).

## Testing

- **Python (`pytest`):** `generate_short_metadata` description ends with the subscribe CTA +
  handle; `short_music_props`/`pick_track` return the default credit when attribution is empty
  and the track's attribution when set; `write_credit` writes `Music: <default>` for a CC0
  track. `build_props` sets `outroMs=2500` for a short (`portrait=True`) and `0` for long-form.
- **Remotion:** `tsc --noEmit`; render one short + confirm by eye the watermark (bottom-right)
  and the end card (logo + Like/Comment/Subscribe + handle) appear, and the music carries under
  the outro.

## Out of scope (YAGNI)

Animated logo, per-video watermark text, removing the now-unused `Outro.tsx`, channel-link
cards/end-screens (YouTube's native end screens are a publish-time feature), and backfilling the
5 published shorts.
