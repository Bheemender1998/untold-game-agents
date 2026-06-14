# Short-form pacing + mood-driven b-roll variety — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make YouTube Shorts scroll-stopping — a conflict-first hook, brisk pacing, and a *new* mood-driven atmospheric b-roll clip every ~2.5s (no single-clip loop), with the no-single-loop variety also applied to long-form at a cinematic cadence.

**Architecture:** Pacing and cut-cadence are format-parameterised (short vs long). B-roll selection moves from per-chapter Claude-written symbolic queries to a deterministic mood→atmospheric-pool table; a new *beat track* (independent of chapter cards) drives one deduped Pexels clip per beat, rendered with a hard cut + Ken-Burns zoom. Hook changes are prompt-only. All long-form narration pace and timing are untouched.

**Tech Stack:** Python 3 (`python3 -m pytest tests/ -q`), kokoro-onnx TTS, Pexels API (`footage.py`), Remotion/React TSX (`engine/video/remotion/`).

**Spec:** `docs/superpowers/specs/2026-06-13-shortform-pacing-and-broll-variety-design.md`

**Branch:** `feat/shortform-pacing-broll` (already created; spec already committed).

**Conventions:** `python3` not `python`. Absolute `engine.*` imports. The PostToolUse hook runs `pytest tests/ -q` after every `engine/**.py` edit. Render is NEVER a test gate — TSX tasks verify via `npx tsc --noEmit` + the final Cantona re-render.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `engine/config.py` | Tunable knobs | + `SHORT_NARRATION_SPEED`, `SHORT_NARRATION_GAP_S`, `SHORT_BROLL_BEAT_S`, `LONG_BROLL_BEAT_S`, `MOOD_BROLL_POOL` |
| `engine/video/tts.py` | Narration synth | + `narration_pace(fmt)` helper |
| `engine/video/footage.py` | Clip sourcing | + `mood_beat_queries(mood, n)` |
| `engine/video/remotion_build.py` | Python→Remotion props bridge | + `beat_track()`; rework `build_props` to emit `bBeats` |
| `engine/run_video.py` | Render entrypoint | pass pace + beat cadence by format |
| `engine/pipeline/script.py` | Short script prompts | sharpen `SHORT_SYSTEM` + `DERIVE_TEASE_SYSTEM` hook |
| `engine/video/remotion/src/types.ts` | Props schema | + `BBeat` type, `bBeats?` field |
| `engine/video/remotion/src/components/Background.tsx` | Background render | render `bBeats` (hard cut + zoom), fall back to `bClip` |
| `engine/video/remotion/src/UntoldShort.tsx`, `UntoldVideo.tsx` | Compositions | pass `bBeats` to `Background` |
| `engine/video/remotion/src/components/ShortCaptions.tsx` | Short captions | small page-level scale pop |
| `tests/test_config.py`, `test_tts.py`, `test_footage.py`, `test_remotion_build.py`, `test_script.py` | Coverage | new assertions |

---

## Task 1: Short-only pacing config + `narration_pace` helper

**Files:**
- Modify: `engine/config.py` (near line 93, the `NARRATION_SPEED`/`NARRATION_GAP_S` block)
- Modify: `engine/video/tts.py` (add helper near `mood_for_pillar`, ~line 140)
- Test: `tests/test_tts.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tts.py`:

```python
def test_narration_pace_short_is_brisk_and_tight():
    from engine.video import tts
    from engine import config
    speed, gap = tts.narration_pace("short")
    assert speed == config.SHORT_NARRATION_SPEED
    assert gap == config.SHORT_NARRATION_GAP_S
    assert speed > config.NARRATION_SPEED      # brisker than long-form
    assert gap < config.NARRATION_GAP_S        # tighter pauses than long-form


def test_narration_pace_long_uses_calm_defaults():
    from engine.video import tts
    from engine import config
    assert tts.narration_pace("long") == (config.NARRATION_SPEED, config.NARRATION_GAP_S)
    # unknown/None format defaults to long-form (calm)
    assert tts.narration_pace(None) == (config.NARRATION_SPEED, config.NARRATION_GAP_S)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tts.py::test_narration_pace_short_is_brisk_and_tight -v`
Expected: FAIL — `AttributeError: module 'engine.config' has no attribute 'SHORT_NARRATION_SPEED'` (or `tts has no attribute 'narration_pace'`).

- [ ] **Step 3: Add the config knobs**

