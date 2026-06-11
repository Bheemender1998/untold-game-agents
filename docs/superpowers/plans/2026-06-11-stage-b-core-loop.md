# Stage B — Automation Core Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the proven manual pipeline into an unattended core loop — one command produces → renders → quality-checks a video and parks it `awaiting_approval`; a human approves from the CLI to publish.

**Architecture:** A `qc.py` local quality gate (ffprobe/ffmpeg, no API) plus a `run_auto.py` orchestrator that shells out to each stage with the correct interpreter (the project has two venvs — `python3` for produce, `.venv-video` for render — so a single process can't import both). Render runs under a hard timeout with a process-group kill. Publish is always human-initiated.

**Tech Stack:** Python 3 (stdlib `subprocess`/`json`/`os`/`signal`), `ffprobe`/`ffmpeg`, pytest 9 (main env), existing `engine.queue_manager` / `engine.publish.uploader` / `engine.publish.auth`.

**Spec:** `docs/superpowers/specs/2026-06-11-stage-b-core-loop-design.md`

---

## File Structure

- **Create** `engine/pipeline/qc.py` — local QC gate: ffprobe/ffmpeg helpers + 3 checks + `qc_video()`.
- **Create** `engine/run_auto.py` — orchestrator CLI: pipeline mode + approval subcommands.
- **Modify** `engine/config.py` — add QC thresholds + `RENDER_TIMEOUT_S`.
- **Create** `tests/__init__.py`, `tests/conftest.py` — hermetic ffmpeg fixtures.
- **Create** `tests/test_qc.py`, `tests/test_run_auto.py`.

**Conventions (existing, do not break):** absolute `engine.*` imports; run via `python3 -m engine.run_auto`; never crash the batch on one idea's failure; `produced/` is **gitignored** (so tests must generate their own fixtures, never depend on a committed render).

**Key facts the code depends on (verified against the codebase):**
- Ranking: `idea["scores"]["viral_overall"]`; `queue_manager.get_pending()` already returns `pending` ideas sorted by it, descending.
- Render outputs (per idea `<id>`): video `produced/<id>/video/video.mp4`, narration `produced/<id>/video/narration.wav`, props `produced/<id>/video/props.json`.
- `video_path` is stored on the idea as a path **relative to repo root** (`run_video` sets it).
- `props["captions"]` is a list of `{"text": str, "startMs": int, "endMs": int}`.
- `metadata.json` keys: `title`, `description`, `tags` (list), `chapters`.
- `uploader.upload(video_path, title, description="", tags=None, privacy="private", publish_at=None, thumbnail_path=None) -> str` (returns YouTube video id).
- `queue_manager`: `get_pending()`, `get_by_status(s)`, `get_by_id(id)`, `update_idea(id, **fields)`.
- `publish.auth` exposes a function that returns an authorized client / refreshes `token.json` (used by `--approve --dry-run` to exercise OAuth without inserting; confirm its exact name when implementing Task 10 — `grep -n "def " engine/publish/auth.py`).

---

## Task 1: Config thresholds

**Files:**
- Modify: `engine/config.py` (append after the queue settings block)

- [ ] **Step 1: Add the constants**

Append to `engine/config.py`:

```python
# ── Stage B: QC thresholds + render timeout ───────────────────────────────────
# qc.py gate. Mean luma is 0-255 (libx264 limited-range black ≈ 16; mid-grey ≈ 126).
QC_BRIGHTNESS_MIN = 40.0       # below → near-black (the darkness bug)
QC_BRIGHTNESS_MAX = 180.0      # above → blown out
QC_MIN_CAPTION_COVERAGE = 0.85 # captions' last word must reach ≥85% of audio length
QC_MAX_CAPTION_GAP_S = 8.0     # no silent caption gap longer than this
QC_DURATION_TOLERANCE = 0.10   # video vs narration-audio duration may differ by ≤10%
RENDER_TIMEOUT_S = 5400        # 90 min hard cap on one render subprocess
```

- [ ] **Step 2: Verify it imports**

Run: `python3 -c "from engine import config; print(config.QC_BRIGHTNESS_MIN, config.RENDER_TIMEOUT_S)"`
Expected: `40.0 5400`

- [ ] **Step 3: Commit**

```bash
git add engine/config.py
git commit -m "feat(config): Stage B QC thresholds + render timeout"
```

---

## Task 2: Test fixtures (hermetic ffmpeg-generated media)

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`

- [ ] **Step 1: Create the package marker**

Create `tests/__init__.py` (empty file).

- [ ] **Step 2: Write the fixtures**

Create `tests/conftest.py`:

```python
"""Hermetic media fixtures built with ffmpeg — no dependency on any real render
(produced/ is gitignored, so committed renders are not available in CI)."""
import shutil
import subprocess

import pytest

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
requires_ffmpeg = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                   check=True, timeout=60)


