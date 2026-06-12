# Title-card Impact SFX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Play a single soft low-end impact ("weighty" variant) as the intro title and each chapter headline springs in, mixed under the narration by Remotion.

**Architecture:** A reusable, peak-normalized `impact.wav` lives at `engine/video/remotion/public/sfx/impact.wav` (a subdirectory the per-render asset-staging step does NOT wipe, because its cleanup glob is top-level only). `UntoldVideo.tsx` drops a small `<Impact/>` `<Audio>` element into the existing Intro sequence and each Chapter sequence; Remotion auto-mixes it with the narration at render. Volume is a single tunable constant.

**Tech Stack:** ffmpeg (`aevalsrc` synthesis + peak-normalize), Remotion 4 (`<Audio>`, `staticFile`), pytest (regression guard for asset staging).

**Spec:** `docs/superpowers/specs/2026-06-12-title-impact-sfx-design.md`

---

## File Structure

- `tests/test_render_remotion.py` — **new.** Regression test locking the invariant that asset staging preserves `public/sfx/impact.wav`.
- `engine/video/make_impact_sfx.sh` — **modify.** Change the install branch to peak-normalize the chosen variant to ≈ −1 dBFS instead of a raw copy. (Synthesis already written and verified.)
- `engine/video/remotion/public/sfx/impact.wav` — **new committed asset.** The installed `weighty` impact.
- `engine/video/remotion/src/UntoldVideo.tsx` — **modify.** Add `IMPACT_VOL` + `Impact` component; render it inside the Intro sequence and each Chapter sequence.

---

## Task 1: Regression test — staging preserves the SFX subdirectory

Locks the load-bearing fact that lets the SFX live in `public/`: `_stage_assets` clears only top-level `public/*.wav|*.mp4|*.mp3`, so `public/sfx/impact.wav` survives every render.

**Files:**
- Test: `tests/test_render_remotion.py` (create)

- [ ] **Step 1: Write the test**

Create `tests/test_render_remotion.py`:

```python
from engine.video import render_remotion


def test_stage_assets_preserves_sfx_subdir(tmp_path, monkeypatch):
    """The committed title-impact SFX lives in public/sfx/ so the per-render asset
    cleanup (which globs only top-level *.wav/*.mp4/*.mp3) must not delete it."""
    public = tmp_path / "public"
    sfx = public / "sfx"
    sfx.mkdir(parents=True)
    impact = sfx / "impact.wav"
    impact.write_bytes(b"IMPACT")              # the committed SFX asset
    (public / "stale.wav").write_bytes(b"old")  # a leftover from a previous render
    monkeypatch.setattr(render_remotion, "PUBLIC_DIR", str(public))

    audio = tmp_path / "narration.wav"
    audio.write_bytes(b"voice")
    clip = tmp_path / "bg_00.mp4"
    clip.write_bytes(b"clip")

    render_remotion._stage_assets(str(audio), [str(clip)])

    assert impact.read_bytes() == b"IMPACT"          # SFX in subdir survived
    assert not (public / "stale.wav").exists()       # stale top-level wav cleared
    assert (public / "narration.wav").exists()       # this render's audio staged
    assert (public / "bg_00.mp4").exists()           # this render's clip staged
```

- [ ] **Step 2: Run the test to verify it passes (characterization guard)**

Run: `python3 -m pytest tests/test_render_remotion.py -v`
Expected: PASS. (This guards existing behavior the SFX depends on. If it FAILS — e.g. the cleanup glob is recursive — STOP: the SFX cannot live in `public/sfx/` and the design needs revisiting.)

- [ ] **Step 3: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (the PostToolUse hook also runs this automatically).

- [ ] **Step 4: Commit**

```bash
git add tests/test_render_remotion.py
git commit -m "test: lock that asset staging preserves public/sfx/ SFX

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Peak-normalize on install, and install the `weighty` variant

The raw `weighty` audition peaks low (≈ −10 dB) because its sub + echo spread the energy. Normalizing to ≈ −1 dBFS on install makes its loudness predictable relative to the narration, so `IMPACT_VOL` tuning is meaningful.

**Files:**
- Modify: `engine/video/make_impact_sfx.sh` (the install branch only)
- Create (generated): `engine/video/remotion/public/sfx/impact.wav`

- [ ] **Step 1: Replace the raw `cp` install with a peak-normalize**

In `engine/video/make_impact_sfx.sh`, replace the install block at the end:

```bash
# If a variant name was passed, install it as the composition's impact.wav.
if [[ "${1:-}" != "" ]]; then
  pick="$OUT/impact_${1}.wav"
  [[ -f "$pick" ]] || { echo "no such variant: $1" >&2; exit 1; }
  mkdir -p "$(dirname "$FINAL")"
  cp "$pick" "$FINAL"
  echo "Installed $1 -> $FINAL"
