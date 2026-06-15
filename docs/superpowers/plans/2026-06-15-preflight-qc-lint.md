# Pre-flight QC Lint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure-stdlib pre-flight lint that auto-fixes deterministic caption/headline/timing defects in `props.json` and blocks the 45-min render on any unfixed CRITICAL defect.

**Architecture:** A new side-effect-free module `engine/video/preflight.py` exposes `lint_props(props, fps, narration_ms) -> (fixed_props, report)`. It applies fixers in a fixed order (drop ghost tokens → merge orphan-punct → min-duration → monotonic-clamp for captions; dedup → overlap-clamp for headlines), then re-runs detectors to compute pass/block. `run_video.py` calls it between writing `props.json` and rendering, regenerates `captions.srt` from the fixed words itself (the linter never touches files), and blocks the render when `report["blocked"]`. A standalone `run_preflight` CLI mirrors `run_factcheck`.

**Tech Stack:** Python 3 (stdlib only — `re`, `copy`, `json`, `argparse`), pytest. Reuses `engine.captions`, `engine.queue_manager`, `engine.paths`, `engine.config`.

**Spec:** `docs/superpowers/specs/2026-06-15-preflight-qc-lint-design.md`

**Conventions:** absolute `engine.*` imports; run via `python3 -m ...`; `python3 -m pytest tests/ -q` after every `engine/**.py` edit (the PostToolUse hook also runs it). Commit after each task.

---

## File structure

| File | Responsibility | New? |
|------|----------------|------|
| `engine/video/preflight.py` | All detectors + fixers + `lint_props` orchestrator. Pure, side-effect-free. | Create |
| `engine/config.py` | 4 new `QC_*` constants for the lint. | Modify |
| `engine/run_preflight.py` | CLI: re-lint an existing `props.json`, `--fix` rewrites it + SRT. | Create |
| `engine/run_video.py` | Call `lint_props` between props-write and render; gate; regen SRT. | Modify (~line 122-140) |
| `tests/test_preflight.py` | Unit tests for every detector/fixer + orchestrator. | Create |
| `tests/test_preflight_lenbias.py` | Golden regression from Len Bias `props.json`. | Create |
| `tests/fixtures/lenbias_props_excerpt.json` | Trimmed real props slice (the `$1,000,000` defect). | Create |
| `.claude/skills/preflight-qc/SKILL.md` | Skill wrapping `run_preflight`. | Create |
| `CLAUDE.md` | Entrypoint + skill row + gate-discipline line. | Modify |

---

## Data shapes (used throughout)

- **caption**: `{"text": str, "startMs": int, "endMs": int}`
- **chapter**: `{"headline": str, "startMs": int, "endMs": int}`
- **props** (relevant keys): `{"captions": [caption], "chapters": [chapter], "fps": int, "narrationMs": int, "audioSrc": str, ...}`
- **mutation**: `{"type": "merge"|"drop"|"retime"|"clamp", "reason": str, ...}`
- **check**: `{"name": str, "severity": "critical"|"warn", "passed": bool, "detail": str, "fixed": int}`
- **report**: `{"passed": bool, "blocked": bool, "checks": [check], "mutations": [mutation]}`

---

## Task 1: Config constants + module foundation

**Files:**
- Modify: `engine/config.py` (after the `QC_*` block, ~line 92)
- Create: `engine/video/preflight.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Add config constants**

In `engine/config.py`, immediately after `QC_DURATION_TOLERANCE = 0.10` (line 92):

```python
# qc preflight (preflight.py) — pre-render lint of props.json. Pure-stdlib, no ffmpeg.
QC_MAX_HEADLINE_S = 70.0          # headline on screen longer than this → "stuck" (warn)
QC_MAX_CAPTION_TOKEN_CHARS = 25   # a single caption token longer than this → glued/defect (warn)
QC_CAPTION_END_TOL_MS = 500       # captions may end up to this far past narrationMs before flagged
QC_FILLER_WORDS = ("um", "uh", "ah", "er", "erm")  # speech fillers stripped from captions
```

- [ ] **Step 2: Write the failing test for the foundation helpers**

Create `tests/test_preflight.py`:

```python
from engine.video import preflight


def test_needs_left_merge_detects_continuation_and_punct():
    assert preflight._needs_left_merge(",000") is True
    assert preflight._needs_left_merge(",000.") is True
    assert preflight._needs_left_merge(".") is True
    assert preflight._needs_left_merge("%") is True
    assert preflight._needs_left_merge("") is True
    assert preflight._needs_left_merge("million.") is False
    assert preflight._needs_left_merge("$1") is False


def test_join_space_glues_punct_without_space_and_words_with_space():
    assert preflight._join_space("$1", ",000") == "$1,000"
    assert preflight._join_space("$1,000", ",000.") == "$1,000,000."
    assert preflight._join_space("the", "race") == "the race"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: FAIL — `ModuleNotFoundError: engine.video.preflight`.

- [ ] **Step 4: Create the module with helpers**

Create `engine/video/preflight.py`:

```python
"""Pre-flight QC lint for props.json. Pure-stdlib, no ffmpeg/network/API.

Operates ONLY on the props dict (captions + chapters): auto-fixes deterministic
caption/headline/timing defects, then re-runs detectors to decide pass/block.
The linter NEVER touches files — run_video.py regenerates captions.srt from the
returned props. Mirrors the fact-gate pattern: auto-fix once → re-verify → gate.
"""
from __future__ import annotations
import copy
import re

from engine import config

# Closing/joining punctuation: a token STARTING with one of these glues onto its
# predecessor with no space (',000' → '$1,000'; '.' / ',' / '%').
_JOIN_PUNCT = set(",.;:%)]}'’\"”!?")
_PUNCT_ONLY = re.compile(r"^[^\w]+$", re.UNICODE)   # token has no letters/digits at all


def _needs_left_merge(tok: str) -> bool:
    """True if this caption token should be swallowed into its predecessor:
    empty, leading join-punctuation, or pure-punctuation."""
    t = (tok or "").strip()
    if not t:
        return True
    if t[0] in _JOIN_PUNCT:
        return True
    return bool(_PUNCT_ONLY.match(t))


def _join_space(prev: str, tok: str) -> str:
    """Glue tok onto prev: NO space for a punct/continuation fragment, one space
    for a normal word (the gap-#1 'space dilemma' fix)."""
    t = (tok or "").strip()
    if not t:
        return prev
    if t[0] in _JOIN_PUNCT or _PUNCT_ONLY.match(t):
        return prev + t
    return prev + " " + t


def _norm_word(s: str) -> str:
    """Letters-only lowercase, for filler matching."""
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _norm_headline(s: str) -> str:
    """Alphanumeric-only lowercase, for duplicate-headline matching."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add engine/config.py engine/video/preflight.py tests/test_preflight.py
git commit -m "feat(qc): preflight module foundation — config + merge helpers"
```

---

## Task 2: Caption text fixers — orphan-punct merge + filler drop

**Files:**
- Modify: `engine/video/preflight.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preflight.py`:

```python
def test_merge_punct_captions_fixes_split_number():
    caps = [
        {"text": "worth", "startMs": 120220, "endMs": 120540},
        {"text": "$1", "startMs": 120540, "endMs": 121020},
        {"text": ",000", "startMs": 121020, "endMs": 121880},
        {"text": ",000.", "startMs": 121880, "endMs": 121880},
        {"text": "Six", "startMs": 121880, "endMs": 122120},
    ]
    fixed, muts = preflight._fix_punct_captions(caps)
    texts = [c["text"] for c in fixed]
    assert texts == ["worth", "$1,000,000.", "Six"]
    assert fixed[1]["endMs"] == 121880          # endMs extended to the swallowed token
    assert any(m["type"] == "merge" and m["into"] == "$1,000,000." for m in muts)


def test_merge_punct_leaves_clean_captions_untouched():
    caps = [{"text": "the", "startMs": 0, "endMs": 100},
            {"text": "race", "startMs": 100, "endMs": 300}]
    fixed, muts = preflight._fix_punct_captions(caps)
    assert [c["text"] for c in fixed] == ["the", "race"]
    assert muts == []


def test_drop_fillers_removes_um_and_logs_mutation():
    caps = [{"text": "and", "startMs": 0, "endMs": 100},
            {"text": "um", "startMs": 100, "endMs": 260},
            {"text": "then", "startMs": 300, "endMs": 500}]
    fixed, muts = preflight._fix_fillers(caps, ("um", "uh"))
    assert [c["text"] for c in fixed] == ["and", "then"]
    assert muts == [{"type": "drop", "token": "um", "reason": "filler", "at_ms": 100}]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: FAIL — `_fix_punct_captions` / `_fix_fillers` not defined.

- [ ] **Step 3: Implement the fixers**

Append to `engine/video/preflight.py`:

```python
def _fix_punct_captions(caps: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rules 1+2: swallow orphan-punct / continuation tokens into the previous word.
    Glue with no space; extend the predecessor's endMs to cover the swallowed token."""
    out: list[dict] = []
    muts: list[dict] = []
    for c in caps:
        if out and _needs_left_merge(c["text"]):
            prev = out[-1]
            merged = _join_space(prev["text"], c["text"])
            muts.append({"type": "merge", "reason": "orphan_punct",
                         "from": [prev["text"], c["text"]], "into": merged})
            prev["text"] = merged
            prev["endMs"] = max(prev["endMs"], c["endMs"])
        else:
            out.append(dict(c))
    return out, muts


def _fix_fillers(caps: list[dict], fillers: tuple[str, ...]) -> tuple[list[dict], list[dict]]:
    """Rule 3: drop filler tokens (um/uh/...). Each word keeps absolute timing, so a
    dropped filler leaves a brief un-captioned gap — nothing freezes."""
    fset = {f.lower() for f in fillers}
    out: list[dict] = []
    muts: list[dict] = []
    for c in caps:
        if _norm_word(c["text"]) in fset:
            muts.append({"type": "drop", "token": c["text"], "reason": "filler",
                         "at_ms": c["startMs"]})
            continue
        out.append(dict(c))
    return out, muts
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/video/preflight.py tests/test_preflight.py
git commit -m "feat(qc): caption text fixers — orphan-punct merge + filler drop"
```

---

## Task 3: Caption timing fixer — ghost-token drop/clamp (Rule 7)

**Files:**
- Modify: `engine/video/preflight.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preflight.py`:

```python
def test_ghost_token_fully_after_audio_is_dropped():
    caps = [{"text": "end.", "startMs": 59000, "endMs": 59500},
            {"text": "the", "startMs": 62000, "endMs": 63000}]   # entirely after audio
    fixed, muts = preflight._fix_past_audio(caps, narration_ms=60000, tol=500)
    assert [c["text"] for c in fixed] == ["end."]
    assert muts == [{"type": "drop", "token": "the", "reason": "ghost_after_audio",
                     "at_ms": 62000}]


def test_straddling_token_is_clamped_not_dropped():
    caps = [{"text": "finish.", "startMs": 59800, "endMs": 61000}]  # straddles 60000
    fixed, muts = preflight._fix_past_audio(caps, narration_ms=60000, tol=500)
    assert fixed[0]["endMs"] == 60000
    assert fixed[0]["startMs"] == 59800
    assert muts[0]["type"] == "clamp" and muts[0]["to"] == [59800, 60000]


def test_clamp_never_creates_negative_duration():
    # token starts before end but a clamp must not invert it
    caps = [{"text": "x", "startMs": 59999, "endMs": 70000}]
    fixed, muts = preflight._fix_past_audio(caps, narration_ms=60000, tol=500)
    assert fixed[0]["endMs"] >= fixed[0]["startMs"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: FAIL — `_fix_past_audio` not defined.

- [ ] **Step 3: Implement**

Append to `engine/video/preflight.py`:

```python
def _fix_past_audio(caps: list[dict], narration_ms: int, tol: int) -> tuple[list[dict], list[dict]]:
    """Rule 7: a Whisper ghost token wholly after the audio is DROPPED (clamping it
    would invert it — gap #2); a token straddling the audio end is clamped to narration_ms."""
    out: list[dict] = []
    muts: list[dict] = []
    limit = narration_ms + tol
    for c in caps:
        if c["startMs"] > limit:
            muts.append({"type": "drop", "token": c["text"], "reason": "ghost_after_audio",
                         "at_ms": c["startMs"]})
            continue
        if c["endMs"] > narration_ms:
            new_end = max(narration_ms, c["startMs"])   # never invert
            muts.append({"type": "clamp", "token": c["text"], "reason": "past_audio",
                         "from": [c["startMs"], c["endMs"]], "to": [c["startMs"], new_end]})
            d = dict(c); d["endMs"] = new_end; out.append(d)
        else:
            out.append(dict(c))
    return out, muts
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/video/preflight.py tests/test_preflight.py
git commit -m "feat(qc): ghost-token drop/clamp — never manufacture negative duration"
```

---

## Task 4: Caption timing fixer — min-frame duration (Rules 5+6)

**Files:**
- Modify: `engine/video/preflight.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preflight.py`:

```python
def test_zero_duration_caption_gets_min_one_frame():
    caps = [{"text": "x", "startMs": 1000, "endMs": 1000}]   # zero duration
    fixed, muts = preflight._fix_min_duration(caps, fps=30)
    # one frame at 30fps ≈ 33ms; end must advance to the next whole frame
    assert fixed[0]["endMs"] > fixed[0]["startMs"]
    assert muts[0]["type"] == "retime" and muts[0]["reason"] == "min_frame_duration"


def test_subframe_caption_is_extended():
    caps = [{"text": "x", "startMs": 0, "endMs": 10}]   # <1 frame (33ms) → invisible
    fixed, _ = preflight._fix_min_duration(caps, fps=30)
    assert preflight._frame_index(fixed[0]["endMs"], 30) > preflight._frame_index(0, 30)


def test_healthy_caption_unchanged_by_min_duration():
    caps = [{"text": "x", "startMs": 0, "endMs": 500}]
    fixed, muts = preflight._fix_min_duration(caps, fps=30)
    assert fixed[0]["endMs"] == 500
    assert muts == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: FAIL — `_fix_min_duration` / `_frame_index` not defined.

- [ ] **Step 3: Implement**

Append to `engine/video/preflight.py`:

```python
def _frame_index(ms: int, fps: int) -> int:
    """Which video frame a millisecond timestamp lands on (Remotion rounds ms→frame)."""
    return int(round(ms * fps / 1000.0))


def _fix_min_duration(caps: list[dict], fps: int) -> tuple[list[dict], list[dict]]:
    """Rules 5+6: every caption must span at least one whole frame. Catches zero/negative
    duration (Rule 5, critical) and positive-but-sub-frame captions (Rule 6, warn) with the
    same bump: push endMs to the start of the next frame."""
    out: list[dict] = []
    muts: list[dict] = []
    for c in caps:
        c = dict(c)
        if _frame_index(c["endMs"], fps) <= _frame_index(c["startMs"], fps):
            new_end = int(round((_frame_index(c["startMs"], fps) + 1) * 1000.0 / fps))
            muts.append({"type": "retime", "token": c["text"], "reason": "min_frame_duration",
                         "from": [c["startMs"], c["endMs"]], "to": [c["startMs"], new_end]})
            c["endMs"] = new_end
        out.append(c)
    return out, muts
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/video/preflight.py tests/test_preflight.py
git commit -m "feat(qc): min-frame caption duration (zero/negative + sub-frame)"
```

---

## Task 5: Caption timing fixer — monotonic clamp (Rule 4) + oversize detector (Rule 11)

**Files:**
- Modify: `engine/video/preflight.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preflight.py`:

```python
def test_overlap_clamped_to_previous_end():
    caps = [{"text": "a", "startMs": 0, "endMs": 500},
            {"text": "b", "startMs": 300, "endMs": 800}]   # starts before a ends
    fixed, muts = preflight._fix_overlap(caps, fps=30)
    assert fixed[1]["startMs"] == 500
    assert fixed[1]["endMs"] == 800
    assert muts[0]["type"] == "clamp" and muts[0]["reason"] == "non_monotonic"


def test_overlap_clamp_keeps_min_frame_when_inverted():
    caps = [{"text": "a", "startMs": 0, "endMs": 500},
            {"text": "b", "startMs": 300, "endMs": 400}]   # clamp start→500 would invert
    fixed, _ = preflight._fix_overlap(caps, fps=30)
    assert fixed[1]["endMs"] >= fixed[1]["startMs"]


def test_detect_oversize_tokens():
    caps = [{"text": "ok", "startMs": 0, "endMs": 100},
            {"text": "x" * 40, "startMs": 100, "endMs": 200}]
    assert preflight._detect_oversize(caps, max_chars=25) == [1]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: FAIL — `_fix_overlap` / `_detect_oversize` not defined.

- [ ] **Step 3: Implement**

Append to `engine/video/preflight.py`:

```python
def _fix_overlap(caps: list[dict], fps: int) -> tuple[list[dict], list[dict]]:
    """Rule 4: enforce monotonic non-overlapping captions. Clamp start to the previous
    end; if that would invert the token, give it one frame so it stays valid."""
    frame_ms = int(round(1000.0 / fps))
    out: list[dict] = []
    muts: list[dict] = []
    for c in caps:
        c = dict(c)
        if out and c["startMs"] < out[-1]["endMs"]:
            new_start = out[-1]["endMs"]
            new_end = c["endMs"] if c["endMs"] >= new_start else new_start + frame_ms
            muts.append({"type": "clamp", "token": c["text"], "reason": "non_monotonic",
                         "from": [c["startMs"], c["endMs"]], "to": [new_start, new_end]})
            c["startMs"], c["endMs"] = new_start, new_end
        out.append(c)
    return out, muts


def _detect_oversize(caps: list[dict], max_chars: int) -> list[int]:
    """Rule 11 (warn): a single caption token longer than max_chars is a glued defect."""
    return [i for i, c in enumerate(caps) if len(c["text"]) > max_chars]
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: PASS (15 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/video/preflight.py tests/test_preflight.py
git commit -m "feat(qc): monotonic caption clamp + oversize-token detector"
```

---

## Task 6: Headline fixers — dedup (10) + overlap clamp (8) + stuck detector (9)

**Files:**
- Modify: `engine/video/preflight.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preflight.py`:

```python
def test_dedup_adjacent_headlines_merges_spans():
    ch = [{"headline": "THE FALL", "startMs": 0, "endMs": 1000},
          {"headline": "the fall", "startMs": 1000, "endMs": 2500},
          {"headline": "AFTER", "startMs": 2500, "endMs": 4000}]
    fixed, muts = preflight._fix_dup_headlines(ch)
    assert [c["headline"] for c in fixed] == ["THE FALL", "AFTER"]
    assert fixed[0]["endMs"] == 2500
    assert muts[0]["reason"] == "dup_headline"


def test_headline_overlap_clamped():
    ch = [{"headline": "A", "startMs": 0, "endMs": 5000},
          {"headline": "B", "startMs": 4000, "endMs": 9000}]
    fixed, muts = preflight._fix_headline_overlap(ch)
    assert fixed[1]["startMs"] == 5000
    assert muts[0]["reason"] == "headline_overlap"


def test_detect_stuck_headlines():
    ch = [{"headline": "A", "startMs": 0, "endMs": 80_000}]   # 80s > 70s default
    assert preflight._detect_stuck_headlines(ch, max_s=70.0) == [0]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: FAIL — headline functions not defined.

- [ ] **Step 3: Implement**

Append to `engine/video/preflight.py`:

```python
def _fix_dup_headlines(ch: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rule 10: merge adjacent chapters with identical (normalized) headline text,
    extending the surviving span to cover both."""
    out: list[dict] = []
    muts: list[dict] = []
    for c in ch:
        if out and _norm_headline(c["headline"]) == _norm_headline(out[-1]["headline"]):
            muts.append({"type": "merge", "reason": "dup_headline",
                         "from": [out[-1]["headline"], c["headline"]], "into": out[-1]["headline"]})
            out[-1]["endMs"] = max(out[-1]["endMs"], c["endMs"])
        else:
            out.append(dict(c))
    return out, muts


def _fix_headline_overlap(ch: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rule 8: enforce non-overlapping chapter cards — clamp start to the previous end."""
    out: list[dict] = []
    muts: list[dict] = []
    for c in ch:
        c = dict(c)
        if out and c["startMs"] < out[-1]["endMs"]:
            new_start = out[-1]["endMs"]
            new_end = max(c["endMs"], new_start)
            muts.append({"type": "clamp", "token": c["headline"], "reason": "headline_overlap",
                         "from": [c["startMs"], c["endMs"]], "to": [new_start, new_end]})
            c["startMs"], c["endMs"] = new_start, new_end
        out.append(c)
    return out, muts


def _detect_stuck_headlines(ch: list[dict], max_s: float) -> list[int]:
    """Rule 9 (warn): a chapter card on screen longer than max_s seconds (dead-air ghost)."""
    return [i for i, c in enumerate(ch) if (c["endMs"] - c["startMs"]) > max_s * 1000]
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: PASS (18 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/video/preflight.py tests/test_preflight.py
git commit -m "feat(qc): headline dedup + overlap clamp + stuck detector"
```

---

## Task 7: `lint_props` orchestrator — ordering, re-verify, report + mutations

**Files:**
- Modify: `engine/video/preflight.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preflight.py`:

```python
def _props(caps, ch, narration_ms=200000, fps=30):
    return {"audioSrc": "narration.wav", "narrationMs": narration_ms, "fps": fps,
            "captions": caps, "chapters": ch}


def test_lint_props_fixes_and_passes():
    caps = [{"text": "$1", "startMs": 1000, "endMs": 1480},
            {"text": ",000", "startMs": 1480, "endMs": 2000},
            {"text": ",000.", "startMs": 2000, "endMs": 2000}]   # split number + zero dur
    ch = [{"headline": "A", "startMs": 0, "endMs": 5000}]
    fixed, report = preflight.lint_props(_props(caps, ch), fps=30, narration_ms=200000)
    assert [c["text"] for c in fixed["captions"]] == ["$1,000,000."]
    assert report["blocked"] is False
    assert report["passed"] is True
    assert any(m["type"] == "merge" for m in report["mutations"])


def test_lint_props_blocks_on_unfixable_structural():
    fixed, report = preflight.lint_props(
        {"audioSrc": "", "narrationMs": 0, "fps": 30, "captions": [], "chapters": []},
        fps=30, narration_ms=0)
    assert report["blocked"] is True
    assert any(c["name"] == "structural" and not c["passed"] for c in report["checks"])


def test_lint_props_does_not_mutate_input():
    caps = [{"text": ",000", "startMs": 1000, "endMs": 2000}]
    src = _props(caps, [{"headline": "A", "startMs": 0, "endMs": 5000}])
    preflight.lint_props(src, fps=30, narration_ms=200000)
    assert src["captions"][0]["text"] == ",000"   # original untouched (deep-copied)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: FAIL — `lint_props` not defined.

- [ ] **Step 3: Implement the orchestrator**

Append to `engine/video/preflight.py`:

```python
def _count(muts: list[dict], reason: str) -> int:
    return sum(1 for m in muts if m.get("reason") == reason)


def lint_props(props: dict, fps: int, narration_ms: int) -> tuple[dict, dict]:
    """Auto-fix deterministic caption/headline defects, then re-run detectors to decide
    pass/block. Returns (fixed_props, report). Never raises — malformed input fails the
    structural check and blocks. The single fix pass runs in dependency order; the
    post-fix detectors are the re-verify backstop."""
    props = copy.deepcopy(props)
    muts: list[dict] = []

    # ── caption fixers, in order (gap #2: drop ghosts BEFORE any clamp) ──
    caps = list(props.get("captions") or [])
    caps, m = _fix_past_audio(caps, narration_ms, config.QC_CAPTION_END_TOL_MS); muts += m
    caps, m = _fix_punct_captions(caps); muts += m
    caps, m = _fix_fillers(caps, config.QC_FILLER_WORDS); muts += m
    caps, m = _fix_min_duration(caps, fps); muts += m
    caps, m = _fix_overlap(caps, fps); muts += m
    props["captions"] = caps

    # ── headline fixers ──
    ch = list(props.get("chapters") or [])
    ch, m = _fix_dup_headlines(ch); muts += m
    ch, m = _fix_headline_overlap(ch); muts += m
    props["chapters"] = ch

    # ── re-verify: run detectors on the FIXED props ──
    structural_ok = bool(props.get("captions")) and bool(props.get("chapters")) \
        and bool(props.get("audioSrc")) and bool(props.get("narrationMs"))
    overlaps = [i for i in range(1, len(caps)) if caps[i]["startMs"] < caps[i - 1]["endMs"]]
    bad_dur = [i for i, c in enumerate(caps)
               if _frame_index(c["endMs"], fps) <= _frame_index(c["startMs"], fps)]
    past = [i for i, c in enumerate(caps) if c["endMs"] > narration_ms + config.QC_CAPTION_END_TOL_MS]
    punct = [i for i, c in enumerate(caps) if i > 0 and _needs_left_merge(c["text"])]
    oversize = _detect_oversize(caps, config.QC_MAX_CAPTION_TOKEN_CHARS)
    h_overlap = [i for i in range(1, len(ch)) if ch[i]["startMs"] < ch[i - 1]["endMs"]]
    h_dup = [i for i in range(1, len(ch))
             if _norm_headline(ch[i]["headline"]) == _norm_headline(ch[i - 1]["headline"])]
    stuck = _detect_stuck_headlines(ch, config.QC_MAX_HEADLINE_S)

    checks = [
        {"name": "structural", "severity": "critical", "passed": structural_ok,
         "detail": "captions/chapters/audioSrc/narrationMs present" if structural_ok
         else "missing captions/chapters/audioSrc/narrationMs", "fixed": 0},
        {"name": "split_number_caption", "severity": "critical", "passed": not punct,
         "detail": f"{len(punct)} orphan-punct caption(s) remain", "fixed": _count(muts, "orphan_punct")},
        {"name": "ghost_after_audio", "severity": "critical", "passed": not past,
         "detail": f"{len(past)} caption(s) past audio end", "fixed": _count(muts, "ghost_after_audio") + _count(muts, "past_audio")},
        {"name": "caption_duration", "severity": "critical", "passed": not bad_dur,
         "detail": f"{len(bad_dur)} zero/sub-frame caption(s)", "fixed": _count(muts, "min_frame_duration")},
        {"name": "caption_monotonic", "severity": "critical", "passed": not overlaps,
         "detail": f"{len(overlaps)} overlapping caption(s)", "fixed": _count(muts, "non_monotonic")},
        {"name": "headline_overlap", "severity": "critical", "passed": not h_overlap,
         "detail": f"{len(h_overlap)} overlapping headline(s)", "fixed": _count(muts, "headline_overlap")},
        {"name": "duplicate_headline", "severity": "critical", "passed": not h_dup,
         "detail": f"{len(h_dup)} duplicate headline(s)", "fixed": _count(muts, "dup_headline")},
        {"name": "filler_caption", "severity": "warn", "passed": True,
         "detail": f"{_count(muts, 'filler')} filler(s) dropped", "fixed": _count(muts, "filler")},
        {"name": "oversize_caption_token", "severity": "warn", "passed": not oversize,
         "detail": f"{len(oversize)} oversize token(s) (>{config.QC_MAX_CAPTION_TOKEN_CHARS} chars)", "fixed": 0},
        {"name": "stuck_headline", "severity": "warn", "passed": not stuck,
         "detail": f"{len(stuck)} headline(s) > {config.QC_MAX_HEADLINE_S:.0f}s", "fixed": 0},
    ]
    blocked = any((not c["passed"]) and c["severity"] == "critical" for c in checks)
    report = {"passed": all(c["passed"] for c in checks), "blocked": blocked,
              "checks": checks, "mutations": muts}
    return props, report
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_preflight.py -q`
Expected: PASS (21 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/video/preflight.py tests/test_preflight.py
git commit -m "feat(qc): lint_props orchestrator — ordered fixers, re-verify, report+mutations"
```

---

## Task 8: Golden regression from Len Bias's real props.json

**Files:**
- Create: `tests/fixtures/lenbias_props_excerpt.json`
- Create: `tests/test_preflight_lenbias.py`

- [ ] **Step 1: Build the fixture from the real defect**

Run this to generate a trimmed slice of the real props around the `$1,000,000` defect:

```bash
python3 - <<'PY'
import json, os
src = json.load(open("produced/af86c186/long/video/props.json"))
excerpt = {
    "audioSrc": src["audioSrc"], "narrationMs": src["narrationMs"], "fps": src["fps"],
    "captions": src["captions"][258:270],      # surrounds tokens 263-265 ($1 / ,000 / ,000.)
    "chapters": src["chapters"][:2],
}
os.makedirs("tests/fixtures", exist_ok=True)
json.dump(excerpt, open("tests/fixtures/lenbias_props_excerpt.json", "w"), indent=2)
print("captions:", [c["text"] for c in excerpt["captions"]])
PY
```

Expected output includes the contiguous `'$1', ',000', ',000.'` tokens and a zero-duration entry.

- [ ] **Step 2: Write the regression test**

Create `tests/test_preflight_lenbias.py`:

```python
import json
import os

from engine.video import preflight

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "lenbias_props_excerpt.json")


def test_lenbias_split_number_is_repaired():
    props = json.load(open(FIXTURE))
    fixed, report = preflight.lint_props(props, fps=props["fps"],
                                         narration_ms=props["narrationMs"])
    texts = [c["text"] for c in fixed["captions"]]
    # the three fragments collapse into one clean money token, no stray ',000'
    assert "$1,000,000." in texts
    assert ",000" not in texts and ",000." not in texts
    # no zero/sub-frame durations survive
    assert all(preflight._frame_index(c["endMs"], props["fps"])
               > preflight._frame_index(c["startMs"], props["fps"])
               for c in fixed["captions"])
    # the merge is recorded in the audit trail and nothing blocks
    assert any(m["type"] == "merge" and m["into"] == "$1,000,000." for m in report["mutations"])
    assert report["blocked"] is False
```

- [ ] **Step 3: Run to verify it passes**

Run: `python3 -m pytest tests/test_preflight_lenbias.py -q`
Expected: PASS. (If the excerpt slice indices miss the defect, adjust the `[258:270]` window so the `$1 / ,000 / ,000.` run is included, then re-run.)

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/lenbias_props_excerpt.json tests/test_preflight_lenbias.py
git commit -m "test(qc): golden regression — Len Bias \$1,000,000 split-number repair"
```

---

## Task 9: Wire the gate into `run_video.py` + regenerate SRT

**Files:**
- Modify: `engine/run_video.py` (the Remotion branch, lines 122-140)
- Test: covered by `tests/test_preflight.py` (orchestrator) + a manual smoke

- [ ] **Step 1: Read the current Remotion-branch block**

Run: `sed -n '108,140p' engine/run_video.py` — confirm `props.json` is written at ~123 and the render starts at ~140-144. The new gate goes between them.

- [ ] **Step 2: Add the SRT-from-fixed-props adapter import + gate**

In `engine/run_video.py`, locate (Remotion branch):

```python
        with open(os.path.join(video_dir, "props.json"), "w") as f:
            json.dump(props, f, indent=2)
        srt_chunks = (captions.chunk_words_to_captions(captions.digitize_number_words(words)) if words
                      else captions.estimate_caption_timings(narration_text, total_dur))
        captions.to_srt(srt_chunks, os.path.join(video_dir, "captions.srt"))
```

Replace with:

```python
        # ── Pre-flight QC lint: auto-fix caption/headline defects, gate the render ──
        from engine.video import preflight
        props, qc_report = preflight.lint_props(props, props["fps"], props["narrationMs"])
        with open(os.path.join(video_dir, "props.json"), "w") as f:
            json.dump(props, f, indent=2)
        with open(os.path.join(video_dir, "qc_lint.json"), "w") as f:
            json.dump(qc_report, f, indent=2)
        # Regenerate the SRT from the FIXED caption words so SRT and props can't diverge.
        srt_chunks = captions.chunk_words_to_captions(
            [{"word": c["text"], "start": c["startMs"] / 1000.0, "end": c["endMs"] / 1000.0}
             for c in props["captions"]])
        captions.to_srt(srt_chunks, os.path.join(video_dir, "captions.srt"))
        n_fixed = sum(c["fixed"] for c in qc_report["checks"])
        n_warn = sum(1 for c in qc_report["checks"] if c["severity"] == "warn" and not c["passed"])
        if qc_report["blocked"]:
            failing = [c["name"] for c in qc_report["checks"]
                       if c["severity"] == "critical" and not c["passed"]]
            # Match run_produce's status convention: long → status, short → short_status.
            if args.format == "short":
                _field, _val = "short_status", "short_needs_review"
            else:
                _field, _val = "status", "needs_review"
            print(f"{RED}✗ pre-flight QC BLOCKED — unfixed: {', '.join(failing)}. "
                  f"Render skipped; idea → {_val}. See qc_lint.json.{RESET}")
            q.update_idea(args.id, **{_field: _val})
            return
        print(f"{GREEN}✓ pre-flight QC: {n_fixed} auto-fixed, {n_warn} warning(s){RESET}")
```

(Note: `digitize_number_words` is intentionally dropped from this path — the lint now owns
number/caption hygiene, and digitizing after alignment is what split `$1,000,000`.)

- [ ] **Step 3: Run the engine test contract**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (the hook runs this automatically too). If `test_render_remotion.py` asserts on the old SRT path, update its expectation to the fixed-props SRT.

- [ ] **Step 4: Smoke the props-only path (no render)**

Run: `python3 -m engine.run_video --id af86c186 --mode narrated --engine remotion` (no `--render`)
Expected: writes `props.json` + `qc_lint.json`; prints `✓ pre-flight QC: N auto-fixed …`; the `$1,000,000.` token is present in `produced/af86c186/long/video/props.json`.

Verify: `python3 -c "import json; print([c['text'] for c in json.load(open('produced/af86c186/long/video/props.json'))['captions'] if '000' in c['text']])"`
Expected: `['$1,000,000.']` (no bare `,000`).

- [ ] **Step 5: Commit**

```bash
git add engine/run_video.py tests/
git commit -m "feat(qc): gate the render on pre-flight QC + regen SRT from fixed props"
```

---

## Task 10: Standalone CLI `engine/run_preflight.py`

**Files:**
- Create: `engine/run_preflight.py`
- Test: a CLI smoke (manual) — logic is already covered by `tests/test_preflight.py`

- [ ] **Step 1: Write the CLI (mirrors `run_factcheck.py`)**

Create `engine/run_preflight.py`:

```python
"""
The Untold Game — PRE-FLIGHT QC lint.

Lints a produced video's props.json (captions + chapters) BEFORE the render:
auto-fixes deterministic caption/headline/timing defects, reports the rest.
Exits non-zero if any CRITICAL defect remains unfixed (the render gate).

Usage:
  python3 -m engine.run_preflight --id <id>                 # report only
  python3 -m engine.run_preflight --id <id> --fix           # rewrite props.json + captions.srt
  python3 -m engine.run_preflight --id <id> --format short  # the short cut
"""
from __future__ import annotations
import argparse
import json
import os
import sys

from engine import paths
from engine.video import captions, preflight

GOLD, GREEN, RED, YELLOW, GRAY, RESET = (
    "\033[93m", "\033[92m", "\033[91m", "\033[33m", "\033[90m", "\033[0m")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _print_report(report: dict) -> None:
    for c in report["checks"]:
        if c["passed"] and not c["fixed"]:
            continue
        mark = (f"{GREEN}✓ fixed" if c["passed"] and c["fixed"]
                else f"{RED}✗ {c['severity'].upper()}" if c["severity"] == "critical"
                else f"{YELLOW}⚠ warn")
        print(f"{mark}{RESET}  {c['name']}: {c['detail']}"
              + (f"  ({c['fixed']} auto-fixed)" if c["fixed"] else ""))
    for m in report["mutations"]:
        print(f"{GRAY}   · {m['type']}: {m.get('into') or m.get('token')} [{m['reason']}]{RESET}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-flight QC lint for a produced props.json")
    ap.add_argument("--id", required=True)
    ap.add_argument("--format", choices=["long", "short"], default="long")
    ap.add_argument("--fix", action="store_true", help="rewrite props.json + captions.srt with fixes")
    args = ap.parse_args()

    vdir = paths.video_dir(args.id, args.format)
    props_path = os.path.join(vdir, "props.json")
    if not os.path.exists(props_path):
        print(f"{RED}No props.json at {os.path.relpath(props_path, _ROOT)}. "
              f"Run `python3 -m engine.run_video --id {args.id}` first.{RESET}")
        return 2
    with open(props_path) as f:
        props = json.load(f)

    print(f"{GOLD}▶ Pre-flight QC [{args.id}/{args.format}] — linting props.json…{RESET}")
    fixed, report = preflight.lint_props(props, props.get("fps", 30), props.get("narrationMs", 0))
    _print_report(report)

    qc_path = os.path.join(paths.artifact_dir(args.id, args.format), "qc_lint.json")
    with open(qc_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"{GRAY}report → {os.path.relpath(qc_path, _ROOT)}{RESET}")

    if args.fix:
        with open(props_path, "w") as f:
            json.dump(fixed, f, indent=2)
        srt_chunks = captions.chunk_words_to_captions(
            [{"word": c["text"], "start": c["startMs"] / 1000.0, "end": c["endMs"] / 1000.0}
             for c in fixed["captions"]])
        captions.to_srt(srt_chunks, os.path.join(vdir, "captions.srt"))
        print(f"{GREEN}✓ wrote fixed props.json + captions.srt{RESET}")

    if report["blocked"]:
        failing = [c["name"] for c in report["checks"]
                   if c["severity"] == "critical" and not c["passed"]]
        print(f"{RED}✗ BLOCKED — unfixed CRITICAL: {', '.join(failing)}. "
              f"Do NOT render until resolved.{RESET}")
        return 1
    print(f"{GREEN}✓ PASSED — no unfixed CRITICAL defects.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke it**

Run: `python3 -m engine.run_preflight --id af86c186 --format long`
Expected: prints the report (split-number auto-fixed), writes `qc_lint.json`, exits 0.

Run: `python3 -m engine.run_preflight --id af86c186 --format long --fix`
Expected: also rewrites `props.json` + `captions.srt`; `$1,000,000.` present, no bare `,000`.

- [ ] **Step 3: Run the test contract**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add engine/run_preflight.py
git commit -m "feat(qc): run_preflight CLI — lint/--fix an existing props.json"
```

---

## Task 11: Skill + CLAUDE.md docs

**Files:**
- Create: `.claude/skills/preflight-qc/SKILL.md`
- Modify: `CLAUDE.md` (Entrypoints, Skills table, Gate discipline)

- [ ] **Step 1: Write the skill**

Create `.claude/skills/preflight-qc/SKILL.md`:

```markdown
---
name: preflight-qc
description: Run the pre-flight QC lint on a produced video's props.json before the 45-min render — auto-fix caption/headline/timing defects (split numbers, zero-duration captions, overlaps, duplicate/stuck headlines) and block the render on unfixed CRITICAL defects. Use when the user says "lint the captions", "pre-flight check <id>", "check props before render", or "/preflight-qc".
---

# Pre-flight QC lint

Wraps `python3 -m engine.run_preflight`. Operates on `produced/<id>/<fmt>/video/props.json`
(build it first with `run_video` *without* `--render`). The lint also runs automatically
inside `run_video.py` before every Remotion render.

## Steps

1. Ensure props exist: `python3 -m engine.run_video --id <id> [--format short]` (no `--render`).
2. Report only: `python3 -m engine.run_preflight --id <id> [--format short]`.
3. Apply fixes: add `--fix` (rewrites `props.json` + `captions.srt`).
4. Read `produced/<id>/<fmt>/qc_lint.json` — `checks` (severity/passed/fixed) and the
   `mutations` audit trail (exactly what text/timestamps were changed and why).

## Gate

Exits non-zero (and `run_video` skips the render, marking the idea `needs_review`) when any
CRITICAL check is still failing after the single auto-fix pass. CRITICAL: split-number/
orphan-punct captions, ghost-after-audio, zero/sub-frame duration, non-monotonic captions,
headline overlap, duplicate headline, structural. WARN (never blocks): fillers dropped,
oversize token, stuck headline.

Scope: pre-flight (props.json) only. Post-render checks live in `engine/pipeline/qc.py`.
```

- [ ] **Step 2: Update CLAUDE.md — Entrypoints block**

In `CLAUDE.md`, in the `## Entrypoints` fenced block, after the `run_thumbnail` line, add:

```bash
python3 -m engine.run_preflight --id <id> [--format short] [--fix]  # pre-flight QC lint of props.json (auto-fix caption/headline defects; --fix rewrites props.json + captions.srt). Runs automatically inside run_video before each render.
```

- [ ] **Step 3: Update CLAUDE.md — Skills table**

In the `## Skills` table, add a row (after `fact-review`):

```markdown
| `preflight-qc` | `run_preflight` — lint props.json before render |
```

- [ ] **Step 4: Update CLAUDE.md — Gate discipline**

In the `## Gate discipline` section, append:

```markdown
A render is **blocked** if the pre-flight QC lint (`engine/video/preflight.py`, auto-run in
`run_video` before each Remotion render) finds an unfixed CRITICAL caption/headline/timing
defect — the idea is marked `needs_review`. Deterministic defects (split numbers, zero-duration
captions, overlaps, duplicate headlines) are auto-corrected once, then re-verified. See
docs/superpowers/specs/2026-06-15-preflight-qc-lint-design.md.
```

- [ ] **Step 5: Verify nothing broke + commit**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

```bash
git add .claude/skills/preflight-qc/SKILL.md CLAUDE.md
git commit -m "docs(qc): preflight-qc skill + CLAUDE.md entrypoint/gate-discipline"
```

---

## Final verification (after all tasks)

- [ ] `python3 -m pytest tests/ -q` — full suite green.
- [ ] `python3 -m engine.run_preflight --id af86c186 --format long` — exits 0, split-number auto-fixed, `qc_lint.json` written with a `mutations` entry for the `$1,000,000.` merge.
- [ ] Ship via the `ship-video-change` skill (engine `.py` changed): branch already `feat/preflight-qc-lint`; dual adversarial review (Codex + Claude code-reviewer), 0 Critical/0 Important from both; PR with `Adversarial-Reviewed:` trailer; squash-merge.
- [ ] HANDOFF + memory: note pre-flight lint shipped; the deferred CH5 post-render audio QC follow-up; the `digitize_number_words`-removed-from-Remotion-SRT-path change.

## Notes / deviations from spec

- **Rule 6 (frame-snap) reinterpreted** as a *sub-frame caption* check folded into the
  min-duration fixer (Task 4). Remotion rounds ms→frame internally, so snapping every
  timestamp to a 33.3ms grid would be noisy and pointless; the meaningful defect is a caption
  that lands on <1 frame (invisible/flicker), which the min-duration bump fixes. Consistent
  with the spec's intent ("prevent sub-frame flashing").
- **`digitize_number_words` removed from the Remotion SRT path** (Task 9): it ran *after*
  `align_to_script` and is the transform that split `$1,000,000`. The lint now owns caption
  number/punctuation hygiene. (It remains available for the legacy estimate path.)
