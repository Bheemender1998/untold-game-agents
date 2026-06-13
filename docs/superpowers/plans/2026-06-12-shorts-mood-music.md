# Shorts Mood-Matched Background Music Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every rendered YouTube Short a mood-matched background music bed mixed low under the narration, with license attribution tracked.

**Architecture:** A new pure-Python `engine/video/music.py` selects a track by the idea's mood (deterministic, seeded by idea id) from `engine/video/music/<mood>/` via a generated `manifest.json`. `remotion_build.build_props` injects `musicSrc`/`musicVolume` props + stages the mp3; `run_video` writes the attribution credit. `UntoldShort.tsx` mixes a faded background `<Audio>` under the narration. Selection, prop-injection, and credit-writing are separate, unit-tested functions. Shorts only — long-form untouched.

**Tech Stack:** Python 3 (stdlib: `hashlib`, `json`, `glob`, `os`, `shutil`), pytest (main env), Remotion/React/TypeScript, ffprobe (verification only).

**Reference spec:** `docs/superpowers/specs/2026-06-12-shorts-mood-music-design.md`

**Conventions (CLAUDE.md):** `python3` not `python`; absolute `engine.*` imports; run tests with `python3 -m pytest tests/ -q`; never crash the run on missing data (self-stub); work on the `feat/shorts-mood-music` branch (already created), never main.

---

## File Structure

- **Create** `engine/video/music.py` — mood→track selection + manifest + credit writing. One responsibility: turn a mood into a chosen track + attribution, and surface that attribution. No Remotion/Node dependency.
- **Create** `tests/test_music.py` — unit tests for `music.py`.
- **Modify** `engine/video/remotion_build.py` — `build_props` returns a 3-tuple `(props, assets, music_credit)`, injecting music props for shorts.
- **Modify** `engine/run_video.py:104` — unpack the 3-tuple; after a successful short render, call `music.write_credit(...)`.
- **Modify** `engine/video/remotion/src/types.ts` — add optional `musicSrc`/`musicVolume` to `UntoldProps`.
- **Modify** `engine/video/remotion/src/UntoldShort.tsx` — add the faded background `<Audio>` layer.
- **Modify** `engine/video/remotion/src/shortDefaultProps.ts` — add default music fields (still-preview safe).
- **Create** `engine/video/music/attribution.json` — `{filename: credit}` for CC-BY tracks.
- **Move** the 51 files in `engine/video/music/music_all/` into `tense/ triumphant/ somber/ hype/ _unused/`.
- **Delete** the empty top-level `engine/music_all/` directory.
- **Generate** `engine/video/music/manifest.json` (committed alongside the sorted library).

---

## Task 1: `music.py` — module skeleton + constants

