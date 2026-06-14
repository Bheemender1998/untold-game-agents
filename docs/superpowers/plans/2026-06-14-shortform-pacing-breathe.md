# Short-form Pacing "Let It Breathe" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make YouTube Shorts feel less hurried and end on a beat that lands — slower read, a longer pause before the payoff, a ~1s hold before the subscribe card, and a fuller closing line — all gated to `format == short` so long-form is untouched.

**Architecture:** Four coordinated changes across config, the TTS layer, the Remotion render layer, and the short script prompts. Each new behavior is keyed off a new config knob that defaults to current behavior for long-form. The gap-assembly logic is extracted into a pure, unit-testable helper.

**Tech Stack:** Python 3 (`engine/`), kokoro-onnx TTS, Remotion (TypeScript/React) render, pytest.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `engine/config.py` | Pacing knobs | Modify 2 values, add 2 constants |
| `engine/video/tts.py` | Narration synthesis | New pure `_gap_schedule`, thread `end_gap_s` |
| `engine/run_video.py` | Render orchestration | Pass `end_gap_s` + `end_hold_ms` for shorts |
| `engine/video/remotion_build.py` | Build Remotion props | New `end_hold_ms` param → `props["endHoldMs"]` |
| `engine/video/remotion/src/types.ts` | Props type | Add optional `endHoldMs` |
| `engine/video/remotion/src/Root.tsx` | Composition duration | Add `endHoldMs` to total |
| `engine/video/remotion/src/UntoldShort.tsx` | Short composition | Hold before EndCTA; music length |
| `engine/video/remotion/src/shortDefaultProps.ts` | Still-preview defaults | Add `endHoldMs` |
| `engine/pipeline/script.py` | Short script prompts | Fuller PAYOFF beat (both writers) |
| `tests/test_tts.py` | TTS tests | Update pace tests, add gap-schedule test |
| `tests/test_remotion_build.py` | Props tests | Add `endHoldMs` tests |
| `tests/test_script.py` | Prompt tests | Add PAYOFF-wording test (create if absent) |

**Contract:** after editing any `engine/**.py`, run `python3 -m pytest tests/ -q` (the PostToolUse hook also runs it). All commands use `python3`, never `python`.

---

### Task 1: Config pacing knobs

**Files:**
- Modify: `engine/config.py:97-102`

- [ ] **Step 1: Update the short pacing constants**

In `engine/config.py`, change lines 101-102 and add two new constants directly after them. Current:

```python
SHORT_NARRATION_SPEED = 1.12     # noticeably brisk, still clear (vs 0.9 long-form)
SHORT_NARRATION_GAP_S = 0.12     # near-eliminate the dramatic pauses (vs 0.5)
```

Replace with:

```python
SHORT_NARRATION_SPEED = 1.05     # brisk but no longer breathless (was 1.12; vs 0.9 long-form)
SHORT_NARRATION_GAP_S = 0.20     # short pauses, room to breathe (was 0.12; vs 0.5 long-form)
SHORT_END_GAP_S = 0.6            # longer silence BEFORE the final (payoff) sentence so it lands apart from the facts
SHORT_END_HOLD_MS = 1000         # hold the last story shot + music this long before the subscribe card (the "end breath")
```

- [ ] **Step 2: Run the existing pace tests to confirm they still pass**

Run: `python3 -m pytest tests/test_tts.py -q -k narration_pace`
Expected: PASS (the existing assertions `speed > NARRATION_SPEED` → `1.05 > 0.9` and `gap < NARRATION_GAP_S` → `0.20 < 0.5` still hold).

- [ ] **Step 3: Commit**

```bash
git add engine/config.py
git commit -m "feat(short): slow narration + add end-gap/end-hold pacing knobs"
```

---

### Task 2: TTS — longer pause before the payoff sentence

**Files:**
- Modify: `engine/video/tts.py:187-192` (`narration_pace`), `:223-235` (`synthesize`), `:278-308` (`_synth_kokoro`)
- Modify: `engine/run_video.py:90-92`
- Test: `tests/test_tts.py`

- [ ] **Step 1: Write the failing test for the pure gap-schedule helper**

Add to `tests/test_tts.py`:

```python
def test_gap_schedule_enlarges_pause_before_final_sentence():
    from engine.video import tts
    # 4 sentences, normal gap 0.2, end gap 0.6 → the gap AFTER sentence index 2
    # (i.e. the one that PRECEDES the final sentence index 3) is the long one.
    assert tts._gap_schedule(4, 0.2, 0.6) == [0.2, 0.2, 0.6, 0.2]


def test_gap_schedule_none_end_gap_is_uniform():
    from engine.video import tts
    # long-form (end_gap_s=None) keeps every gap identical — no behavior change.
    assert tts._gap_schedule(4, 0.5, None) == [0.5, 0.5, 0.5, 0.5]


def test_gap_schedule_single_sentence_has_no_preceding_gap():
    from engine.video import tts
    assert tts._gap_schedule(1, 0.2, 0.6) == [0.2]
    assert tts._gap_schedule(0, 0.2, 0.6) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_tts.py -q -k gap_schedule`
Expected: FAIL with `AttributeError: module 'engine.video.tts' has no attribute '_gap_schedule'`

- [ ] **Step 3: Add the pure helper to `engine/video/tts.py`**

Add directly above `_synth_kokoro` (before line 278):

```python
def _gap_schedule(n: int, gap_s: float, end_gap_s: float | None) -> list[float]:
    """Silence (seconds) to append AFTER each of `n` sentences. When `end_gap_s` is set
    and there are >=2 sentences, the gap that PRECEDES the final sentence (i.e. the one
    after sentence n-2) is enlarged to `end_gap_s` so the payoff lands set apart from the
    facts. `end_gap_s=None` (long-form) keeps every gap uniform — no behavior change."""
    gaps = [gap_s] * n
    if end_gap_s is not None and n >= 2:
        gaps[n - 2] = end_gap_s
    return gaps
```

- [ ] **Step 4: Run to verify the helper tests pass**

Run: `python3 -m pytest tests/test_tts.py -q -k gap_schedule`
Expected: PASS

- [ ] **Step 5: Wire the helper into `_synth_kokoro` and thread `end_gap_s`**

Change the signature at line 278 from:

```python
                  speed: float | None = None, gap_s: float | None = None) -> str:
```

to:

```python
                  speed: float | None = None, gap_s: float | None = None,
                  end_gap_s: float | None = None) -> str:
```

Then replace the synthesis loop (current lines 296-304):

```python
    sample_rate = 24000
    gap = np.zeros(int(gap_s * sample_rate), dtype=np.float32)   # pause between sentences
    chunks: list = []
    for sent in _split_sentences(text):
        samples, sr = kokoro.create(sent, voice=voice, speed=speed, lang="en-us")
        sample_rate = sr
        chunks.append(np.asarray(samples, dtype=np.float32))
        chunks.append(gap)
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
```

with:

```python
    sample_rate = 24000
    sents = _split_sentences(text)
    gaps = _gap_schedule(len(sents), gap_s, end_gap_s)   # longer pause before the payoff (short only)
    chunks: list = []
    for sent, g in zip(sents, gaps):
        samples, sr = kokoro.create(sent, voice=voice, speed=speed, lang="en-us")
        sample_rate = sr
        chunks.append(np.asarray(samples, dtype=np.float32))
        chunks.append(np.zeros(int(g * sample_rate), dtype=np.float32))
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
```

- [ ] **Step 6: Thread `end_gap_s` through `synthesize`**

In `engine/video/tts.py`, change `synthesize` signature (lines 223-225) from:

```python
def synthesize(text: str, out_path: str, provider: str | None = None,
               voice: str | None = None, speed: float | None = None,
               gap_s: float | None = None) -> str:
```

to:

```python
def synthesize(text: str, out_path: str, provider: str | None = None,
               voice: str | None = None, speed: float | None = None,
               gap_s: float | None = None, end_gap_s: float | None = None) -> str:
```

And change the kokoro dispatch (line 233) from:

```python
        return _synth_kokoro(text, out_path, voice, speed, gap_s)
```

to:

```python
        return _synth_kokoro(text, out_path, voice, speed, gap_s, end_gap_s)
```

(The `say` provider ignores `end_gap_s` — no change there.)

- [ ] **Step 7: Make `narration_pace` return the end-gap; update its tests**

Change `narration_pace` (lines 187-192) to:

```python
def narration_pace(fmt: str | None) -> tuple[float, float, float | None]:
    """(speed, gap_s, end_gap_s) for kokoro narration by output format. 'short' is brisk +
    tight with a longer pause before the payoff; long/None keep the calm cinematic defaults
    and a uniform gap (end_gap_s=None)."""
    if fmt == "short":
        return (config.SHORT_NARRATION_SPEED, config.SHORT_NARRATION_GAP_S,
                config.SHORT_END_GAP_S)
    return config.NARRATION_SPEED, config.NARRATION_GAP_S, None
```

Update the existing tests in `tests/test_tts.py` (lines 181-196) to the 3-tuple:

```python
def test_narration_pace_short_is_brisk_and_tight():
    from engine.video import tts
    from engine import config
    speed, gap, end_gap = tts.narration_pace("short")
    assert speed == config.SHORT_NARRATION_SPEED
    assert gap == config.SHORT_NARRATION_GAP_S
    assert end_gap == config.SHORT_END_GAP_S
    assert speed > config.NARRATION_SPEED      # brisker than long-form
    assert gap < config.NARRATION_GAP_S        # tighter pauses than long-form
    assert end_gap > gap                        # payoff gets a longer lead-in than the facts


def test_narration_pace_long_uses_calm_defaults():
    from engine.video import tts
    from engine import config
    assert tts.narration_pace("long") == (config.NARRATION_SPEED, config.NARRATION_GAP_S, None)
    # unknown/None format defaults to long-form (calm, uniform gaps)
    assert tts.narration_pace(None) == (config.NARRATION_SPEED, config.NARRATION_GAP_S, None)
```

- [ ] **Step 8: Update the caller in `engine/run_video.py:90-92`**

Change from:

```python
                speed, gap_s = tts.narration_pace(args.format)
                tts.synthesize(narration_text, audio_path, provider=args.tts, voice=voice,
                               speed=speed, gap_s=gap_s)
```

to:

```python
                speed, gap_s, end_gap_s = tts.narration_pace(args.format)
                tts.synthesize(narration_text, audio_path, provider=args.tts, voice=voice,
                               speed=speed, gap_s=gap_s, end_gap_s=end_gap_s)
```

- [ ] **Step 9: Run the full TTS suite**

Run: `python3 -m pytest tests/test_tts.py -q`
Expected: PASS (all, including the updated pace tests)

- [ ] **Step 10: Commit**

```bash
git add engine/video/tts.py engine/run_video.py tests/test_tts.py
git commit -m "feat(short): longer pause before the payoff sentence (end_gap)"
```

---

### Task 3: Remotion — end breath before the subscribe card

**Files:**
- Modify: `engine/video/remotion_build.py:42-47` (signature), `:101-114` (props dict)
- Modify: `engine/run_video.py:109-117` (build_props call)
- Modify: `engine/video/remotion/src/types.ts:25-40`
- Modify: `engine/video/remotion/src/Root.tsx:20,35`
- Modify: `engine/video/remotion/src/UntoldShort.tsx:29,47`
- Modify: `engine/video/remotion/src/shortDefaultProps.ts:13-15`
- Test: `tests/test_remotion_build.py`

- [ ] **Step 1: Write the failing tests for `endHoldMs` in props**

Add to `tests/test_remotion_build.py` (it already has a `_patch_heavy(monkeypatch)` helper and imports `remotion_build, music`):

```python
def test_build_props_sets_end_hold_for_short(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, _, _ = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0,
        portrait=True, end_hold_ms=1000)
    assert props["endHoldMs"] == 1000


def test_build_props_end_hold_defaults_to_zero(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, _, _ = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0)
    assert props["endHoldMs"] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_remotion_build.py -q -k end_hold`
Expected: FAIL with `KeyError: 'endHoldMs'`

- [ ] **Step 3: Add `end_hold_ms` to `build_props`**

In `engine/video/remotion_build.py`, change the signature (lines 42-47). Current last two param lines:

```python
                portrait: bool = False,
                intro_ms: int = INTRO_MS, outro_ms: int = OUTRO_MS,
                broll_beat_s: float = LONG_BROLL_BEAT_S) -> tuple[dict, list[str], str]:
```

to:

```python
                portrait: bool = False,
                intro_ms: int = INTRO_MS, outro_ms: int = OUTRO_MS,
                end_hold_ms: int = 0,
                broll_beat_s: float = LONG_BROLL_BEAT_S) -> tuple[dict, list[str], str]:
```

Then in the `props` dict (lines 101-114), add `"endHoldMs": end_hold_ms,` next to `"outroMs"`:

```python
        "introMs": intro_ms,
        "outroMs": outro_ms,
        "endHoldMs": end_hold_ms,
        "narrationMs": narration_ms,
```

- [ ] **Step 4: Run to verify the props tests pass**

Run: `python3 -m pytest tests/test_remotion_build.py -q -k end_hold`
Expected: PASS

- [ ] **Step 5: Pass `end_hold_ms` from `run_video.py`**

In `engine/run_video.py`, the `build_props` call (lines 109-117) currently ends:

```python
            intro_ms=(0 if is_short else remotion_build.INTRO_MS),
            outro_ms=(2500 if is_short else remotion_build.OUTRO_MS),
            broll_beat_s=(config.SHORT_BROLL_BEAT_S if is_short else config.LONG_BROLL_BEAT_S),
        )
```

Insert the `end_hold_ms` line:

```python
            intro_ms=(0 if is_short else remotion_build.INTRO_MS),
            outro_ms=(2500 if is_short else remotion_build.OUTRO_MS),
            end_hold_ms=(config.SHORT_END_HOLD_MS if is_short else 0),
            broll_beat_s=(config.SHORT_BROLL_BEAT_S if is_short else config.LONG_BROLL_BEAT_S),
        )
```

- [ ] **Step 6: Add `endHoldMs` to the Remotion props type**

In `engine/video/remotion/src/types.ts`, add to the `UntoldProps` type (after the `outroMs: number;` line at line 33):

```typescript
  outroMs: number;
  endHoldMs?: number;    // Shorts: hold the final story shot + music this long before the EndCTA (default 0)
  narrationMs: number;   // length of the narration audio
```

- [ ] **Step 7: Add `endHoldMs` to both composition durations in `Root.tsx`**

In `engine/video/remotion/src/Root.tsx`, both `calculateMetadata` blocks compute `totalMs` (lines 20 and 35). Change both occurrences of:

```typescript
          const totalMs = props.introMs + props.narrationMs + props.outroMs;
```

to:

```typescript
          const totalMs = props.introMs + props.narrationMs + (props.endHoldMs ?? 0) + props.outroMs;
```

(Long-form passes no `endHoldMs` → `?? 0` → its duration is unchanged.)

- [ ] **Step 8: Hold before the EndCTA in `UntoldShort.tsx`**

In `engine/video/remotion/src/UntoldShort.tsx`:

Change the music `total` (line 29) from:

```typescript
              const total = ms2f(props.introMs + props.narrationMs + props.outroMs, fps);
```

to:

```typescript
              const total = ms2f(props.introMs + props.narrationMs + (props.endHoldMs ?? 0) + props.outroMs, fps);
```

Change the EndCTA `Sequence from` (line 47) from:

```typescript
      <Sequence from={introF + ms2f(props.narrationMs, fps)} name="EndCTA">
```

to:

```typescript
      <Sequence from={introF + ms2f(props.narrationMs + (props.endHoldMs ?? 0), fps)} name="EndCTA">
```

(NOTE — corrected during implementation: Remotion `Sequence`s *unmount* when their duration
elapses, so the b-roll beats — which `beat_track` caps at `narration_ms` — would leave only the
gradient during the breath, not the story shot. Fixed in `build_props` by stretching the final
b-roll beat's `endMs` by `end_hold_ms` so the last clip (which `BeatClip` loops to fill) carries
the breath. The narration `Audio` simply ends, leaving music + the held story footage.)

- [ ] **Step 9: Add `endHoldMs` to the still-preview defaults**

In `engine/video/remotion/src/shortDefaultProps.ts`, add to the props object near `outroMs` (lines 13-15):

```typescript
  introMs: 0,         // Shorts: no intro delay — captions start at frame 0
  outroMs: 0,
  endHoldMs: 0,       // still-preview neutral; real renders pass SHORT_END_HOLD_MS
  narrationMs: 9000,
```

- [ ] **Step 10: Typecheck the Remotion sources (best-effort) and run the Python suite**