@pytest.fixture
def gray_video(tmp_path):
    """2s mid-grey (luma ~126) clip WITH an audio track — passes brightness."""
    out = tmp_path / "video.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x808080:s=320x180:d=2:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:d=2",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out))
    return out


@pytest.fixture
def black_video(tmp_path):
    """2s near-black (luma ~16) clip with audio — fails brightness_band."""
    out = tmp_path / "black.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=320x180:d=2:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:d=2",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out))
    return out


@pytest.fixture
def silent_audio(tmp_path):
    """2s wav — the narration-duration ground truth."""
    out = tmp_path / "narration.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:d=2", str(out))
    return out
```

- [ ] **Step 3: Verify fixtures build**

Run: `python3 -m pytest tests/ -q` (collects 0 tests but conftest must import cleanly)
Expected: `no tests ran` with no import error.

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: hermetic ffmpeg media fixtures for Stage B"
```

---

## Task 3: qc.py — ffprobe helpers + render_integrity

**Files:**
- Create: `engine/pipeline/qc.py`
- Test: `tests/test_qc.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_qc.py`:

```python
from engine.pipeline import qc
from tests.conftest import requires_ffmpeg


@requires_ffmpeg
def test_render_integrity_passes_on_good_video(gray_video, silent_audio):
    r = qc.render_integrity(str(gray_video), str(silent_audio))
    assert r["name"] == "render_integrity"
    assert r["passed"] is True


@requires_ffmpeg
def test_render_integrity_fails_when_audio_missing(gray_video, tmp_path):
    r = qc.render_integrity(str(gray_video), str(tmp_path / "nope.wav"))
    assert r["passed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_qc.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.pipeline.qc'`

- [ ] **Step 3: Write minimal implementation**

Create `engine/pipeline/qc.py`:

```python
"""Local quality gate for a rendered video. ffprobe/ffmpeg only — no network, no API.
Each check returns {'name', 'passed', 'detail'}; qc_video() ANDs them and writes qc.json."""
from __future__ import annotations
import json
import os
import re
import subprocess

from engine import config

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ffprobe_duration(path: str) -> float | None:
    if not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return None


def _ffprobe_stream_types(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}
    except subprocess.SubprocessError:
        return set()


def render_integrity(video_path: str, audio_path: str) -> dict:
    """Pass = file exists, has video+audio streams, and its duration is within
    QC_DURATION_TOLERANCE of the narration audio (the ground-truth length)."""
    name = "render_integrity"
    if not os.path.exists(video_path):
        return {"name": name, "passed": False, "detail": "video.mp4 missing"}
    streams = _ffprobe_stream_types(video_path)
    if not {"video", "audio"} <= streams:
        return {"name": name, "passed": False, "detail": f"streams={sorted(streams)}"}
    v_dur, a_dur = _ffprobe_duration(video_path), _ffprobe_duration(audio_path)
    if v_dur is None or a_dur is None or a_dur == 0:
        return {"name": name, "passed": False, "detail": f"unreadable durations v={v_dur} a={a_dur}"}
    drift = abs(v_dur - a_dur) / a_dur
    ok = drift <= config.QC_DURATION_TOLERANCE
    return {"name": name, "passed": ok,
            "detail": f"video={v_dur:.1f}s audio={a_dur:.1f}s drift={drift:.0%}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_qc.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/qc.py tests/test_qc.py
git commit -m "feat(qc): render_integrity check (streams + duration vs narration)"
```

