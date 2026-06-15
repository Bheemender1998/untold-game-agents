# Long-form caption & headline alignment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long-form captions and chapter headlines use the *script's* text (not free Whisper ASR), fixing name errors, hyphen artifacts, and headline mis-placement/overlap in one change; plus a headline de-dup/clamp and a TTS staccato-loop guard.

**Architecture:** Keep faster-whisper for *timing only*. A new pure function `align_to_script()` projects the script's words onto Whisper's timestamps via `difflib`, so captions and headline anchors share the script's exact text. A small `compose.py` post-step de-dups/clamps headlines. The TTS loop is diagnosed against a real render then guarded.

**Tech Stack:** Python 3.14 (`python3` env for logic + tests), faster-whisper (`.venv-video`, timing only), `difflib` (stdlib). Spec: `docs/superpowers/specs/2026-06-15-longform-caption-alignment-design.md`.

---

### Task 1: `align_to_script()` — project script words onto Whisper timings

**Files:**
- Modify: `engine/video/captions.py` (add `_norm_tok` + `align_to_script` near the other pure helpers, after `chunk_words_to_captions`)
- Test: `tests/test_caption_alignment.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_caption_alignment.py
from engine.video import captions


def _ww(pairs):  # [(word, start, end), ...] -> whisper word dicts
    return [{"word": w, "start": s, "end": e} for w, s, e in pairs]


def test_replaces_misheard_word_with_script_text_keeping_timing():
    whisper = _ww([("Coach", 0.0, 0.4), ("Eber", 0.4, 0.9), ("understood", 0.9, 1.5)])
    out = captions.align_to_script(whisper, "Coach Iba understood")
    assert [w["word"] for w in out] == ["Coach", "Iba", "understood"]
    assert out[1]["start"] == 0.4 and out[1]["end"] == 0.9          # timing preserved
    assert all(out[i]["start"] <= out[i + 1]["start"] for i in range(len(out) - 1))


def test_interpolates_word_whisper_dropped():
    # script has 4 words; whisper dropped "to"
    whisper = _ww([("He", 0.0, 0.2), ("went", 0.2, 0.6), ("Munich", 0.6, 1.2)])
    out = captions.align_to_script(whisper, "He went to Munich")
    assert [w["word"] for w in out] == ["He", "went", "to", "Munich"]
    # "to" sits between "went".end (0.6) and "Munich".start (0.6) -> non-decreasing, in range
    assert 0.2 <= out[2]["start"] <= out[3]["start"] <= 1.2


def test_drops_whisper_words_not_in_script():
    whisper = _ww([("The", 0.0, 0.2), ("um", 0.2, 0.4), ("end", 0.4, 0.8)])
    out = captions.align_to_script(whisper, "The end")
    assert [w["word"] for w in out] == ["The", "end"]


def test_distributes_timing_across_multi_word_replace():
    # whisper one token spanning a long time, script two words -> split proportionally
    whisper = _ww([("USA", 0.0, 1.0)])
    out = captions.align_to_script(whisper, "U.S. A")
    assert [w["word"] for w in out] == ["U.S.", "A"]
    assert out[0]["start"] == 0.0 and out[-1]["end"] == 1.0
    assert out[0]["end"] == out[1]["start"]                         # contiguous, monotonic


def test_empty_inputs_fall_back():
    assert captions.align_to_script([], "anything") == []
    w = _ww([("hi", 0.0, 0.3)])
    assert captions.align_to_script(w, "") == w                     # no script -> unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_caption_alignment.py -q`
Expected: FAIL — `AttributeError: module 'engine.video.captions' has no attribute 'align_to_script'`

- [ ] **Step 3: Implement `_norm_tok` and `align_to_script`**

