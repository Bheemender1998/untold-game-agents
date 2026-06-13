# Branding & Profile Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Add a corner watermark, a Like/Comment/Subscribe end card, and description polish (subscribe CTA + music credit) to all future renders of both formats.

**Architecture:** Two new Remotion components (`Watermark`, `EndCTA`) sharing `brand.ts` + committed `public/brand/logo.png`, wired into both compositions; `build_props` gives shorts a 2.5s outro; Python adds a subscribe-CTA constant to descriptions and a default music credit so `write_credit` always credits.

**Reference spec:** `docs/superpowers/specs/2026-06-12-branding-profile-design.md`

---

## Task 1: Brand constants + config

**Files:** Create `engine/video/remotion/src/brand.ts`; modify `engine/config.py`; Test `tests/test_config.py` (append or create).

- [ ] **Step 1: brand.ts**

```typescript
// engine/video/remotion/src/brand.ts
export const HANDLE = '@untoldgamemedia';
export const LOGO = 'brand/logo.png'; // under public/, staticFile path
```

- [ ] **Step 2: config constants — write the failing test**

```python
# tests/test_config.py
from engine import config

def test_brand_constants():
    assert config.CHANNEL_HANDLE == "@untoldgamemedia"
    assert config.MUSIC_CREDIT_DEFAULT  # non-empty courtesy credit
```

- [ ] **Step 3: run → fail**, then add to `engine/config.py`:

```python
CHANNEL_HANDLE = "@untoldgamemedia"
MUSIC_CREDIT_DEFAULT = "Music from Pixabay (royalty-free)"
```

Run: `python3 -m pytest tests/test_config.py::test_brand_constants -v` → PASS

- [ ] **Step 4: Commit** `git add engine/video/remotion/src/brand.ts engine/config.py tests/test_config.py && git commit -m "feat(brand): handle + music-credit constants"`

---

## Task 2: Music credit always present

**Files:** Modify `engine/video/music.py` (`short_music_props`); Test `tests/test_music.py`.

- [ ] **Step 1: Failing test (append to tests/test_music.py)**

```python
def test_short_music_props_defaults_credit_for_cc0(tmp_path, monkeypatch):
    from engine import config
    root = _seed_tree(tmp_path)
    monkeypatch.setattr(music, "MUSIC_DIR", root)
    _, asset, credit = music.short_music_props({"id": "idea-123", "mood": "tense"})
    assert asset is not None
    assert credit == config.MUSIC_CREDIT_DEFAULT  # no attribution.json → default
```

- [ ] **Step 2: run → fail** (`credit == ""`).

- [ ] **Step 3: Implement** — in `short_music_props`, default the credit:

```python
    chosen = pick_track(idea.get("mood") or "", idea.get("id", ""), music_dir)
    if not chosen:
        return {}, None, ""
    from engine import config
    credit = chosen["attribution"] or config.MUSIC_CREDIT_DEFAULT
    frag = {"musicSrc": os.path.basename(chosen["path"]), "musicVolume": MUSIC_VOLUME}
    return frag, chosen["path"], credit
```

- [ ] **Step 4: run → pass**; `python3 -m pytest tests/test_music.py -q`

- [ ] **Step 5: Commit** `git add engine/video/music.py tests/test_music.py && git commit -m "feat(music): always credit the bed (default source for CC0)"`

---

## Task 3: Subscribe CTA in Short description

**Files:** Modify `engine/pipeline/metadata.py` (`generate_short_metadata`); Test `tests/test_metadata.py`.

- [ ] **Step 1: Failing test (append)**

```python
def test_short_description_has_subscribe_cta(monkeypatch):
    from engine import config
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda i, s: ("Hook.", ["t"]))
    m = metadata.generate_short_metadata({"title_variants": ["T"], "sport": "F1", "pillar": "p"}, "Hook.")
    assert m["description"].rstrip().endswith(config.CHANNEL_HANDLE)
    assert "Subscribe" in m["description"]
```

- [ ] **Step 2: run → fail.**

- [ ] **Step 3: Implement** — in `generate_short_metadata`, after building `description`:

```python
    from engine.config import CHANNEL_HANDLE
    description = (f"{body}\n\n{hashtags}\n\n"
                  f"\U0001F44D Like · \U0001F4AC Comment · \U0001F514 Subscribe → {CHANNEL_HANDLE}")
```

(replace the existing `description = f"{body}\n\n{hashtags}"` line.)

- [ ] **Step 4: run → pass**; full suite `python3 -m pytest tests/ -q`.

- [ ] **Step 5: Commit** `git add engine/pipeline/metadata.py tests/test_metadata.py && git commit -m "feat(metadata): subscribe CTA in Short descriptions"`

---

## Task 4: Shorts get a 2.5s outro (build_props)

**Files:** Modify `engine/run_video.py` (the `intro_ms/outro_ms` for shorts) OR `remotion_build.INTRO_MS/OUTRO_MS`; Test `tests/test_remotion_build.py`.

- [ ] **Step 1: Failing test (append to tests/test_remotion_build.py)**

```python
def test_build_props_short_has_outro(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props", lambda i, *a, **k: ({}, None, ""))
    idea = {"id": "i", "mood": "tense", "title_variants": ["T"]}
    props, _, _ = remotion_build.build_props(idea, "# s\nb", str(tmp_path), "n.wav", None, 10.0,
                                             portrait=True, outro_ms=2500)
    assert props["outroMs"] == 2500
```

- [ ] **Step 2: run → pass already** (build_props already passes outro_ms through). This test just locks it. Then change the **caller** default in `engine/run_video.py`:

```python
            intro_ms=(0 if is_short else remotion_build.INTRO_MS),
            outro_ms=(2500 if is_short else remotion_build.OUTRO_MS),
```

(was `0 if is_short`.)

- [ ] **Step 3: run full suite → pass.**

- [ ] **Step 4: Commit** `git add engine/run_video.py tests/test_remotion_build.py && git commit -m "feat(video): 2.5s end-card outro for shorts"`

---

## Task 5: Watermark + EndCTA components

**Files:** Create `src/components/Watermark.tsx`, `src/components/EndCTA.tsx`; modify `UntoldShort.tsx`, `UntoldVideo.tsx`, `types.ts` (none needed — components are self-contained).

- [ ] **Step 1: Watermark.tsx**

```tsx
import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {HANDLE, LOGO} from '../brand';
import {oswald, CREAM} from '../fonts';

export const Watermark: React.FC<{vertical?: boolean}> = ({vertical}) => {
  const logo = vertical ? 64 : 56;
  const bottom = vertical ? 140 : 48;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'flex-end', opacity: 0.6}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 12, padding: `0 ${vertical ? 36 : 48}px ${bottom}px 0`}}>
        <Img src={staticFile(LOGO)} style={{width: logo, height: logo, borderRadius: '50%'}} />
        <span style={{fontFamily: oswald, fontWeight: 600, fontSize: vertical ? 30 : 26,
          color: CREAM, letterSpacing: '0.04em', textShadow: '0 2px 12px rgba(0,0,0,0.8)'}}>{HANDLE}</span>
      </div>
    </AbsoluteFill>
  );
};
```

- [ ] **Step 2: EndCTA.tsx**

```tsx
import React from 'react';
import {AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {HANDLE, LOGO} from '../brand';
import {anton, oswald, GOLD, CREAM} from '../fonts';

export const EndCTA: React.FC<{vertical?: boolean}> = ({vertical}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const appear = spring({frame: f, fps, config: {damping: 200}});
  const y = interpolate(appear, [0, 1], [30, 0]);
  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', flexDirection: 'column', opacity: appear}}>
      <Img src={staticFile(LOGO)} style={{width: vertical ? 160 : 120, height: vertical ? 160 : 120,
        borderRadius: '50%', marginBottom: 28, transform: `translateY(${y}px)`}} />
      <div style={{fontFamily: anton, fontSize: vertical ? 64 : 80, color: CREAM, textTransform: 'uppercase',
        textAlign: 'center', lineHeight: 1.08, transform: `translateY(${y}px)`,
        textShadow: '0 6px 40px rgba(0,0,0,0.7)'}}>LIKE · COMMENT<br />SUBSCRIBE</div>
      <div style={{fontFamily: oswald, fontWeight: 600, letterSpacing: '0.3em', textTransform: 'uppercase',
        fontSize: vertical ? 34 : 30, color: GOLD, marginTop: 24, transform: `translateY(${y}px)`}}>{HANDLE}</div>
      <div style={{fontFamily: oswald, fontSize: vertical ? 26 : 24, color: CREAM, opacity: 0.8, marginTop: 14}}>for more untold stories.</div>
    </AbsoluteFill>
  );
};
```