---

## Task 4: qc.py — brightness_band

**Files:**
- Modify: `engine/pipeline/qc.py`
- Test: `tests/test_qc.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_qc.py`:

```python
@requires_ffmpeg
def test_brightness_passes_on_grey(gray_video):
    assert qc.brightness_band(str(gray_video))["passed"] is True


@requires_ffmpeg
def test_brightness_fails_on_black(black_video):
    r = qc.brightness_band(str(black_video))
    assert r["passed"] is False
    assert "luma" in r["detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_qc.py -k brightness -q`
Expected: FAIL — `AttributeError: module 'engine.pipeline.qc' has no attribute 'brightness_band'`

- [ ] **Step 3: Write minimal implementation**

Append to `engine/pipeline/qc.py`:

```python
def _mean_luma(path: str, every_n: int = 30) -> float | None:
    """Average YAVG (0-255) over every Nth frame via ffmpeg signalstats."""
    if not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", path,
             "-vf", f"select='not(mod(n\\,{every_n}))',signalstats,metadata=print:file=-",
             "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120)
    except subprocess.SubprocessError:
        return None
    vals = [float(m) for m in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", out.stdout)]
    return sum(vals) / len(vals) if vals else None


def brightness_band(video_path: str) -> dict:
    name = "brightness_band"
    luma = _mean_luma(video_path)
    if luma is None:
        return {"name": name, "passed": False, "detail": "could not read luma"}
    ok = config.QC_BRIGHTNESS_MIN <= luma <= config.QC_BRIGHTNESS_MAX
    return {"name": name, "passed": ok,
            "detail": f"mean luma={luma:.0f} band=[{config.QC_BRIGHTNESS_MIN:.0f},{config.QC_BRIGHTNESS_MAX:.0f}]"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_qc.py -k brightness -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/qc.py tests/test_qc.py
git commit -m "feat(qc): brightness_band check (ffmpeg signalstats YAVG)"
```

---

## Task 5: qc.py — caption_coverage

**Files:**
- Modify: `engine/pipeline/qc.py`
- Test: `tests/test_qc.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_qc.py`:

```python
import json


def _props(tmp_path, captions):
    p = tmp_path / "props.json"
    p.write_text(json.dumps({"captions": captions}))
    return p


def test_caption_coverage_passes_full(tmp_path):
    # words span 0..1900ms over a 2.0s audio → 95% coverage, no big gaps
    caps = [{"text": "a", "startMs": i * 100, "endMs": i * 100 + 90} for i in range(20)]
    r = qc.caption_coverage(str(_props(tmp_path, caps)), audio_dur=2.0)
    assert r["passed"] is True


def test_caption_coverage_fails_when_captions_stop_early(tmp_path):
    # words stop at 600ms of a 2.0s audio → 30% coverage
    caps = [{"text": "a", "startMs": i * 100, "endMs": i * 100 + 90} for i in range(6)]
    r = qc.caption_coverage(str(_props(tmp_path, caps)), audio_dur=2.0)
    assert r["passed"] is False


def test_caption_coverage_fails_on_long_gap(tmp_path):
    caps = [{"text": "a", "startMs": 0, "endMs": 100},
            {"text": "b", "startMs": 100, "endMs": 1900}]  # 1.8s is fine for default 8s gap...
    # force a >8s gap:
    caps = [{"text": "a", "startMs": 0, "endMs": 100},
            {"text": "b", "startMs": 9000, "endMs": 9100}]
    r = qc.caption_coverage(str(_props(tmp_path, caps)), audio_dur=9.1)
    assert r["passed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_qc.py -k caption -q`