fi
```

with a peak-normalizing install (target ≈ −1 dBFS):

```bash
# If a variant name was passed, peak-normalize it to ~ -1 dBFS and install it as the
# composition's impact.wav (predictable loudness vs. the narration).
if [[ "${1:-}" != "" ]]; then
  pick="$OUT/impact_${1}.wav"
  [[ -f "$pick" ]] || { echo "no such variant: $1" >&2; exit 1; }
  maxdb=$(ffmpeg -hide_banner -i "$pick" -af volumedetect -f null - 2>&1 \
            | grep -oE "max_volume: [-0-9.]+ dB" | grep -oE "[-0-9.]+")
  gain=$(awk "BEGIN{printf \"%.2f\", -1.0 - ($maxdb)}")
  mkdir -p "$(dirname "$FINAL")"
  ffmpeg -hide_banner -loglevel error -y -i "$pick" -af "volume=${gain}dB" \
    -c:a pcm_s16le "$FINAL"
  echo "Installed $1 -> $FINAL  (peak-normalized ${gain}dB to ~ -1 dBFS)"
fi
```

- [ ] **Step 2: Regenerate auditions and install `weighty`**

Run: `engine/video/make_impact_sfx.sh weighty`
Expected: prints the three audition writes, then `Installed weighty -> .../public/sfx/impact.wav (peak-normalized +X.XXdB ...)`.

- [ ] **Step 3: Verify the installed file is ~ −1 dBFS and not clipping**

Run:
```bash
ffmpeg -hide_banner -i engine/video/remotion/public/sfx/impact.wav -af volumedetect -f null - 2>&1 \
  | grep -oE "max_volume: [-0-9.]+ dB"
```
Expected: `max_volume: -1.0 dB` (± 0.2 dB), i.e. negative — no clipping.

- [ ] **Step 4: Commit the script change and the asset**

```bash
git add engine/video/make_impact_sfx.sh engine/video/remotion/public/sfx/impact.wav
git commit -m "feat(video): synth + install peak-normalized title impact SFX (weighty)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire the impact into the Intro and Chapter sequences

**Files:**
- Modify: `engine/video/remotion/src/UntoldVideo.tsx`

(`Audio` and `staticFile` are already imported from `remotion` in this file — no import change.)

- [ ] **Step 1: Add the `IMPACT_VOL` constant and the `Impact` component**

In `engine/video/remotion/src/UntoldVideo.tsx`, just below the `ms2f` helper line
(`const ms2f = (ms: number, fps: number) => Math.round((ms / 1000) * fps);`), add:

```tsx
// Soft low-end impact under each title reveal (intro + chapter cards). Remotion mixes it
// alongside the narration; kept low so it sits under the voice. Tune IMPACT_VOL by ear.
const IMPACT_VOL = 0.4;
const Impact: React.FC = () => (
  <Audio src={staticFile('sfx/impact.wav')} volume={IMPACT_VOL} />
);
```

- [ ] **Step 2: Drop the impact into the Intro sequence**

Replace the Intro sequence block:

```tsx
      <Sequence durationInFrames={introF} name="Intro">
        <Intro title={props.title} kicker={props.kicker} />
      </Sequence>
```

with:

```tsx
      <Sequence durationInFrames={introF} name="Intro">
        <Intro title={props.title} kicker={props.kicker} />
        <Impact />
      </Sequence>
```

- [ ] **Step 3: Drop the impact into each Chapter sequence**

Replace the chapter map's Sequence body:

```tsx
        <Sequence
          key={i}
          from={introF + ms2f(c.startMs, fps)}
          durationInFrames={Math.max(1, ms2f(c.endMs - c.startMs, fps))}
          name={`Chapter ${i + 1}`}
        >
          <ChapterCard headline={c.headline} />
        </Sequence>
```

with:

```tsx
        <Sequence
          key={i}
          from={introF + ms2f(c.startMs, fps)}
          durationInFrames={Math.max(1, ms2f(c.endMs - c.startMs, fps))}
          name={`Chapter ${i + 1}`}
        >
          <ChapterCard headline={c.headline} />
          <Impact />
        </Sequence>
```