In `engine/config.py`, directly below the existing lines:

```python
NARRATION_SPEED = 0.9            # kokoro speed; <1.0 = slower, calmer
NARRATION_GAP_S = 0.5           # silence between sentences (seconds)
```

add:

```python
# Short-form is brisker and tighter than the cinematic long-form pace above — TikTok/Reels
# give you ~2s before a swipe, so we cut the calm. Long-form keeps the values above.
SHORT_NARRATION_SPEED = 1.12     # noticeably brisk, still clear (vs 0.9 long-form)
SHORT_NARRATION_GAP_S = 0.12     # near-eliminate the dramatic pauses (vs 0.5)
```

- [ ] **Step 4: Add the helper**

In `engine/video/tts.py`, after `mood_for_pillar` (~line 142):

```python
def narration_pace(fmt: str | None) -> tuple[float, float]:
    """(speed, gap_s) for kokoro narration by output format. 'short' is brisk + tight;
    anything else (long/None) keeps the calm cinematic defaults."""
    if fmt == "short":
        return config.SHORT_NARRATION_SPEED, config.SHORT_NARRATION_GAP_S
    return config.NARRATION_SPEED, config.NARRATION_GAP_S
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tts.py -q`
Expected: PASS (all tts tests).

- [ ] **Step 6: Commit**

```bash
git add engine/config.py engine/video/tts.py tests/test_tts.py
git commit -m "feat(short): brisk short-only narration pace + narration_pace helper"
```

---

## Task 2: Wire short pace into the render path

**Files:**
- Modify: `engine/run_video.py` (the narrated-mode synth call, ~line 85-89)

No new unit test (the synth call shells into Kokoro; the helper is already covered by Task 1). Verified by the final re-render.

- [ ] **Step 1: Pass the format-derived pace to `synthesize`**

In `engine/run_video.py`, find (~line 85-89):

```python
            narration_text = tts.apply_pronunciation(tts.script_to_narration_text(script_md))
            ...
                voice = tts.narration_voice(idea, override=args.voice, provider=provider)
                tts.synthesize(narration_text, audio_path, provider=args.tts, voice=voice)
```

Change the `synthesize` call to:

```python
                voice = tts.narration_voice(idea, override=args.voice, provider=provider)
                speed, gap_s = tts.narration_pace(args.format)
                tts.synthesize(narration_text, audio_path, provider=args.tts, voice=voice,
                               speed=speed, gap_s=gap_s)
```

(`synthesize` already accepts `speed` / `gap_s`; they are no-ops for the macOS `say` provider, which is the intended fallback behaviour.)

- [ ] **Step 2: Run the suite (hook runs it too)**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (no regressions).

- [ ] **Step 3: Commit**

```bash
git add engine/run_video.py
git commit -m "feat(short): render path narrates shorts at the brisk short pace"
```

---

## Task 3: Mood → atmospheric pool + per-beat query builder

**Files:**
- Modify: `engine/config.py` (new `MOOD_BROLL_POOL` near the other mood tables, ~line 105 `PILLAR_MOOD`)
- Modify: `engine/video/footage.py` (add `mood_beat_queries`)
- Test: `tests/test_footage.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_footage.py`:

```python
def test_mood_beat_queries_draws_from_the_mood_pool():
    from engine.video import footage
    from engine import config
    qs = footage.mood_beat_queries("somber", 3)
    assert len(qs) == 3
    assert set(qs) <= set(config.MOOD_BROLL_POOL["somber"])


def test_mood_beat_queries_varies_no_immediate_repeat():
    from engine.video import footage
    qs = footage.mood_beat_queries("triumphant", 5)
    assert len(qs) == 5
    assert all(qs[i] != qs[i + 1] for i in range(len(qs) - 1)), f"immediate repeat: {qs}"


def test_mood_beat_queries_cycles_when_n_exceeds_pool():
    from engine.video import footage
    from engine import config
    n = len(config.MOOD_BROLL_POOL["tense"]) + 2
    qs = footage.mood_beat_queries("tense", n)
    assert len(qs) == n  # cycles the pool rather than running out


def test_mood_beat_queries_unknown_mood_falls_back():
    from engine.video import footage
    qs = footage.mood_beat_queries("", 4)         # empty/unknown mood
    assert len(qs) == 4 and all(isinstance(q, str) and q for q in qs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_footage.py::test_mood_beat_queries_draws_from_the_mood_pool -v`