```python
# engine/video/captions.py  — add `import difflib` at top with the other imports,
# then add below chunk_words_to_captions:

def _norm_tok(s: str) -> str:
    """Lowercase, strip non-alphanumerics — for MATCHING only (not display)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def align_to_script(whisper_words: list[dict], narration_text: str) -> list[dict]:
    """Project the SCRIPT's words onto whisper's timings so caption/headline TEXT is the
    script (correct names, hyphens, abbreviations) while TIMING comes from whisper.

    whisper_words: [{word,start,end}] (seconds). Returns the same shape with script text.
    - equal/replace: script words take the matched whisper span (split proportionally by
      char length when counts differ);
    - delete (script word whisper dropped): timing interpolated between known neighbours;
    - insert (whisper word not in script): dropped.
    Falls back to whisper_words unchanged if either side is empty (never crashes a render)."""
    swords = [w for w in re.split(r"\s+", (narration_text or "").strip()) if w]
    if not whisper_words or not swords:
        return whisper_words
    wnorm = [_norm_tok(w["word"]) for w in whisper_words]
    snorm = [_norm_tok(w) for w in swords]
    out: list[dict] = []
    sm = difflib.SequenceMatcher(a=snorm, b=wnorm, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            continue                                   # whisper-only tokens -> drop
        sseg = swords[i1:i2]
        if tag == "delete":                            # script words whisper dropped
            for w in sseg:
                out.append({"word": w, "start": None, "end": None})
            continue
        wseg = whisper_words[j1:j2]                     # equal or replace
        t0, t1 = wseg[0]["start"], wseg[-1]["end"]
        span = max(0.0, t1 - t0)
        lengths = [max(1, len(w)) for w in sseg]
        total = sum(lengths)
        cursor = t0
        for w, ln in zip(sseg, lengths):
            dur = span * (ln / total) if total else 0.0
            out.append({"word": w, "start": cursor, "end": cursor + dur})
            cursor += dur
    # Fill interpolated (None) timings between anchored neighbours, keep monotonic.
    n = len(out)
    for k in range(n):
        if out[k]["start"] is not None:
            continue
        prev = next((out[p]["end"] for p in range(k - 1, -1, -1) if out[p]["end"] is not None), None)
        nxt = next((out[q]["start"] for q in range(k + 1, n) if out[q]["start"] is not None), None)
        lo = prev if prev is not None else (nxt if nxt is not None else 0.0)
        hi = nxt if nxt is not None else lo
        run = [q for q in range(k, n) if out[q]["start"] is None]
        step = (hi - lo) / (len(run) + 1)
        for m, q in enumerate(run, start=1):
            out[q]["start"] = lo + step * m
            out[q]["end"] = lo + step * (m + 0.5)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_caption_alignment.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/video/captions.py tests/test_caption_alignment.py
git commit -m "feat(captions): align_to_script — project script words onto whisper timings"
```

---

### Task 2: Wire `align_to_script` into the caption pipeline

**Files:**
- Modify: `engine/run_video.py:98-121` (after `transcribe`, before captions/headlines consume `words`)

- [ ] **Step 1: Apply alignment right after transcription**

Locate (around line 99-100) where `words` is taken from the transcript. Insert alignment so every downstream consumer (SRT chunks + Remotion props + headline anchors) sees script-true words. Because the text is now the script's, the ASR-era `digitize_number_words` step is no longer needed on the aligned path — the script already carries the intended number form.

```python
# engine/run_video.py — after: tx = captions.transcribe(audio_path, initial_prompt=glossary)
narration_text = tts.script_to_narration_text(script_md)
words = captions.align_to_script(tx["words"], narration_text) if tx else None
...
# line ~121: drop digitize_number_words on the aligned path:
srt_chunks = captions.chunk_words_to_captions(words) if words \
    else captions.estimate_caption_timings(narration_text, total_dur)
```

- [ ] **Step 2: Orchestrator smoke (no render)**

Run: `python3 -m engine.run_auto --list`
Expected: no traceback (import-clean).

- [ ] **Step 3: Commit**

```bash
git add engine/run_video.py
git commit -m "feat(captions): feed script-aligned words to captions + headline anchoring"
```

---

### Task 3: Headline de-dup + min-duration clamp

**Files:**
- Modify: `engine/video/compose.py` (add `_dedup_and_clamp_headlines`, call it at the end of `assign_headline_times` before return; add `HEADLINE_MIN_MS = 3000` near module constants)
- Test: `tests/test_headline_layout.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_headline_layout.py
from engine.video import compose


def _h(headline, s, e):
    return {"headline": headline, "startMs": s, "endMs": e}


def test_merges_consecutive_duplicate_headlines():
    hs = [_h("IBA VS THE SOVIETS", 0, 5000), _h("IBA VS THE SOVIETS", 5000, 6000),
          _h("THE FINAL SECONDS", 6000, 12000)]
    out = compose._dedup_and_clamp_headlines(hs, total_ms=12000)
    assert [h["headline"] for h in out] == ["IBA VS THE SOVIETS", "THE FINAL SECONDS"]
    assert out[0]["startMs"] == 0 and out[0]["endMs"] == 6000     # spans both merged


def test_sub_floor_headline_merges_into_neighbour():
    hs = [_h("A", 0, 8000), _h("B", 8000, 9000), _h("C", 9000, 15000)]  # B only 1s
    out = compose._dedup_and_clamp_headlines(hs, total_ms=15000)
    assert all(h["endMs"] - h["startMs"] >= compose.HEADLINE_MIN_MS for h in out)
    assert [h["headline"] for h in out] == ["A", "C"]             # B absorbed into A


def test_well_spaced_headlines_untouched():
    hs = [_h("A", 0, 6000), _h("B", 6000, 12000)]
    out = compose._dedup_and_clamp_headlines(hs, total_ms=12000)
    assert out == hs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_headline_layout.py -q`
Expected: FAIL — `AttributeError: module 'engine.video.compose' has no attribute '_dedup_and_clamp_headlines'`

- [ ] **Step 3: Implement the helper and call it**