Expected: FAIL — no attribute `caption_coverage`

- [ ] **Step 3: Write minimal implementation**

Append to `engine/pipeline/qc.py`:

```python
def caption_coverage(props_path: str, audio_dur: float) -> dict:
    """Pass = caption words reach ≥ QC_MIN_CAPTION_COVERAGE of the audio AND no inter-word
    gap exceeds QC_MAX_CAPTION_GAP_S. Reads props.json['captions'] ({text,startMs,endMs})."""
    name = "caption_coverage"
    try:
        caps = json.load(open(props_path)).get("captions", [])
    except (OSError, ValueError):
        return {"name": name, "passed": False, "detail": "props.json unreadable"}
    if not caps or not audio_dur:
        return {"name": name, "passed": False, "detail": "no captions or zero audio"}
    caps = sorted(caps, key=lambda c: c["startMs"])
    last_end_s = max(c["endMs"] for c in caps) / 1000.0
    coverage = last_end_s / audio_dur
    max_gap_s = max([(caps[i + 1]["startMs"] - caps[i]["endMs"]) / 1000.0
                     for i in range(len(caps) - 1)] or [0.0])
    ok = coverage >= config.QC_MIN_CAPTION_COVERAGE and max_gap_s <= config.QC_MAX_CAPTION_GAP_S
    return {"name": name, "passed": ok,
            "detail": f"coverage={coverage:.0%} max_gap={max_gap_s:.1f}s"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_qc.py -k caption -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/qc.py tests/test_qc.py
git commit -m "feat(qc): caption_coverage check (props.json word timings)"
```

---

## Task 6: qc.py — qc_video orchestration + qc.json

**Files:**
- Modify: `engine/pipeline/qc.py`
- Test: `tests/test_qc.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_qc.py`:

```python
import os


@requires_ffmpeg
def test_qc_video_writes_report_and_ands_checks(tmp_path, gray_video, silent_audio, monkeypatch):
    # Build a fake produced/<id>/video layout
    idea_id = "testid01"
    vdir = tmp_path / "produced" / idea_id / "video"
    vdir.mkdir(parents=True)
    (vdir / "video.mp4").write_bytes(gray_video.read_bytes())
    (vdir / "narration.wav").write_bytes(silent_audio.read_bytes())
    caps = [{"text": "a", "startMs": i * 100, "endMs": i * 100 + 90} for i in range(20)]
    (vdir / "props.json").write_text(json.dumps({"captions": caps}))
    monkeypatch.setattr(qc, "_ROOT", str(tmp_path))

    report = qc.qc_video(idea_id)
    assert set(c["name"] for c in report["checks"]) == {
        "render_integrity", "brightness_band", "caption_coverage"}
    assert report["passed"] is True
    assert os.path.exists(tmp_path / "produced" / idea_id / "qc.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_qc.py -k qc_video -q`
Expected: FAIL — no attribute `qc_video`

- [ ] **Step 3: Write minimal implementation**

Append to `engine/pipeline/qc.py`:

```python
def qc_video(idea_id: str) -> dict:
    """Run all local checks on produced/<id>/video and write produced/<id>/qc.json.
    Returns {'passed': bool, 'checks': [...]}. Never raises — missing inputs fail a check."""
    base = os.path.join(_ROOT, "produced", idea_id)
    vdir = os.path.join(base, "video")
    video = os.path.join(vdir, "video.mp4")
    audio = os.path.join(vdir, "narration.wav")
    props = os.path.join(vdir, "props.json")
    audio_dur = _ffprobe_duration(audio) or 0.0

    checks = [
        render_integrity(video, audio),
        brightness_band(video),
        caption_coverage(props, audio_dur),
    ]
    report = {"passed": all(c["passed"] for c in checks), "checks": checks}
    with open(os.path.join(base, "qc.json"), "w") as f:
        json.dump(report, f, indent=2)
    return report
```