Expected: FAIL — `AttributeError: ... no attribute 'MOOD_BROLL_POOL'`.

- [ ] **Step 3: Add the mood pool to config**

In `engine/config.py`, after the `PILLAR_MOOD` table:

```python
# Atmospheric b-roll search terms per mood. Purely symbolic/abstract (nature, sky, weather,
# space, texture) — zero integrity risk (never implies real event footage). Each pool has
# enough terms that beat-level selection + the global used_clips.json dedup yields a fresh
# clip per beat. Keys match the four canonical MOODS (tense/triumphant/somber/hype).
MOOD_BROLL_POOL = {
    "somber": ["rain on window", "grey ocean waves", "dusk fog forest", "empty road night",
               "falling snow slow", "still misty lake", "dark clouds drifting", "candle flame dark"],
    "triumphant": ["sunrise over clouds", "light rays forest", "open blue sky", "mountain summit",
                   "golden hour ocean", "soaring birds sky", "sun flare horizon", "aurora night sky"],
    "tense": ["storm clouds timelapse", "lightning strike", "crashing waves rocks", "dark smoke",
              "fast moving clouds", "flickering light dark", "rough sea storm", "wind grass field"],
    "hype": ["city lights night", "neon lights motion", "fireworks night", "highway traffic timelapse",
             "fast city motion", "abstract energy light", "crowd lights blur", "spinning star trails"],
}
```

- [ ] **Step 4: Add the builder to footage.py**

In `engine/video/footage.py` (after `_sport_query`, ~line 55):

```python
from engine import config as _config

def mood_beat_queries(mood: str | None, n: int) -> list[str]:
    """n atmospheric search queries for the given mood, cycling the pool so consecutive
    beats differ. Unknown/empty mood falls back to 'tense'. Deterministic (no RNG) — the
    per-clip variety comes from footage.fetch_clips' dedup, not from query randomness."""
    pool = _config.MOOD_BROLL_POOL.get(mood or "", _config.MOOD_BROLL_POOL["tense"])
    return [pool[i % len(pool)] for i in range(n)]
```