- [ ] **Step 4: Verify the composition still compiles (render a still)**

Run:
```bash
cd engine/video/remotion && node_modules/.bin/remotion still src/index.ts UntoldVideo \
  out/polish/sfx_wired.png --frame=134 --log=error; echo "EXIT=$?"
```
Expected: `EXIT=0` and `out/polish/sfx_wired.png` exists. (A still ignores audio; this only confirms the new `<Audio>`/`Impact` elements typecheck and the graph renders. The `impact.wav` from Task 2 must exist or `staticFile` resolution fails.)

- [ ] **Step 5: Commit**

```bash
git add engine/video/remotion/src/UntoldVideo.tsx
git commit -m "feat(video): play title impact SFX on intro + chapter cards

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Integration check — render a short audio segment, judge by ear, tune volume

The only real test of an SFX mix is listening. Render the opening (intro + first two chapter hits) with the real narration and have the user audition it.

**Files:**
- (Possibly) Modify: `engine/video/remotion/src/UntoldVideo.tsx` — only if the user wants `IMPACT_VOL` adjusted.

- [ ] **Step 1: Render a ~9s segment with audio**

Run:
```bash
cd engine/video/remotion && node_modules/.bin/remotion render src/index.ts UntoldVideo \
  out/polish/sfx_check.mp4 --frames=0-270 --log=error; echo "EXIT=$?"
```
Expected: `EXIT=0`, `out/polish/sfx_check.mp4` exists. (Uses `defaultProps` → the real `public/narration.wav`; frames 0-270 cover the intro hit at frame 0 and the chapter hits at frames 120 and 255.)

- [ ] **Step 2: Confirm the output actually has an audio stream**

Run:
```bash
ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 \
  engine/video/remotion/out/polish/sfx_check.mp4
```
Expected: `audio`

- [ ] **Step 3: User auditions and judges**

Open `engine/video/remotion/out/polish/sfx_check.mp4` (`open` it). The user judges: does the impact land *with* each title and sit *under* the voice (felt, not masking words)? Too loud / too quiet / too long a tail?

- [ ] **Step 4: Tune `IMPACT_VOL` if needed (repeat until the user is happy)**

If the user wants it louder/quieter, change `const IMPACT_VOL = 0.4;` in
`engine/video/remotion/src/UntoldVideo.tsx` (e.g. `0.3` quieter, `0.5` louder) and re-run
Steps 1–3. If they want a different character (shorter tail, etc.), adjust the `weighty`
synthesis params in `make_impact_sfx.sh`, re-run `make_impact_sfx.sh weighty`, and re-render.

- [ ] **Step 5: Commit any volume change**

```bash
git add engine/video/remotion/src/UntoldVideo.tsx
git commit -m "tune(video): set title impact SFX volume

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(Skip this commit if `IMPACT_VOL` was left at `0.4`.)

---

## Ship

This is an `engine/video/**` change → ship via the **`ship-video-change`** rail (branch, `python3 -m pytest tests/ -q`, dual adversarial review — Codex + Claude — and a PR with the `Adversarial-Reviewed:` trailer). The 45-min full render is never a gate; Task 4's short segment + the user's ear are the check. Note: `engine/video/sfx_auditions/` stays untracked (throwaway previews).

---

## Self-Review

- **Spec coverage:**
  - "single low impact … intro + each chapter" → Task 3 (Intro + chapter sequences). ✓
  - "sits under the narration / felt" → `IMPACT_VOL` (Task 3) + audition tuning (Task 4). ✓
  - "fully owned / CC0, synthesized, reproducible" → `make_impact_sfx.sh` (Task 2). ✓
  - "chosen sound = weighty, peak-normalized on install" → Task 2 Steps 1–3. ✓
  - "asset at public/sfx/impact.wav, committed" → Task 2 Step 4. ✓
  - "risk: produce pipeline wipes public/" → resolved (non-recursive glob) + guarded by Task 1. ✓
  - "mixing inside Remotion via <Audio>" → Task 3. ✓
  - "verify: short render + ffprobe + user ear" → Task 4. ✓
  - "pytest stays green" → Task 1 Step 3. ✓
- **Placeholder scan:** No TBD/TODO; every code/command step shows exact content. ✓
- **Type consistency:** `Impact` component and `IMPACT_VOL` defined in Task 3 Step 1 and used in Steps 2–3; `_stage_assets`/`PUBLIC_DIR` names match `render_remotion.py`. ✓