```python
# engine/video/compose.py — module constant near the top:
HEADLINE_MIN_MS = 3000

# add the function above assign_headline_times:
def _dedup_and_clamp_headlines(headlines: list[dict], total_ms: int) -> list[dict]:
    """Belt-and-suspenders after time assignment: (1) merge consecutive identical headlines
    into one span; (2) absorb any headline shorter than HEADLINE_MIN_MS into the previous one
    (or the next if it is first), so a placement miss can never flash many headlines at once."""
    if not headlines:
        return []
    merged: list[dict] = []
    for h in headlines:
        if merged and h["headline"] == merged[-1]["headline"]:
            merged[-1]["endMs"] = h["endMs"]
        else:
            merged.append(dict(h))
    out: list[dict] = []
    for h in merged:
        if out and (h["endMs"] - h["startMs"]) < HEADLINE_MIN_MS:
            out[-1]["endMs"] = h["endMs"]               # absorb into previous
        else:
            out.append(h)
    # if the FIRST headline is sub-floor, pull the next start back instead
    if len(out) >= 2 and (out[0]["endMs"] - out[0]["startMs"]) < HEADLINE_MIN_MS:
        out[1]["startMs"] = out[0]["startMs"]
        out.pop(0)
    out[-1]["endMs"] = total_ms
    return out
```

Then, at the end of `assign_headline_times`, replace `return <headlines>` with:

```python
    return _dedup_and_clamp_headlines(<headlines>, int(total_dur * 1000))
```

(Use the existing local variable name that holds the finished `[{headline,startMs,endMs}]` list — confirm by reading the function's current return.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_headline_layout.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/video/compose.py tests/test_headline_layout.py
git commit -m "feat(headlines): de-dup consecutive + clamp to a minimum on-screen duration"
```

---

### Task 4: TTS staccato-loop guard (diagnose-first)

The `Possession./Pass./Possession./Pass.` loop could not be confirmed from static analysis (`_split_sentences` already splits these into separate chunks), so this task **reproduces before fixing** — do not write a speculative guard.

**Files:**
- Modify: `engine/video/tts.py` (`_split_sentences` or `_synth_kokoro`, depending on the repro)
- Test: `tests/test_tts.py` (extend)

- [ ] **Step 1: Reproduce.** In `.venv-video`, synthesize just the offending run to a wav and listen / inspect duration vs. expected:

```bash
.venv-video/bin/python -c "from engine.video import tts; tts.synthesize('Possession. Pass. Possession. Pass.', '/tmp/staccato.wav', provider='kokoro')"
```
Expected: confirm whether the wav loops/garbles or runs long. Capture the exact failing input shape (single ≤2-word repeated chunks vs. the concatenation step).

- [ ] **Step 2: Pin the mechanism** — add a `[DEBUG-tts]`-tagged log of each chunk + its synthesized duration in `_synth_kokoro`; re-run; identify which chunk loops.

- [ ] **Step 3: Write a failing unit test** at the confirmed seam (pure-python, no Kokoro). E.g. if the fix lives in chunk preparation, test that the staccato run is normalized to a non-looping shape:

```python
def test_staccato_run_is_normalized(...):
    # ASSERT the confirmed transformation, e.g. consecutive <=2-word repeats are merged/spaced
    ...
```

- [ ] **Step 4: Implement the minimal guard** at that seam (merge a run of >=3 repeated <=2-word sentences into one spoken chunk, or synthesize+concatenate with an explicit silence gap — whichever the repro shows fixes it). Self-stubbing: on any edge, fall back to current behaviour.

- [ ] **Step 5: Verify** the unit test passes AND re-run the Step-1 repro to confirm the wav no longer loops. Remove `[DEBUG-tts]` logs.

- [ ] **Step 6: Commit**

```bash
git add engine/video/tts.py tests/test_tts.py
git commit -m "fix(tts): guard against kokoro loop on staccato repeated phrases"
```

---

## Verification (render gate — not CI)

After all tasks: re-render `adfea6c1` long on `main` (`.venv-video`, launchd/M5), then confirm:
1. `produced/adfea6c1/long/video/captions.srt` reads `Iba`, `U.S.`, `Sixty-three` (no `Eber`, no `X -Y`).
2. `props.json` chapter `startMs` spread across the timeline; none below `HEADLINE_MIN_MS`; no duplicate headline.
3. The 178–185s region has captions and the audio no longer loops.

The 45-min render is NOT a gate — rely on the unit tests + the still-preview trick (`npx remotion still … --frame=N`).

## Ship rail

All `engine/*.py` changes ship via **ship-video-change** (feature branch, `python3 -m pytest tests/ -q`, dual adversarial review Codex + Claude, PR with `Adversarial-Reviewed:` trailer, squash-merge). Render verification is local; never in a hook/CI.

## Self-review notes

- **Spec coverage:** Unit 1 (forced alignment) → Tasks 1-2; Unit 2 (TTS guard) → Task 4; Unit 3 (headline dedup/clamp) → Task 3. All three covered.
- **Type consistency:** word dicts are `{word,start,end}` (seconds) throughout (Tasks 1-2); headline dicts are `{headline,startMs,endMs}` (ms) throughout (Task 3) — matches `props.json` and `assign_headline_times`.
- **Known open detail:** Task 3 Step 3 says to use the existing return variable name in `assign_headline_times` — the implementer confirms it by reading the function's current tail (it returns the finished `[{headline,startMs,endMs}]` list). Task 4 is deliberately diagnose-first because the loop mechanism is unconfirmed.