(If `footage.py` already imports config under another name, reuse that name instead of adding a second import.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_footage.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/config.py engine/video/footage.py tests/test_footage.py
git commit -m "feat(broll): mood-driven atmospheric query pool + per-beat query builder"
```

---

## Task 4: Beat-track builder

**Files:**
- Modify: `engine/video/remotion_build.py` (add `beat_track` near top, after imports)
- Test: `tests/test_remotion_build.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_remotion_build.py`:

```python
import math
from engine.video import remotion_build


def test_beat_track_covers_narration_contiguously():
    beats = remotion_build.beat_track(10_000, 2.5)   # 10s narration, 2.5s beats
    assert len(beats) == 4
    assert beats[0]["startMs"] == 0
    # contiguous, non-overlapping
    for a, b in zip(beats, beats[1:]):
        assert a["endMs"] == b["startMs"]
    # last beat reaches the end of the narration
    assert beats[-1]["endMs"] == 10_000


def test_beat_track_rounds_up_partial_final_beat():
    beats = remotion_build.beat_track(9_000, 2.5)     # 9 / 2.5 = 3.6 → 4 beats
    assert len(beats) == math.ceil(9_000 / 2_500)
    assert beats[-1]["endMs"] == 9_000                # clamped to narration end


def test_beat_track_long_cadence_is_coarser():
    short_beats = remotion_build.beat_track(60_000, 2.5)
    long_beats = remotion_build.beat_track(60_000, 7.0)
    assert len(short_beats) > len(long_beats)         # short cuts more often
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_remotion_build.py::test_beat_track_covers_narration_contiguously -v`
Expected: FAIL — `AttributeError: ... no attribute 'beat_track'`.

- [ ] **Step 3: Implement `beat_track`**

In `engine/video/remotion_build.py`, after the imports / constants (after `OUTRO_MS = 3500`):

```python
import math


def beat_track(narration_ms: int, beat_s: float) -> list[dict]:
    """Split a narration of `narration_ms` into contiguous b-roll beats of ~`beat_s`
    seconds each. Returns [{"startMs", "endMs"}, ...]; the final beat is clamped to
    narration_ms. One clip will be fetched per beat (no single-clip loop)."""
    if narration_ms <= 0 or beat_s <= 0:
        return [{"startMs": 0, "endMs": max(0, narration_ms)}]
    beat_ms = int(round(beat_s * 1000))
    n = max(1, math.ceil(narration_ms / beat_ms))
    beats = []
    for i in range(n):
        start = i * beat_ms
        end = min((i + 1) * beat_ms, narration_ms)
        beats.append({"startMs": start, "endMs": end})
    return beats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_remotion_build.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/video/remotion_build.py tests/test_remotion_build.py
git commit -m "feat(broll): contiguous beat-track builder for b-roll cadence"
```

---

## Task 5: Emit `bBeats` from `build_props` (mood pool + zoom + per-beat fetch)

**Files:**
- Modify: `engine/video/remotion_build.py` (`build_props`)
- Modify: `engine/run_video.py` (pass `broll_beat_s` by format)
- Modify: `engine/config.py` (beat cadence constants)
- Test: `tests/test_remotion_build.py`

- [ ] **Step 1: Add cadence constants to config**

In `engine/config.py`, just below the `MOOD_BROLL_POOL` block:

```python
SHORT_BROLL_BEAT_S = 2.5    # short: a new atmospheric clip every ~2.5s (TikTok energy)
LONG_BROLL_BEAT_S = 7.0     # long: every ~7s — varied but cinematic, no single-clip loop
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_remotion_build.py`:

```python
def test_build_props_emits_bbeats_from_mood_pool(tmp_path, monkeypatch):
    from engine.video import remotion_build, footage, music
    from engine import config

    # Neutralize heavy/network helpers; capture the queries footage receives.
    captured = {}
    def _fake_fetch(queries, vd, portrait=False, sport=None):
        captured["queries"] = list(queries)
        captured["sport"] = sport
        return [f"bg_{i:02d}.mp4" for i in range(len(queries))]   # every beat gets a clip

    monkeypatch.setattr(remotion_build._tts, "script_to_narration_text", lambda md: "w w w")
    monkeypatch.setattr(remotion_build._captions, "estimate_word_timings",
                        lambda text, dur: [{"text": "w", "startMs": 0, "endMs": 500}])
    monkeypatch.setattr(remotion_build._compose, "build_section_headlines", lambda idea, md: [])
    monkeypatch.setattr(remotion_build._compose, "assign_headline_times", lambda s, w, d, n: [])
    monkeypatch.setattr(remotion_build._footage, "fetch_clips", _fake_fetch)
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))

    idea = {"id": "i1", "mood": "somber", "pillar": "hidden_story", "title_variants": ["T"],
            "sport": "Soccer"}
    props, assets, credit = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0, broll_beat_s=2.5)

    # 10s / 2.5s = 4 beats → 4 bBeats, each with a src + contiguous timing + alternating zoom.
    beats = props["bBeats"]
    assert len(beats) == 4
    assert [b["zoomDir"] for b in beats] == ["in", "out", "in", "out"]
    assert all(b["src"] for b in beats)
    assert beats[0]["startMs"] == 0 and beats[-1]["endMs"] == 10_000
    # queries came from the somber mood pool, generic (sport not biased in)
    assert set(captured["queries"]) <= set(config.MOOD_BROLL_POOL["somber"])
    assert captured["sport"] is None


def test_build_props_bbeats_mood_falls_back_to_pillar(tmp_path, monkeypatch):
    from engine.video import remotion_build, footage, music
    from engine import config

    monkeypatch.setattr(remotion_build._tts, "script_to_narration_text", lambda md: "w")
    monkeypatch.setattr(remotion_build._captions, "estimate_word_timings",
                        lambda text, dur: [{"text": "w", "startMs": 0, "endMs": 500}])
    monkeypatch.setattr(remotion_build._compose, "build_section_headlines", lambda idea, md: [])
    monkeypatch.setattr(remotion_build._compose, "assign_headline_times", lambda s, w, d, n: [])
    grabbed = {}
    def _fake_fetch(queries, vd, portrait=False, sport=None):
        grabbed["queries"] = list(queries)
        return [None for _ in queries]      # no clips available → graceful
    monkeypatch.setattr(remotion_build._footage, "fetch_clips", _fake_fetch)
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))

    # No idea["mood"] → derive from pillar via tts.mood_for_pillar.
    pillar = next(iter(config.PILLAR_MOOD))
    expected_mood = config.PILLAR_MOOD[pillar]
    idea = {"id": "i2", "pillar": pillar, "title_variants": ["T"]}
    props, _, _ = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 5.0, broll_beat_s=7.0)

    assert set(grabbed["queries"]) <= set(config.MOOD_BROLL_POOL[expected_mood])
    # beats with no clip omit src but keep timing (gradient shows through, never crashes)
    assert props["bBeats"][0]["src"] is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_remotion_build.py::test_build_props_emits_bbeats_from_mood_pool -v`
Expected: FAIL — `build_props() got an unexpected keyword argument 'broll_beat_s'` (then `KeyError: 'bBeats'`).

- [ ] **Step 4: Rework `build_props`**

In `engine/video/remotion_build.py`, change the signature to add `broll_beat_s`:

```python
def build_props(idea: dict, script_md: str, video_dir: str, audio_filename: str,
                words: list[dict] | None, total_dur: float, fps: int = 30,
                width: int = 1920, height: int = 1080,
                portrait: bool = False,
                intro_ms: int = INTRO_MS, outro_ms: int = OUTRO_MS,
                broll_beat_s: float = LONG_BROLL_BEAT_S) -> tuple[dict, list[str]]:
```

Replace the chapter-clip block (current lines ~47-63, from `# One atmospheric Pexels clip per chapter` through the `chapters.append(ch)` loop) with **headline-only chapters + a beat-driven b-roll track**:

```python
    # Chapters are headline cards only now (long-form). B-roll is a separate beat track.
    chapters = [{"headline": h["headline"],
                 "startMs": int(round(h["start"] * 1000)),
                 "endMs": int(round(h["end"] * 1000))}
                for h in heads]

    # B-roll beat track: a NEW deduped atmospheric clip per beat (no single-clip loop).
    # Mood drives the pool (short: from the script's MOOD line, persisted on idea["mood"];
    # long: pillar-derived). Generic atmospheric → sport bias intentionally off.
    narration_ms = int(round(total_dur * 1000))
    beats = beat_track(narration_ms, broll_beat_s)
    mood = idea.get("mood") or _tts.mood_for_pillar(idea.get("pillar"))
    beat_queries = _footage.mood_beat_queries(mood, len(beats))
    beat_clips = _footage.fetch_clips(beat_queries, video_dir, portrait=portrait, sport=None)

    b_beats, assets = [], []
    for i, (beat, clip) in enumerate(zip(beats, beat_clips)):
        b_beats.append({
            "startMs": beat["startMs"],
            "endMs": beat["endMs"],
            "src": os.path.basename(clip) if clip else None,
            "zoomDir": "in" if i % 2 == 0 else "out",
        })
        if clip:
            assets.append(clip)
```

Then add `bBeats` to the `props` dict (keep `chapters` as-is):

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
        "narrationMs": narration_ms,
        "captions": cap_words,
        "chapters": chapters,
        "bBeats": b_beats,
    }
```

(The music block below it is unchanged. Note `narrationMs` now reuses the `narration_ms` local.)

- [ ] **Step 5: Pass cadence by format in run_video**

In `engine/run_video.py`, the `build_props(...)` call (~line 106-112) — add the `broll_beat_s` argument:

```python
        props, assets, music_credit = remotion_build.build_props(
            ...,
            portrait=is_short,
            intro_ms=(0 if is_short else remotion_build.INTRO_MS),
            outro_ms=(2500 if is_short else remotion_build.OUTRO_MS),
            broll_beat_s=(config.SHORT_BROLL_BEAT_S if is_short else config.LONG_BROLL_BEAT_S),
        )
```

Ensure `from engine import config` is present in `run_video.py` (add it to the imports if missing).

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS. (Watch `test_remotion_build.py` — the older `test_build_props_*` tests should still pass; `build_props` still returns `(props, assets, credit)` and still adds music.)

- [ ] **Step 7: Commit**

```bash
git add engine/config.py engine/video/remotion_build.py engine/run_video.py tests/test_remotion_build.py
git commit -m "feat(broll): build_props emits a mood-driven bBeats track (per-format cadence)"
```

---

## Task 6: Remotion — render the `bBeats` track (hard cut + Ken-Burns zoom)

**Files:**
- Modify: `engine/video/remotion/src/types.ts`
- Modify: `engine/video/remotion/src/components/Background.tsx`
- Modify: `engine/video/remotion/src/UntoldShort.tsx`, `engine/video/remotion/src/UntoldVideo.tsx`

No pytest. Verify with `npx tsc --noEmit` in the remotion dir, then the final render.

- [ ] **Step 1: Extend the props schema**

In `engine/video/remotion/src/types.ts`, add the beat type and field:

```typescript
export type BBeat = {
  startMs: number;       // relative to narration start
  endMs: number;
  src?: string | null;   // filename in public/ (atmospheric clip); null/omitted → gradient shows through
  zoomDir: 'in' | 'out'; // Ken-Burns direction for this beat
};
```

and add to `UntoldProps`:

```typescript
  bBeats?: BBeat[];      // beat-level b-roll track; preferred over per-chapter `chapters[].bClip`