**Files:**
- Create: `engine/video/music.py`
- Test: `tests/test_music.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_music.py
from engine.video import music


def test_module_constants():
    assert music.MUSIC_VOLUME == 0.12
    assert music.MOODS == ("tense", "triumphant", "somber", "hype")
    # MUSIC_DIR points at the committed library folder
    assert music.MUSIC_DIR.endswith("engine/video/music")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_music.py::test_module_constants -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.video.music'` (it's a package dir today, not a module — the new file shadows nothing; the `music/` folder and `music.py` coexist since Python prefers the package only if it has `__init__.py`; verify in Step 4 that the import resolves to the file).

- [ ] **Step 3: Write minimal implementation**

```python
# engine/video/music.py
"""
Mood-matched background music for Shorts.

Selection is deterministic (seeded by idea id) over a per-mood folder of cleared
royalty-free tracks. A generated manifest.json carries each track's license
attribution. Selection, prop-injection, and credit-surfacing are separate so each
can be tested in isolation. Pure Python — no Remotion/Node dependency.
"""
from __future__ import annotations
import glob
import hashlib
import json
import os

MUSIC_DIR = os.path.join(os.path.dirname(__file__), "music")
MANIFEST = os.path.join(MUSIC_DIR, "manifest.json")
ATTRIBUTION = os.path.join(MUSIC_DIR, "attribution.json")
MOODS = ("tense", "triumphant", "somber", "hype")
MUSIC_VOLUME = 0.12
_EXTS = (".mp3", ".wav")
```

NOTE: `engine/video/music/` is a plain folder (no `__init__.py`), so `from engine.video import music` resolves to `music.py`. Confirm no `engine/video/music/__init__.py` exists; if one does, the import is ambiguous — delete it (the folder holds only audio, not Python).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_music.py::test_module_constants -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/video/music.py tests/test_music.py
git commit -m "feat(music): module skeleton + constants"
```

---

## Task 2: `build_manifest` — scan mood folders → manifest.json

**Files:**
- Modify: `engine/video/music.py`
- Test: `tests/test_music.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_manifest_groups_by_mood_and_ignores_unused(tmp_path):
    root = tmp_path / "music"
    for mood in ("tense", "somber"):
        (root / mood).mkdir(parents=True)
    (root / "tense" / "dark.mp3").write_bytes(b"x")
    (root / "somber" / "sad.mp3").write_bytes(b"x")
    (root / "somber" / "notes.txt").write_text("ignore me")   # non-audio ignored
    (root / "_unused").mkdir()
    (root / "_unused" / "boogie.mp3").write_bytes(b"x")        # off-tone, excluded
    (root / "attribution.json").write_text('{"sad.mp3": "Music by X (CC BY 4.0)"}')

    man = music.build_manifest(str(root))

    assert man["tense"] == [{"file": "tense/dark.mp3", "attribution": ""}]
    assert man["somber"] == [{"file": "somber/sad.mp3",
                              "attribution": "Music by X (CC BY 4.0)"}]
    assert "_unused" not in man
    # persisted to disk
    assert json.loads((root / "manifest.json").read_text())["tense"][0]["file"] == "tense/dark.mp3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_music.py::test_build_manifest_groups_by_mood_and_ignores_unused -v`
Expected: FAIL with `AttributeError: module 'engine.video.music' has no attribute 'build_manifest'`

- [ ] **Step 3: Write minimal implementation**

Append to `engine/video/music.py`:

```python
def _load_attribution(music_dir: str) -> dict:
    path = os.path.join(music_dir, "attribution.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def build_manifest(music_dir: str = MUSIC_DIR) -> dict:
    """Scan music_dir/<mood>/ for audio, write <music_dir>/manifest.json, return it.

    Shape: {mood: [{"file": "<mood>/<name>", "attribution": "<str>"}]}. Only the four
    canonical MOODS are scanned; _unused/ and stray files are ignored. Idempotent.
    """
    attribution = _load_attribution(music_dir)
    manifest: dict[str, list[dict]] = {}
    for mood in MOODS:
        tracks = []
        for path in sorted(glob.glob(os.path.join(music_dir, mood, "*"))):
            if os.path.splitext(path)[1].lower() not in _EXTS:
                continue
            name = os.path.basename(path)
            tracks.append({"file": f"{mood}/{name}",
                           "attribution": attribution.get(name, "")})
        manifest[mood] = tracks
    with open(os.path.join(music_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_music.py::test_build_manifest_groups_by_mood_and_ignores_unused -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/video/music.py tests/test_music.py
git commit -m "feat(music): build_manifest scans mood folders + attribution"
```

---

## Task 3: `pick_track` — deterministic mood selection

**Files:**
- Modify: `engine/video/music.py`
- Test: `tests/test_music.py`

- [ ] **Step 1: Write the failing test**

```python
def _seed_tree(tmp_path):
    root = tmp_path / "music"
    (root / "tense").mkdir(parents=True)
    (root / "tense" / "a.mp3").write_bytes(b"x")
    (root / "tense" / "b.mp3").write_bytes(b"x")
    (root / "tense" / "c.mp3").write_bytes(b"x")
    (root / "somber").mkdir()           # empty mood
    music.build_manifest(str(root))
    return str(root)


def test_pick_track_deterministic_for_same_seed(tmp_path):
    root = _seed_tree(tmp_path)
    a = music.pick_track("tense", "idea-123", root)
    b = music.pick_track("tense", "idea-123", root)
    assert a == b
    assert os.path.isabs(a["path"]) and a["path"].endswith(".mp3")
    assert a["attribution"] == ""


def test_pick_track_rotates_across_seeds(tmp_path):
    root = _seed_tree(tmp_path)
    picks = {os.path.basename(music.pick_track("tense", f"id-{i}", root)["path"])
             for i in range(20)}
    assert len(picks) >= 2     # not all seeds map to one track


def test_pick_track_none_for_empty_or_unknown_mood(tmp_path):
    root = _seed_tree(tmp_path)
    assert music.pick_track("somber", "idea-123", root) is None   # empty folder
    assert music.pick_track("nonsense", "idea-123", root) is None  # unknown mood
    assert music.pick_track("", "idea-123", root) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_music.py -k pick_track -v`
Expected: FAIL with `AttributeError: module 'engine.video.music' has no attribute 'pick_track'`

- [ ] **Step 3: Write minimal implementation**

Append to `engine/video/music.py`:

```python
def _read_manifest(music_dir: str) -> dict:
    path = os.path.join(music_dir, "manifest.json")
    if not os.path.exists(path):
        return build_manifest(music_dir)
    with open(path) as f:
        return json.load(f)


def pick_track(mood: str, seed: str, music_dir: str = MUSIC_DIR) -> dict | None:
    """Deterministically choose a track for `mood`, seeded by `seed` (the idea id).

    Returns {"path": <abs path>, "attribution": <str>} or None when the mood is
    unknown/empty. Same seed → same track; different seeds rotate over the folder.
    """
    if mood not in MOODS:
        return None
    tracks = _read_manifest(music_dir).get(mood, [])
    if not tracks:
        return None
    idx = int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(tracks)
    chosen = tracks[idx]
    return {"path": os.path.join(music_dir, chosen["file"]),
            "attribution": chosen.get("attribution", "")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_music.py -k pick_track -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/video/music.py tests/test_music.py
git commit -m "feat(music): deterministic pick_track by mood + seed"
```

---

## Task 4: `short_music_props` + `write_credit`

**Files:**
- Modify: `engine/video/music.py`
- Test: `tests/test_music.py`

- [ ] **Step 1: Write the failing test**

```python
def test_short_music_props_returns_fragment_asset_credit(tmp_path, monkeypatch):
    root = _seed_tree(tmp_path)
    monkeypatch.setattr(music, "MUSIC_DIR", root)
    idea = {"id": "idea-123", "mood": "tense"}
    frag, asset, credit = music.short_music_props(idea)
    assert frag["musicVolume"] == music.MUSIC_VOLUME
    assert frag["musicSrc"] == os.path.basename(asset)
    assert asset.endswith(".mp3") and os.path.isabs(asset)
    assert credit == ""


def test_short_music_props_empty_when_no_mood_track(tmp_path, monkeypatch):
    root = _seed_tree(tmp_path)
    monkeypatch.setattr(music, "MUSIC_DIR", root)
    frag, asset, credit = music.short_music_props({"id": "x", "mood": "somber"})  # empty mood
    assert frag == {} and asset is None and credit == ""


def test_write_credit_appends_once_and_writes_sidecar(tmp_path):
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps({"description": "A story."}))

    music.write_credit(str(video_dir), str(meta), "Music by X (CC BY 4.0)")
    music.write_credit(str(video_dir), str(meta), "Music by X (CC BY 4.0)")  # idempotent

    desc = json.loads(meta.read_text())["description"]
    assert desc.count("Music: Music by X (CC BY 4.0)") == 1
    assert (video_dir / "music_credit.txt").read_text() == "Music by X (CC BY 4.0)"


def test_write_credit_noop_on_empty(tmp_path):
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps({"description": "A story."}))
    music.write_credit(str(video_dir), str(meta), "")
    assert json.loads(meta.read_text())["description"] == "A story."
    assert not (video_dir / "music_credit.txt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_music.py -k "short_music_props or write_credit" -v`
Expected: FAIL with `AttributeError: ... has no attribute 'short_music_props'`

- [ ] **Step 3: Write minimal implementation**

Append to `engine/video/music.py`:

```python
def short_music_props(idea: dict, music_dir: str = MUSIC_DIR) -> tuple[dict, str | None, str]:
    """For a Short: pick a bed for the idea's mood.

    Returns (props_fragment, asset_path, credit). On a miss: ({}, None, "") so the
    caller renders silent (self-stub). props_fragment merges into the Remotion props.
    """
    chosen = pick_track(idea.get("mood") or "", idea.get("id", ""), music_dir)
    if not chosen:
        return {}, None, ""
    frag = {"musicSrc": os.path.basename(chosen["path"]), "musicVolume": MUSIC_VOLUME}
    return frag, chosen["path"], chosen["attribution"]


def write_credit(video_dir: str, metadata_path: str, credit: str) -> None:
    """Surface a non-empty attribution: sidecar file + one-time append to the
    metadata.json description. No-op when credit is empty. Idempotent."""
    if not credit:
        return
    with open(os.path.join(video_dir, "music_credit.txt"), "w") as f:
        f.write(credit)
    if not os.path.exists(metadata_path):
        return
    with open(metadata_path) as f:
        meta = json.load(f)
    line = f"Music: {credit}"
    desc = meta.get("description", "")
    if line not in desc:
        meta["description"] = (desc + "\n\n" + line).strip()
        with open(metadata_path, "w") as f:
            json.dump(meta, f, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_music.py -k "short_music_props or write_credit" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/video/music.py tests/test_music.py
git commit -m "feat(music): short_music_props + write_credit attribution surfacing"
```

---

## Task 5: Wire music into `build_props` (3-tuple return)

**Files:**
- Modify: `engine/video/remotion_build.py:22-76`
- Test: `tests/test_remotion_build.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_remotion_build.py
from engine.video import remotion_build, music


def _patch_heavy(monkeypatch):
    """Neutralize the network/heavy helpers so we test only the music wiring."""
    monkeypatch.setattr(remotion_build._tts, "script_to_narration_text", lambda md: "word word word")
    monkeypatch.setattr(remotion_build._captions, "estimate_word_timings",
                        lambda text, dur: [{"text": "word", "startMs": 0, "endMs": 500}])
    monkeypatch.setattr(remotion_build._compose, "build_section_headlines", lambda idea, md: [])
    monkeypatch.setattr(remotion_build._compose, "assign_headline_times", lambda s, w, d, n: [])
    monkeypatch.setattr(remotion_build._footage, "fetch_clips", lambda queries, vd, portrait=False: [])


def test_build_props_adds_music_for_short(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props",
                        lambda idea, *a, **k: ({"musicSrc": "x.mp3", "musicVolume": 0.12},
                                               "/lib/x.mp3", "Music by X"))
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, assets, credit = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0, portrait=True)
    assert props["musicSrc"] == "x.mp3" and props["musicVolume"] == 0.12
    assert "/lib/x.mp3" in assets
    assert credit == "Music by X"


def test_build_props_no_music_for_longform(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    called = []
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: called.append(1) or ({}, None, ""))
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, assets, credit = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0, portrait=False)
    assert "musicSrc" not in props and credit == ""
    assert called == []   # long-form never asks for music
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_remotion_build.py -v`
Expected: FAIL — `build_props` returns a 2-tuple (`ValueError: not enough values to unpack`).

- [ ] **Step 3: Write minimal implementation**

In `engine/video/remotion_build.py`, add the import near the others (line ~13):

```python
from engine.video import music as _music
```

Replace the final `props = {...}` / `return props, assets` block (lines ~63-76) with:

```python
    props = {
        "title": idea["title_variants"][0],
        "kicker": "THE UNTOLD GAME",
        "audioSrc": os.path.basename(audio_filename),
        "fps": fps,
        "width": width,
        "height": height,
        "introMs": intro_ms,
        "outroMs": outro_ms,
        "narrationMs": int(round(total_dur * 1000)),
        "captions": cap_words,
        "chapters": chapters,
    }

    # Shorts only: a mood-matched background bed mixed low under the narration.
    music_credit = ""
    if portrait:
        frag, music_asset, music_credit = _music.short_music_props(idea)
        if music_asset:
            props.update(frag)
            assets.append(music_asset)

    return props, assets, music_credit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_remotion_build.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/video/remotion_build.py tests/test_remotion_build.py
git commit -m "feat(music): inject mood bed into build_props for shorts"
```

---

## Task 6: Update the `run_video` caller (unpack 3-tuple, write credit)

**Files:**
- Modify: `engine/run_video.py:104-141`
- Test: covered by the full suite (`run_video` has no dedicated unit test; the 2→3 tuple change would break import/run if wrong — guard via `test_run_auto.py` which imports the stack, plus the smoke render in Task 9).

- [ ] **Step 1: Make the change**

In `engine/run_video.py`, change the `build_props` call (line ~104) to unpack three values:

```python
        props, assets, music_credit = remotion_build.build_props(
            idea, script_md, video_dir, audio_ref, words, total_dur,
            width=(1080 if is_short else 1920),
            height=(1920 if is_short else 1080),
            portrait=is_short,
            intro_ms=(0 if is_short else remotion_build.INTRO_MS),
            outro_ms=(0 if is_short else remotion_build.OUTRO_MS),
        )
```

After the successful-render block, immediately before `q.update_idea(args.id, video_path=...)` (line ~139), add the credit write:

```python
        from engine.video import music as _music
        _music.write_credit(video_dir, os.path.join(video_dir, "metadata.json"), music_credit)
        q.update_idea(args.id, video_path=os.path.relpath(mp4, _ROOT))
```

NOTE: `produced/<id>/metadata.json` is written by `run_produce`; `run_video`'s `video_dir` is `produced/<id>/video/`, so the metadata path is one level up: use `os.path.join(os.path.dirname(video_dir), "metadata.json")` if `metadata.json` is not inside `video_dir`. **Verify the actual location first** with `ls produced/0eaa1b66/` — adjust the path to wherever `metadata.json` lives. (From the repo it is `produced/<id>/metadata.json`, i.e. `os.path.dirname(video_dir)`.)

- [ ] **Step 2: Fix the metadata path per the note**

Use:

```python
        meta_path = os.path.join(os.path.dirname(os.path.abspath(video_dir)), "metadata.json")
        from engine.video import music as _music
        _music.write_credit(video_dir, meta_path, music_credit)
```

- [ ] **Step 3: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (no 2-tuple unpack errors anywhere; existing tests green).

- [ ] **Step 4: Commit**

```bash
git add engine/run_video.py
git commit -m "feat(music): write music attribution after short render"
```

---

## Task 7: Remotion — faded background `<Audio>` in the Short

**Files:**
- Modify: `engine/video/remotion/src/types.ts:17-29`
- Modify: `engine/video/remotion/src/UntoldShort.tsx`
- Modify: `engine/video/remotion/src/shortDefaultProps.ts`

- [ ] **Step 1: Add the optional props to the type**

In `types.ts`, add two fields to `UntoldProps` (after `chapters`):

```typescript
  chapters: Chapter[];
  musicSrc?: string;     // background bed filename in public/ (Shorts only); omitted → silent
  musicVolume?: number;  // peak bed volume under the narration (e.g. 0.12)
};
```

- [ ] **Step 2: Add default fields (still-preview safe)**

In `shortDefaultProps.ts`, add inside the default object (these keep the Studio preview happy; audio is ignored for still renders):

```typescript
  musicSrc: undefined,
  musicVolume: 0.12,
```

- [ ] **Step 3: Render the faded bed**

In `UntoldShort.tsx`, add the import for `interpolate` and render the bed inside the Narration sequence. Replace the component body's `Narration` sequence with:

```tsx
import {AbsoluteFill, Audio, interpolate, Sequence, staticFile, useVideoConfig} from 'remotion';
```

```tsx
      <Sequence from={introF} name="Narration">
        <Audio src={staticFile(props.audioSrc)} />
        {props.musicSrc ? (
          <Audio
            src={staticFile(props.musicSrc)}
            loop
            volume={(f) => {
              const peak = props.musicVolume ?? 0.12;
              const total = ms2f(props.narrationMs, fps);
              const fadeIn = Math.round(1.5 * fps);
              const fadeOut = Math.round(2.5 * fps);
              return interpolate(
                f,
                [0, fadeIn, Math.max(fadeIn, total - fadeOut), total],
                [0, peak, peak, 0],
                {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
              );
            }}
          />
        ) : null}
      </Sequence>
```

- [ ] **Step 4: Verify the composition still type-checks / bundles**

Run: `cd engine/video/remotion && npx remotion render src/index.ts UntoldShort /tmp/_musictest.mp4 --props=props.json --frames=0-0 2>&1 | tail -5` — using an existing `produced/<id>/video/props.json` copied to `engine/video/remotion/props.json` (or render a real short in Task 9). A single-frame render proves the bundle compiles with the new `<Audio>`/`interpolate` code.
Expected: render completes (single frame), no TypeScript/bundler error. (Audio is silent in a 1-frame render — that's fine; this only checks it compiles.)

- [ ] **Step 5: Commit**

```bash
git add engine/video/remotion/src/types.ts engine/video/remotion/src/UntoldShort.tsx engine/video/remotion/src/shortDefaultProps.ts
git commit -m "feat(music): faded background Audio bed in UntoldShort"
```

---

## Task 8: Triage — sort the 51 tracks + attribution + manifest

**Files:**
- Move: `engine/video/music/music_all/*` → `tense/ triumphant/ somber/ hype/ _unused/`
- Create: `engine/video/music/attribution.json`
- Delete: empty `engine/music_all/`
- Generate: `engine/video/music/manifest.json`

> **Sorting is a human-confirmed step.** The mapping below is the spec's proposed
> categorization. Before moving, present it to the user for correction (they can hear the
> tracks; the agent cannot). Apply their adjustments, THEN run the moves.

- [ ] **Step 1: Create the mood folders if missing**

```bash
cd engine/video/music
mkdir -p tense triumphant somber hype _unused
```

- [ ] **Step 2: Move tracks per the (confirmed) mapping**

```bash
cd engine/video/music/music_all
# somber
mv "paulyudin-sad-sad-music-508961.mp3" "paulyudin-sad-sad-music-485935.mp3" \
   "leberch-sad-piano-music-501447.mp3" "leberch-sad-piano-501483.mp3" \
   "mondamusic-sad-piano-529575.mp3" "Evening.mp3" "Southern Gothic.mp3" ../somber/
# tense
mv "universfield-dark-wave-cinematic-background-30s-498210.mp3" \
   "alexgrohl-dark-mystery-trailer-taking-our-time-131566.mp3" \
   "leberch-dark-cinematic-thriller-249485.mp3" "leberch-dark-510496.mp3" \
   "leberch-dark-cinematic-509801.mp3" "tunetank-cinematic-dark-mysterious-music-412770.mp3" \
   "alexzavesa-cinematic-dramatic-11120.mp3" ../tense/
# triumphant
mv "joyinsound-inspiring-inspirational-398333.mp3" "leberch-inspiring-516867.mp3" \
   "leberch-inspiring-511351.mp3" "tunetank-inspiring-cinematic-music-409347.mp3" \
   "jonasblakewood-inspiring-517928.mp3" "the_mountain-inspiring-483307.mp3" \
   "music_for_videos-inspiring-emotional-uplifting-piano-112623.mp3" \
   "stereo_color-inspiring-cinematic-trailer-484743.mp3" ../triumphant/
# hype
mv "paulyudin-epic-epic-music-482365.mp3" "the_mountain-epic-483805.mp3" \
   "good_b_music-epic-hollywood-trailer-9489.mp3" "nastelbom-trailer-cinematic-488314.mp3" \
   "the_mountain-cinematic-489998.mp3" "lexin_music-cinematic-time-lapse-115672.mp3" ../hype/
# everything still here is off-tone → _unused
mv ./* ../_unused/ 2>/dev/null || true
```

- [ ] **Step 3: Write attribution.json for CC-BY tracks**

Most selected tracks are Pixabay (CC0, no credit). Any Kevin MacLeod / Incompetech or
credit-required track that survived into a mood folder needs an entry. Based on the proposed
mapping, no CC-BY track lands in a mood folder, so the file starts effectively empty but
present (so `build_manifest` always finds it):

```json
{}
```

If the user moves a credit-required track into a mood folder, add e.g.
`"Lord of the Rangs.mp3": "Music by Kevin MacLeod (incompetech.com), licensed CC BY 4.0"`.

- [ ] **Step 4: Remove the stray empty top-level dir**

```bash
rmdir /Users/bheemendergurram/untold_game_agents/engine/music_all 2>/dev/null || true
```

- [ ] **Step 5: Generate the manifest**

```bash
python3 -c "from engine.video import music; import json; print(json.dumps(music.build_manifest(), indent=2))"
```

Expected: each mood lists its moved tracks; `_unused/` absent.

- [ ] **Step 6: Decide git-tracking of the binaries (ask user)**

The audio files are NOT gitignored. Options to present:
- **(a) Commit the curated library** (`tense/ triumphant/ somber/ hype/` + `manifest.json` + `attribution.json`) and **gitignore `_unused/`** — reproducible renders, modest repo growth (selected beds are ~1–3 min each).
- **(b) Gitignore all audio**, commit only `manifest.json` + `attribution.json` + README — keep repo lean; library lives locally on the render M2.

Apply the user's choice: if (a), `git add` the four mood folders + manifest + attribution and add `engine/video/music/_unused/` + `engine/video/music/music_all/` to `.gitignore`. If (b), add `engine/video/music/**/*.mp3` and `*.wav` to `.gitignore` and commit only the manifest/attribution/README.

- [ ] **Step 7: Run the full suite (manifest now reflects the real library)**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A engine/video/music .gitignore
git commit -m "feat(music): triage 51 tracks into moods + manifest + attribution"
```

---

## Task 9: Smoke render — confirm audible bed

**Files:** none (verification).

- [ ] **Step 1: Re-render one short with a known mood**

Pick a rendered short whose mood has tracks (e.g. O.J. `0eaa1b66`, mood derived from pillar/script).

Run: `python3 -m engine.run_video --id 0eaa1b66 --mode narrated --format short --render 2>&1 | tail -20`
Expected: render completes; `produced/0eaa1b66/video/props.json` now contains `musicSrc`/`musicVolume`.

- [ ] **Step 2: Confirm the output has two mixed sources / non-silent bed**

Run: `ffprobe -v error -show_entries stream=codec_type -of csv=p=0 produced/0eaa1b66/video/video.mp4` (expect a video + audio stream) and spot-check by ear that music sits under the narration without drowning it.
Expected: audio stream present; narration clearly intelligible with a low bed.

- [ ] **Step 3: Confirm attribution only when required**

Run: `cat produced/0eaa1b66/video/music_credit.txt 2>/dev/null || echo "no credit (CC0 track) — expected"`
Expected: file present only if a CC-BY track was selected; otherwise absent.

- [ ] **Step 4: Final full suite + done**

Run: `python3 -m pytest tests/ -q`
Expected: PASS. Feature complete.

---

## Self-Review Notes

- **Spec coverage:** music.py (manifest/pick/props/credit) → Tasks 1–4; build_props injection → Task 5; run_video credit write → Task 6; UntoldShort Audio + fades + loop → Task 7; 51-track triage + attribution + `_unused` + remove `engine/music_all` + git-tracking decision → Task 8; graceful silent fallback → tested in Tasks 3–5; smoke verification → Task 9. All spec sections covered.
- **Determinism:** `pick_track` uses `hashlib.sha1` (not `Math.random`/`Date.now`), so renders are reproducible.
- **Self-stub:** every miss path returns empty/None → silent render, never a crash.
- **Type consistency:** `short_music_props` returns `(frag, asset, credit)`; `build_props` returns `(props, assets, music_credit)`; `run_video` unpacks three; props fields `musicSrc`/`musicVolume` match `types.ts` and `UntoldShort.tsx`.
- **Ship rail:** this is an `engine/*.py` change → after Task 9, ship via the `ship-video-change` rail (dual adversarial review + PR trailer), per CLAUDE.md.