- [ ] **Step 4: Run the full qc suite**

Run: `python3 -m pytest tests/test_qc.py -q`
Expected: PASS (all qc tests)

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/qc.py tests/test_qc.py
git commit -m "feat(qc): qc_video orchestration + qc.json report"
```

---

## Task 7: run_auto.py — idea selection + produce step (--no-render path)

**Files:**
- Create: `engine/run_auto.py`
- Test: `tests/test_run_auto.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_auto.py`:

```python
from engine import run_auto


def test_select_returns_top_n_pending(monkeypatch):
    pending = [{"id": "a"}, {"id": "b"}, {"id": "c"}]  # get_pending() already sorts by score
    monkeypatch.setattr(run_auto.q, "get_pending", lambda: pending)
    assert [i["id"] for i in run_auto._select(2)] == ["a", "b"]


def test_produce_one_returns_resulting_status(monkeypatch):
    monkeypatch.setattr(run_auto, "_run", lambda *a, **k: 0)  # produce subprocess "succeeds"
    monkeypatch.setattr(run_auto.q, "get_by_id",
                        lambda i: {"id": i, "status": "in_production", "human_reviewed": False})
    assert run_auto._produce_one("x") == "in_production"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_run_auto.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.run_auto'`

- [ ] **Step 3: Write minimal implementation**

Create `engine/run_auto.py`:

```python
"""Stage B orchestrator: unattended produce → render → QC → awaiting_approval, plus the
human approval CLI. Runs in the user's shell (render needs npx). Shells out per stage with
the right interpreter (the produce/render venvs can't coexist in one process)."""
from __future__ import annotations
import os
import signal
import subprocess
import sys

from engine import config
from engine import queue_manager as q

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENV_PY = os.path.join(_ROOT, ".venv-video", "bin", "python")


def _run(cmd: list[str], timeout: float | None = None) -> int:
    """Run a subprocess in its own process group; return exit code.
    On timeout, kill the whole group and return a sentinel 124 (like coreutils timeout)."""
    proc = subprocess.Popen(cmd, cwd=_ROOT, start_new_session=True)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
        return 124


def _select(count: int) -> list[dict]:
    return q.get_pending()[:count]


def _produce_one(idea_id: str) -> str:
    """Run produce as a subprocess; return the idea's resulting status."""
    _run([sys.executable, "-m", "engine.run_produce", "--id", idea_id])
    idea = q.get_by_id(idea_id) or {}
    return idea.get("status", "unknown")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_run_auto.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto.py
git commit -m "feat(run_auto): idea selection + produce-step subprocess"
```

---

## Task 8: run_auto.py — render step (timeout + process-group kill)

**Files:**
- Modify: `engine/run_auto.py`
- Test: `tests/test_run_auto.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_auto.py`:

```python
import time


def test_run_kills_on_timeout():
    start = time.monotonic()
    rc = run_auto._run(["sleep", "10"], timeout=1)
    assert rc == 124
    assert time.monotonic() - start < 5  # killed promptly, not after 10s


def test_render_one_marks_render_failed_on_nonzero(monkeypatch):
    monkeypatch.setattr(run_auto, "_run", lambda *a, **k: 1)
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    assert run_auto._render_one("x") is False
    assert seen["status"] == "render_failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_run_auto.py -k "timeout or render_one" -q`
Expected: FAIL — no attribute `_render_one` (the `_run` timeout test passes already)

- [ ] **Step 3: Write minimal implementation**

Append to `engine/run_auto.py`:

```python
def _render_one(idea_id: str) -> bool:
    """Render via the video venv under a hard timeout. On nonzero/timeout → render_failed."""
    rc = _run([_VENV_PY, "-m", "engine.run_video", "--id", idea_id,
               "--render", "--mode", "narrated"],
              timeout=config.RENDER_TIMEOUT_S)
    if rc != 0:
        why = "render timed out" if rc == 124 else f"render exit {rc}"
        q.update_idea(idea_id, status="render_failed", render_note=why)
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_run_auto.py -k "timeout or render_one" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto.py
git commit -m "feat(run_auto): render step with hard timeout + process-group kill"
```

---

## Task 9: run_auto.py — pipeline() (clear-to-render gate, QC, status transitions)

**Files:**
- Modify: `engine/run_auto.py`
- Test: `tests/test_run_auto.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_auto.py`:

```python
def _stub_pipeline(monkeypatch, idea, render_ok=True, qc_pass=True):
    monkeypatch.setattr(run_auto, "_select", lambda n: [idea])
    monkeypatch.setattr(run_auto, "_produce_one", lambda i: idea["status"])
    monkeypatch.setattr(run_auto, "_render_one", lambda i: render_ok)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i: {"passed": qc_pass, "checks": []})
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    return seen


def test_pipeline_marks_awaiting_approval_on_qc_pass(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    seen = _stub_pipeline(monkeypatch, idea, qc_pass=True)
    run_auto.pipeline(count=1, no_render=False)
    assert seen["status"] == "awaiting_approval"


def test_pipeline_human_reviewed_clears_to_render(monkeypatch):
    idea = {"id": "x", "status": "needs_review", "human_reviewed": True}
    seen = _stub_pipeline(monkeypatch, idea, qc_pass=True)
    run_auto.pipeline(count=1, no_render=False)
    assert seen["status"] == "awaiting_approval"


def test_pipeline_skips_unreviewed_needs_review(monkeypatch):
    idea = {"id": "x", "status": "needs_review", "human_reviewed": False}
    called = {"render": False}
    monkeypatch.setattr(run_auto, "_select", lambda n: [idea])
    monkeypatch.setattr(run_auto, "_produce_one", lambda i: "needs_review")
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    monkeypatch.setattr(run_auto, "_render_one",
                        lambda i: called.__setitem__("render", True) or True)
    run_auto.pipeline(count=1, no_render=False)
    assert called["render"] is False  # never rendered an unreviewed needs_review idea


def test_pipeline_marks_qc_failed(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    seen = _stub_pipeline(monkeypatch, idea, qc_pass=False)
    run_auto.pipeline(count=1, no_render=False)
    assert seen["status"] == "qc_failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_run_auto.py -k pipeline -q`
Expected: FAIL — no attribute `pipeline` (and `qc` not imported)

- [ ] **Step 3: Write minimal implementation**

Add `from engine.pipeline import qc` to the imports of `engine/run_auto.py`, then append:

```python
def _cleared_to_render(idea: dict) -> bool:
    return idea.get("status") == "in_production" or idea.get("human_reviewed") is True


def pipeline(count: int, no_render: bool) -> None:
    """Produce → (render → QC) for the top-`count` pending ideas. One failure never
    aborts the batch."""
    for idea in _select(count):
        idea_id = idea["id"]
        try:
            _produce_one(idea_id)
            current = q.get_by_id(idea_id) or {}
            if not _cleared_to_render(current):
                print(f"· {idea_id}: not cleared ({current.get('status')}) — skipping")
                continue
            if no_render:
                print(f"· {idea_id}: cleared (--no-render, stopping before render)")
                continue
            if not _render_one(idea_id):
                print(f"· {idea_id}: render_failed")
                continue
            report = qc.qc_video(idea_id)
            status = "awaiting_approval" if report["passed"] else "qc_failed"
            q.update_idea(idea_id, status=status)
            print(f"· {idea_id}: {status}")
        except Exception as e:  # never abort the batch
            print(f"! {idea_id}: error {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_run_auto.py -k pipeline -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto.py
git commit -m "feat(run_auto): pipeline() with clear-to-render gate, QC, status transitions"
```

---