```

- [ ] **Step 2: Render `bBeats` in Background.tsx**

In `engine/video/remotion/src/components/Background.tsx`, change the component signature to accept `bBeats` and render the beat track when present, else fall back to the existing chapter loop. Replace the component definition:

```tsx
export const Background: React.FC<{chapters: Chapter[]; introMs: number; bBeats?: BBeat[]}> = ({
  chapters,
  introMs,
  bBeats,
}) => {
  const {fps} = useVideoConfig();
  const introF = ms2f(introMs, fps);

  return (
    <AbsoluteFill>
      <GradientField />

      {bBeats && bBeats.length > 0
        ? bBeats.map((b, i) => {
            if (!b.src) return null;                       // gradient shows through this beat
            const from = i === 0 ? 0 : introF + ms2f(b.startMs, fps);
            const to = introF + ms2f(b.endMs, fps);
            const dur = Math.max(1, to - from);
            return (
              <Sequence key={i} from={from} durationInFrames={dur} name={`beat ${i + 1}`}>
                <BeatClip src={b.src} durationInFrames={dur} zoomDir={b.zoomDir} />
              </Sequence>
            );
          })
        : chapters.map((c, i) => {
            if (!c.bClip) return null;
            const from = i === 0 ? 0 : introF + ms2f(c.startMs, fps);
            const to = introF + ms2f(c.endMs, fps);
            const dur = Math.max(1, to - from);
            const clipF = c.bClipMs ? Math.max(1, ms2f(c.bClipMs, fps)) : dur;
            return (
              <Sequence key={i} from={from} durationInFrames={dur} name={`bg ${i + 1}`}>
                <Fade durationInFrames={dur}>
                  <AbsoluteFill style={{filter: 'brightness(1.22) contrast(1.03) sepia(0.18) saturate(1.18) hue-rotate(-6deg)'}}>
                    <Loop durationInFrames={clipF}>
                      <OffthreadVideo
                        src={staticFile(c.bClip)}
                        muted
                        style={{width: '100%', height: '100%', objectFit: 'cover'}}
                      />
                    </Loop>
                  </AbsoluteFill>
                </Fade>
              </Sequence>
            );
          })}

      {/* light vignette + bottom-weighted scrim (unchanged) */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle at 50% 44%, rgba(0,0,0,0) 46%, rgba(20,11,3,0.30) 100%)',
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(8,7,5,0.28) 0%, rgba(8,7,5,0) 24%, rgba(8,7,5,0) 60%, rgba(8,7,5,0.55) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};
```

Add the `BeatClip` helper (hard cut = very short 3-frame crossfade to avoid black flash; Ken-Burns scale across the beat) above `Background`, after `Fade`:

```tsx
// A single b-roll beat: hard cut in (tiny 3-frame fade so there's no black flash), looped
// to fill the beat, with a slow Ken-Burns zoom in the beat's direction.
const BeatClip: React.FC<{src: string; durationInFrames: number; zoomDir: 'in' | 'out'}> = ({
  src,
  durationInFrames,
  zoomDir,
}) => {
  const f = useCurrentFrame();
  const fadeF = Math.min(3, Math.max(1, Math.floor(durationInFrames / 2)));
  const opacity = interpolate(f, [0, fadeF], [0, 1], {extrapolateRight: 'clamp'});
  const p = durationInFrames > 1 ? f / (durationInFrames - 1) : 0;
  const scale = zoomDir === 'in'
    ? interpolate(p, [0, 1], [1.0, 1.08], {extrapolateRight: 'clamp'})
    : interpolate(p, [0, 1], [1.08, 1.0], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{opacity}}>
      <AbsoluteFill
        style={{
          filter: 'brightness(1.22) contrast(1.03) sepia(0.18) saturate(1.18) hue-rotate(-6deg)',
          transform: `scale(${scale})`,
        }}
      >
        <Loop durationInFrames={durationInFrames}>
          <OffthreadVideo
            src={staticFile(src)}
            muted
            style={{width: '100%', height: '100%', objectFit: 'cover'}}
          />
        </Loop>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
```

Update the import of types at the top of `Background.tsx` to include `BBeat`:

```tsx
import type {Chapter, BBeat} from '../types';
```

- [ ] **Step 3: Pass `bBeats` from both compositions**

In `engine/video/remotion/src/UntoldShort.tsx`, change:

```tsx
      <Background chapters={props.chapters} introMs={props.introMs} />
```
to:
```tsx
      <Background chapters={props.chapters} introMs={props.introMs} bBeats={props.bBeats} />
```

In `engine/video/remotion/src/UntoldVideo.tsx`, find the `<Background ... />` usage and add `bBeats={props.bBeats}` the same way (keep its existing `chapters`/`introMs` props).

- [ ] **Step 4: Typecheck the Remotion project**

Run:
```bash
cd engine/video/remotion && npx tsc --noEmit; cd -
```
Expected: no type errors. (If the project has an `npm run lint`, run that too.)

- [ ] **Step 5: Commit**

```bash
git add engine/video/remotion/src/types.ts engine/video/remotion/src/components/Background.tsx engine/video/remotion/src/UntoldShort.tsx engine/video/remotion/src/UntoldVideo.tsx
git commit -m "feat(render): beat-level b-roll with hard cut + Ken-Burns zoom (bBeats)"
```

---

## Task 7: Sharpen the short hook prompts

**Files:**
- Modify: `engine/pipeline/script.py` (`SHORT_SYSTEM` ~line 98, `DERIVE_TEASE_SYSTEM` ~line 225)
- Test: `tests/test_script.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_script.py`:

```python
def test_short_system_prompt_front_loads_conflict():
    from engine.pipeline import script
    s = script.SHORT_SYSTEM.lower()
    # conflict-first, with specifics deferred to the FACT beat
    assert "first line" in s
    assert "eight words" in s or "≤ 8" in s or "8 words" in s
    assert "fact beat" in s
    # explicit ban on atmosphere/scene-setting openers
    assert "atmosphere" in s or "scene-setting" in s
    # integrity preserved (no rounding)
    assert "never round" in s


def test_derive_tease_prompt_front_loads_conflict():
    from engine.pipeline import script
    s = script.DERIVE_TEASE_SYSTEM.lower()
    assert "first line" in s
    assert "eight words" in s or "8 words" in s
    assert "atmosphere" in s or "scene-setting" in s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_script.py::test_short_system_prompt_front_loads_conflict -v`
Expected: FAIL — assertion (the phrases aren't in the prompt yet).

- [ ] **Step 3: Update `SHORT_SYSTEM`**

In `engine/pipeline/script.py`, replace the HOOK bullet in `SHORT_SYSTEM` (the bullet starting `- HOOK: front-load the mystery, not the data.`) with:

```
- HOOK: the FIRST line must hit the central conflict or mystery in EIGHT WORDS OR FEWER,
  payoff-forward — the turn, the loss, the vanishing ("Then he just walked away."). It is the
  scroll-stopper; the viewer gives you ~2 seconds. NO atmosphere or scene-setting opener
  ("He was a king in exile…", "It was a cold night…"), no throat-clearing, no "in this video".
  Carry NO specific number, name, or date in the hook — those land in the FACT beat one line
  later. If a specific must appear it is the exact verified value: never round (1,457, never
  ~1,500), never assert a superlative as fact ("the greatest ... ever") unless attributed or
  defensibly hedged ("of his generation").
```

- [ ] **Step 4: Update `DERIVE_TEASE_SYSTEM`**

In the same file, replace the HOOK bullet in `DERIVE_TEASE_SYSTEM` (starting `- HOOK: front-load the mystery, not the data`) with:

```
- HOOK: the FIRST line must hit the central conflict or mystery in EIGHT WORDS OR FEWER,
  payoff-forward — the scroll-stopper, since the viewer gives you ~2 seconds. NO atmosphere or
  scene-setting opener, no throat-clearing. Carry NO specific number, name, or date in the hook
  — those land in the FACT beat. If a specific must appear it is the exact verified value: never
  round, never assert a superlative as fact unless attributed/defensibly hedged.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_script.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/pipeline/script.py tests/test_script.py
git commit -m "feat(short): conflict-first ≤8-word hook prompt (integrity held)"
```

---

## Task 8: Caption page punch-in (shorts only)

**Files:**
- Modify: `engine/video/remotion/src/components/ShortCaptions.tsx`

No pytest (TSX). The per-token spring/scale already exists; this adds a subtle page-level scale pop on each new caption page so the *block* punches in, not just individual words. Verify via `npx tsc --noEmit` + render.

- [ ] **Step 1: Add a page-entrance scale to the caption block**

In `ShortCaptions.tsx`, after `pageOpacity` is computed (~line 54), add a page-entrance scale driven by a spring on `intoPage`:

```tsx
  // Page-level punch: the whole block springs in slightly on each new caption page —
  // a pattern interrupt on top of the per-word animation below.
  const intoPageF = (intoPage / 1000) * fps;
  const pagePop = spring({frame: intoPageF, fps, config: {damping: 14, mass: 0.4, stiffness: 200}});
  const pageScale = 0.96 + 0.04 * Math.min(pagePop, 1);
```

Then apply it to the caption block wrapper `<div style={{...}}>` (the one at ~line 78 with `top: blockTop`) — add to its style object:

```tsx
          transform: `scale(${pageScale})`,
          transformOrigin: 'center center',
```

(Keep `opacity: pageOpacity` and the existing properties.)

- [ ] **Step 2: Typecheck**

Run:
```bash
cd engine/video/remotion && npx tsc --noEmit; cd -
```
Expected: no type errors.

- [ ] **Step 3: Commit**

```bash
git add engine/video/remotion/src/components/ShortCaptions.tsx
git commit -m "feat(short): page-level caption punch-in"
```

---

## Task 9: Proof — re-produce + re-render the Cantona short

**Files:** none (verification task).

- [ ] **Step 1: Re-produce the script with the new hook prompt**

Run: `python3 -m engine.run_produce --id 25051da8 --format short`
Expected: a new `produced/25051da8/short/script.md` with a conflict-first ≤8-word opening line. If the fact-gate flags it `needs_review`, run the `fact-review` skill (verify vs an authoritative source, fix only real errors) before rendering — same discipline as before.

- [ ] **Step 2: Clear to render (if it went needs_review)**

Run: `python3 -m engine.run_auto --review 25051da8 --note "fact-reviewed; short-form v2 re-cut"`

- [ ] **Step 3: Render via the video venv**

Run: `.venv-video/bin/python -m engine.run_video --id 25051da8 --render --mode narrated --format short`
Expected: exit 0; `produced/25051da8/short/video/video.mp4` finalized (probe shows duration + `moov` atom present — re-probe after the process exits, not mid-mux).

- [ ] **Step 4: QC**

Run:
```bash
.venv-video/bin/python -c "from engine.pipeline import qc, json; print(json.dumps(qc.qc_video('25051da8','short'),indent=2))"
```
Expected: `passed: true` (render_integrity, brightness, caption_coverage).

- [ ] **Step 5: Eyeball vs baseline**

Run: `open produced/25051da8/short/video/video.mp4`
Confirm: conflict-first hook in ~2s, brisk delivery, a new atmospheric clip every ~2.5s with a slow zoom (no single-clip loop), caption punch-in. Compare against the saved baseline render.

---

## Ship (after all tasks pass)

Per `ship-video-change`: `pytest tests/ -q` green + dual adversarial review (Codex + Claude), then a PR with the `Adversarial-Reviewed:` trailer, squash-merge. This is an `engine/*.py` change, so the trailer is required (not a docs bypass).

---

## Self-Review (done at write time)

- **Spec coverage:** A-hook → Task 7; B-pacing → Tasks 1-2; C-mood pool → Task 3, beat track → Task 4, bBeats+zoom → Tasks 5-6; D-caption punch → Task 8; proof → Task 9. All spec sections mapped.
- **Type consistency:** `narration_pace(fmt)`, `mood_beat_queries(mood, n)`, `beat_track(narration_ms, beat_s)`, `build_props(..., broll_beat_s=)`, props key `bBeats`, TS `BBeat{startMs,endMs,src?,zoomDir}` — names match across Python emit (Task 5) and TSX consume (Task 6). `zoomDir` values `"in"|"out"` consistent.
- **No placeholders:** every code step shows the actual code; every test step shows the assertions and the exact command + expected result.
- **Risk note:** Task 5 removes per-chapter b-roll fetching; long-form background now also comes from `bBeats`. `Background` keeps the `bClip` fallback for any props lacking `bBeats`, so no composition breaks if an older props.json is rendered.