Run (best-effort — skip if the dev toolchain isn't installed; the render itself would fail on a type error):
`cd engine/video/remotion && npx tsc --noEmit; cd -`
Expected: no type errors. Then:
Run: `python3 -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add engine/video/remotion_build.py engine/run_video.py \
        engine/video/remotion/src/types.ts engine/video/remotion/src/Root.tsx \
        engine/video/remotion/src/UntoldShort.tsx engine/video/remotion/src/shortDefaultProps.ts \
        tests/test_remotion_build.py
git commit -m "feat(short): hold last shot + music ~1s before the subscribe card (endHoldMs)"
```

---

### Task 4: Script — fuller, resolving PAYOFF beat

**Files:**
- Modify: `engine/pipeline/script.py:116` (SHORT_SYSTEM PAYOFF), `:224` (DERIVE_TEASE_SYSTEM PAYOFF)
- Test: `tests/test_script.py` (create if absent)

- [ ] **Step 1: Write the failing test asserting both short prompts call for a 1-2 sentence payoff**

Append to `tests/test_script.py` (create the file with this content if it does not exist):

```python
from engine.pipeline import script


def test_short_writers_ask_for_a_resolving_two_sentence_payoff():
    # Both short writers must call for a fuller, resolving close (1-2 sentences),
    # not a single clipped line, so the ending lands.
    for prompt in (script.SHORT_SYSTEM, script.DERIVE_TEASE_SYSTEM):
        low = prompt.lower()
        assert "one to two sentences" in low
        # the old single-line wording must be gone
        assert "one resonant closing line" not in low
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_script.py -q -k payoff`
Expected: FAIL (`AssertionError`, or import error if the file was just created and the strings aren't updated yet)

- [ ] **Step 3: Update the SHORT_SYSTEM PAYOFF line**

In `engine/pipeline/script.py`, change line 116 from:

```python
- PAYOFF: one resonant closing line that recontextualises it.
```

to:

```python
- PAYOFF: a resolving close of ONE TO TWO SENTENCES that recontextualises the story and lands
  the ending — earned, not clipped. Nod that the full story is bigger. Introduce no new fact.
```

- [ ] **Step 4: Update the DERIVE_TEASE_SYSTEM PAYOFF line**

In `engine/pipeline/script.py`, change line 224 from:

```python
- PAYOFF: a closing line that resolves the short while nodding that the full story is bigger.
```

to:

```python
- PAYOFF: a resolving close of ONE TO TWO SENTENCES that lands the ending — earned, not clipped —
  while nodding that the full story is bigger.
```

- [ ] **Step 5: Run to verify the test passes**

Run: `python3 -m pytest tests/test_script.py -q -k payoff`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add engine/pipeline/script.py tests/test_script.py
git commit -m "feat(short): fuller resolving payoff beat in both short writers"
```

---

## Post-merge operations (not part of the branch)

After the PR merges to `main`, re-render the two already-rendered shorts so they
pick up the new pacing. The pacing/render changes (Tasks 1-3) are render-only;
the fuller payoff line (Task 4) only takes effect if the short script is
regenerated. Decide per-short whether to also regenerate the script:

```bash
# Render-only (new pace + end-gap + end-breath) on the existing script:
python3 -m engine.run_video --id 050d8550 --format short --render
python3 -m engine.run_video --id 9bbd24cd --format short --render
# (To also get the fuller payoff line, re-run the short produce step first, then render.)
```

Confirm the exact entrypoint/flags against the current `run_video.py` CLI at
execution time, then eyeball the preview for pace + the end breath.

---

## Self-Review

**Spec coverage:**
- Spec §1 (slow the read) → Task 1. ✓
- Spec §2 (payoff apart, `SHORT_END_GAP_S`, `_synth_kokoro`, threading) → Task 2. ✓
- Spec §3 (end breath, `SHORT_END_HOLD_MS`, `endHoldMs` prop, Root/UntoldShort/types/shortDefaultProps) → Task 3. ✓
- Spec §4 (stronger payoff, both writers) → Task 4. ✓
- Spec "re-render both / keep word count" → Post-merge section; word count deliberately untouched. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code and exact commands. ✓

**Type consistency:** `end_gap_s` (snake) in Python; `endHoldMs` / `?? 0` (camel) in TS, used identically in `types.ts`, `Root.tsx`, `UntoldShort.tsx`, `shortDefaultProps.ts`, and set via `end_hold_ms` → `props["endHoldMs"]` in `remotion_build.py`. `narration_pace` returns a 3-tuple everywhere it's consumed (`run_video.py`, both updated tests). `_gap_schedule(n, gap_s, end_gap_s)` signature matches its call in `_synth_kokoro`. ✓