## Task 10: run_auto.py — approval CLI (list / review / reject / approve)

**Files:**
- Modify: `engine/run_auto.py`
- Test: `tests/test_run_auto.py`

> **Before coding:** `grep -n "def " engine/publish/auth.py` to find the exact authorize/refresh
> function name; use it in `cmd_approve`'s `--dry-run` branch (shown as `auth.authorize()` below —
> rename to match).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_auto.py`:

```python
def test_cmd_review_sets_two_fields(monkeypatch):
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto.cmd_review("x", note="checked scorecard")
    assert seen["human_reviewed"] is True
    assert seen["human_review_note"].endswith("checked scorecard")


def test_cmd_approve_uploads_and_marks_published(monkeypatch, tmp_path):
    idea = {"id": "x", "status": "awaiting_approval",
            "metadata_path": "produced/x/metadata.json",
            "video_path": "produced/x/video/video.mp4"}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    monkeypatch.setattr(run_auto, "_load_metadata",
                        lambda p: {"title": "T", "description": "D", "tags": ["a"]})
    calls = {}
    monkeypatch.setattr(run_auto.uploader, "upload",
                        lambda **k: calls.update(k) or "yt123")
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto.cmd_approve("x", public=False, dry_run=False)
    assert calls["privacy"] == "unlisted"
    assert seen["status"] == "published"
    assert "yt123" in seen["youtube_url"]


def test_cmd_approve_dry_run_skips_upload(monkeypatch):
    idea = {"id": "x", "status": "awaiting_approval",
            "metadata_path": "produced/x/metadata.json",
            "video_path": "produced/x/video/video.mp4"}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    monkeypatch.setattr(run_auto, "_load_metadata",
                        lambda p: {"title": "T", "description": "D", "tags": ["a"]})
    monkeypatch.setattr(run_auto.auth, "authorize", lambda: object())  # auth exercised
    called = {"upload": False}
    monkeypatch.setattr(run_auto.uploader, "upload",
                        lambda **k: called.__setitem__("upload", True))
    run_auto.cmd_approve("x", public=False, dry_run=True)
    assert called["upload"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_run_auto.py -k "cmd_review or cmd_approve" -q`
Expected: FAIL — no attribute `cmd_review` (and `uploader`/`auth` not imported)

- [ ] **Step 3: Write minimal implementation**

Add imports to `engine/run_auto.py`: `import json` and `from engine.publish import uploader, auth` (`cmd_review` imports `datetime` locally). Then append:

```python
def _load_metadata(rel_path: str) -> dict:
    with open(os.path.join(_ROOT, rel_path)) as f:
        return json.load(f)


def cmd_list() -> None:
    rows = q.get_by_status("awaiting_approval")
    if not rows:
        print("No videos awaiting approval.")
        return
    for i in rows:
        title = (i.get("title_variants") or ["?"])[0]
        print(f"{i['id']}  {title[:60]}")


def cmd_review(idea_id: str, note: str = "") -> None:
    import datetime
    stamp = datetime.date.today().isoformat()
    q.update_idea(idea_id, human_reviewed=True,
                  human_review_note=f"{stamp}: {note}".rstrip(": "))
    print(f"✓ {idea_id} marked human_reviewed")


def cmd_reject(idea_id: str) -> None:
    q.update_idea(idea_id, status="rejected")
    print(f"✓ {idea_id} rejected")


def cmd_approve(idea_id: str, public: bool, dry_run: bool) -> None:
    idea = q.get_by_id(idea_id) or {}
    meta = _load_metadata(idea["metadata_path"])
    video = os.path.join(_ROOT, idea["video_path"])
    privacy = "public" if public else "unlisted"
    if dry_run:
        auth.authorize()  # exercise OAuth/token refresh — catches expiry
        assert meta.get("title") and os.path.exists(video), "metadata/video invalid"
        print(f"✓ dry-run OK for {idea_id} (auth + metadata valid; not published)")
        return
    yt_id = uploader.upload(video_path=video, title=meta["title"],
                            description=meta.get("description", ""),
                            tags=meta.get("tags"), privacy=privacy)
    q.update_idea(idea_id, status="published",
                  youtube_url=f"https://youtu.be/{yt_id}")
    print(f"✓ published {idea_id} → https://youtu.be/{yt_id} ({privacy})")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_run_auto.py -k "cmd_review or cmd_approve" -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto.py
git commit -m "feat(run_auto): approval CLI (list/review/reject/approve + dry-run)"
```

---

## Task 11: run_auto.py — argparse main() wiring + manual smoke

**Files:**
- Modify: `engine/run_auto.py`

- [ ] **Step 1: Add the CLI entrypoint**

Append to `engine/run_auto.py`:

```python
def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="The Untold Game — Stage B orchestrator")
    ap.add_argument("--count", type=int, default=1, help="ideas to produce+render this run")
    ap.add_argument("--no-render", action="store_true", help="stop before render (dry test)")
    ap.add_argument("--list", action="store_true", help="list awaiting_approval videos")
    ap.add_argument("--review", metavar="ID", help="mark an idea human_reviewed")
    ap.add_argument("--note", default="", help="note for --review")
    ap.add_argument("--approve", metavar="ID", help="publish an awaiting_approval video")
    ap.add_argument("--public", action="store_true", help="--approve as public (default unlisted)")
    ap.add_argument("--dry-run", action="store_true", help="--approve: auth+metadata check, no insert")
    ap.add_argument("--reject", metavar="ID", help="mark an idea rejected")
    args = ap.parse_args()

    if args.list:
        cmd_list()
    elif args.review:
        cmd_review(args.review, args.note)
    elif args.reject:
        cmd_reject(args.reject)
    elif args.approve:
        cmd_approve(args.approve, public=args.public, dry_run=args.dry_run)
    else:
        pipeline(count=args.count, no_render=args.no_render)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Full suite + headless import check**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (all qc + run_auto tests)