- [ ] **Step 3: Verify fonts exports** — `grep -n "GOLD\|CREAM\|anton\|oswald" src/fonts.ts` (confirm these are exported; they are used by Outro.tsx already).

- [ ] **Step 4: Commit** `git add src/components/Watermark.tsx src/components/EndCTA.tsx && git commit -m "feat(brand): Watermark + EndCTA remotion components"`

---

## Task 6: Wire components into both compositions

**Files:** Modify `src/UntoldShort.tsx`, `src/UntoldVideo.tsx`.

- [ ] **Step 1: UntoldShort.tsx** — add imports and, inside the root `<AbsoluteFill>` after the Captions Sequence, add the outro + watermark:

```tsx
import {Watermark} from './components/Watermark';
import {EndCTA} from './components/EndCTA';
```
```tsx
      <Sequence from={introF + ms2f(props.narrationMs, fps)} name="EndCTA">
        <EndCTA vertical />
      </Sequence>
      <Watermark vertical />
```
(Placed as the last children so they layer on top.)

- [ ] **Step 2: UntoldVideo.tsx** — swap the Outro for EndCTA and add the watermark. Change the import `import {Outro} from './components/Outro';` to `import {EndCTA} from './components/EndCTA';` plus `import {Watermark} from './components/Watermark';`, and replace `<Outro kicker={props.kicker} />` with `<EndCTA />`. Add `<Watermark />` as the last child of the root `<AbsoluteFill>`.

- [ ] **Step 3: Type-check** — `cd engine/video/remotion && npx --no-install tsc --noEmit` → no errors.

- [ ] **Step 4: Commit** `git add src/UntoldShort.tsx src/UntoldVideo.tsx && git commit -m "feat(brand): wire watermark + end card into both compositions"`

---

## Task 7: Music bed carries under the outro

**Files:** Modify `src/UntoldShort.tsx` (the music `<Audio>` fade window).

- [ ] **Step 1: Change the fade to span the full composition** — in the music `<Audio volume>` callback, replace `const total = ms2f(props.narrationMs, fps);` with `const total = ms2f(props.introMs + props.narrationMs + props.outroMs, fps);` so the bed fades out at the very end (under the card) instead of when narration stops.

- [ ] **Step 2: Type-check** — `npx --no-install tsc --noEmit` → no errors.

- [ ] **Step 3: Commit** `git add src/UntoldShort.tsx && git commit -m "feat(brand): music bed carries under the Short end card"`

---

## Task 8: Verify with a real short render

**Files:** none.

- [ ] **Step 1: Render one short** (use a fresh idea or re-render an existing produced one; the 5 published stay untouched on YouTube — this only writes a local mp4):

`/.venv-video/bin/python -m engine.run_video --id 0c76c4c4 --mode narrated --format short --render`

- [ ] **Step 2: Eyeball** the local `produced/0c76c4c4/video/video.mp4`: bottom-right watermark present throughout; a ~2.5s Like/Comment/Subscribe card with logo + handle at the end; music audible under the card. (This is local only — does NOT touch the published unlisted video.)

- [ ] **Step 3: Full suite** `python3 -m pytest tests/ -q` → PASS.

---

## Self-Review Notes

- **Spec coverage:** brand constants → T1; music credit → T2; CTA → T3; shorts outro → T4; components → T5; wiring → T6; music-under-outro → T7; verify → T8.
- **Both formats** get watermark + end card; description CTA is shorts (long-form already has a CTA via METADATA_SYSTEM — handle added there is optional, deferred).
- **Self-stub:** missing track → no credit; logo committed.