Run: `python3 -m engine.run_auto --list`
Expected: prints awaiting-approval ideas (or "No videos awaiting approval."), no traceback.

- [ ] **Step 3: Manual smoke (real, against the Kolkata idea once it has rendered)**

```bash
# After the Kolkata render finishes (video.mp4 + props.json exist) and the idea is human_reviewed:
python3 -c "from engine.pipeline import qc; import json; print(json.dumps(qc.qc_video('85a68197'), indent=2))"
# Then dry-run the publish path (no insert):
python3 -m engine.run_auto --approve 85a68197 --dry-run
```
Expected: a QC report (3 checks) + `dry-run OK`.

- [ ] **Step 4: Commit**

```bash
git add engine/run_auto.py
git commit -m "feat(run_auto): argparse main() — pipeline + approval subcommands"
```

---

## Self-review notes (resolved inline)

- **Spec coverage:** qc.py 3 checks (Tasks 3-5) + qc_video (Task 6); run_auto produce/render/QC pipeline (Tasks 7-9); approval CLI incl. v1 `--review`, `--approve --dry-run` (Task 10); render timeout + killpg (Task 8); status adds `awaiting_approval`/`qc_failed`/`render_failed` (used in Tasks 8-9); `human_reviewed` override (Task 9). Retry semantics = no auto-retry (the pipeline simply advances; re-running re-attempts) — matches spec.
- **Fixture portability:** the spec named the Escobar render as a fixture, but `produced/` is gitignored, so Tasks 2-6 use hermetic ffmpeg-generated clips instead (strictly more portable; same intent — known-good vs darkened).
- **Deferred (not in this plan, per spec):** launchd scheduler, Claude-vision people-check, web approval UI, Shorts/vertical.
- **Open confirm at implementation time:** the exact `publish.auth` authorize/refresh function name (Task 10 note) — grep before wiring `--dry-run`.
```
