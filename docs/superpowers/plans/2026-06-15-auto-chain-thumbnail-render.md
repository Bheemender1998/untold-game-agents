# Auto-chain thumbnail-on-render Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every idea that finishes a render reaches `awaiting_approval` with a composited `thumbnail.jpg` already present (when a subject can be sourced), and a missing thumbnail at approve time warns loudly instead of shipping a default frame silently.

**Architecture:** Add a single self-stubbing `_ensure_thumbnail(idea_id, fmt)` helper to `engine/run_auto.py` (main-env orchestration layer), called after a successful render for both the long (`_render_and_qc`) and companion short (`_companion_short`). It calls the existing `engine.pipeline.subject.source_subject` + `engine.pipeline.thumbnail.generate_thumbnail` in-process (same pattern as the existing `chapters`/`run_produce` in-process calls — respects the two-venv split, since `run_auto` runs under main `python3`). Add a non-blocking warning to the `cmd_approve` upload path when no thumbnail file exists.

**Tech Stack:** Python 3 (main env), pytest, monkeypatch. PIL/network deps live behind `subject`/`thumbnail` modules (mocked in tests).

**Spec:** `docs/superpowers/specs/2026-06-15-auto-chain-thumbnail-render-design.md`

---

## File Structure

- **Modify:** `engine/run_auto.py`
  - Add import: `from engine.pipeline import subject, thumbnail`
  - Add helper `_ensure_thumbnail(idea_id, fmt)`
  - Call it in `_render_and_qc` (long) and `_companion_short` (short)
  - Add soft warning in `cmd_approve` upload path (long + short)
- **Modify/Create test:** `tests/test_run_auto_thumbnail.py` (already exists — append helper tests + a warning test)
- **Docs:** `CLAUDE.md` (pipeline-layout line), `.claude/skills/thumbnail-assets/SKILL.md`

---

## Task 1: `_ensure_thumbnail` helper (TDD)

**Files:**
- Modify: `engine/run_auto.py` (imports near line 19-20; new helper after `_render_one`, before `_cleared_to_render` ~line 72)
- Test: `tests/test_run_auto_thumbnail.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run_auto_thumbnail.py`:

```python
def _patch_thumb_env(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_auto, "_ROOT", str(tmp_path))
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda _id: {"id": _id})


def test_ensure_thumbnail_skips_when_thumbnail_exists(tmp_path, monkeypatch):
    _patch_thumb_env(tmp_path, monkeypatch)
    os.makedirs(paths.artifact_dir("pubid", "long"), exist_ok=True)
    from PIL import Image
    Image.new("RGB", (1280, 720), (0, 0, 0)).save(paths.thumbnail_path("pubid", "long"))
    calls = {"source": 0, "gen": 0}
    monkeypatch.setattr(run_auto.subject, "source_subject",
                        lambda idea, fmt: calls.__setitem__("source", calls["source"] + 1) or {"source": "x"})
    monkeypatch.setattr(run_auto.thumbnail, "generate_thumbnail",
                        lambda idea, fmt: calls.__setitem__("gen", calls["gen"] + 1))
    run_auto._ensure_thumbnail("pubid", "long")
    assert calls == {"source": 0, "gen": 0}   # neither called — thumbnail already present


def test_ensure_thumbnail_generates_when_missing(tmp_path, monkeypatch):
    _patch_thumb_env(tmp_path, monkeypatch)
    calls = {"gen": 0}
    monkeypatch.setattr(run_auto.subject, "source_subject", lambda idea, fmt: {"source": "wikipedia"})
    monkeypatch.setattr(run_auto.thumbnail, "generate_thumbnail",
                        lambda idea, fmt: calls.__setitem__("gen", calls["gen"] + 1))
    run_auto._ensure_thumbnail("pubid", "long")
    assert calls["gen"] == 1


def test_ensure_thumbnail_self_stubs_when_no_photo(tmp_path, monkeypatch):
    _patch_thumb_env(tmp_path, monkeypatch)
    calls = {"gen": 0}
    monkeypatch.setattr(run_auto.subject, "source_subject", lambda idea, fmt: {"source": None, "path": "p"})
    monkeypatch.setattr(run_auto.thumbnail, "generate_thumbnail",
                        lambda idea, fmt: calls.__setitem__("gen", calls["gen"] + 1))
    run_auto._ensure_thumbnail("pubid", "long")   # must not raise
    assert calls["gen"] == 0   # no subject → no generation


def test_ensure_thumbnail_swallows_exceptions(tmp_path, monkeypatch):
    _patch_thumb_env(tmp_path, monkeypatch)
    monkeypatch.setattr(run_auto.subject, "source_subject", lambda idea, fmt: {"source": "pexels"})
    def boom(idea, fmt):
        raise RuntimeError("PIL exploded")
    monkeypatch.setattr(run_auto.thumbnail, "generate_thumbnail", boom)
    run_auto._ensure_thumbnail("pubid", "long")   # must return normally, not propagate
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_run_auto_thumbnail.py -q`
Expected: FAIL — `AttributeError: module 'engine.run_auto' has no attribute 'subject'` (and `_ensure_thumbnail` undefined).

- [ ] **Step 3: Add the import**

In `engine/run_auto.py`, after line 19 (`from engine.pipeline import qc`), add:

```python
from engine.pipeline import subject, thumbnail
```

- [ ] **Step 4: Implement the helper**

In `engine/run_auto.py`, add this function immediately after `_render_one` (before `_cleared_to_render`):

```python
def _ensure_thumbnail(idea_id: str, fmt: str) -> None:
    """Best-effort: ensure produced/<id>/<fmt>/thumbnail.jpg exists after a render.

    Skips if a thumbnail already exists (never clobbers hand-composited work).
    Self-stubs on any failure — a missing thumbnail must never break render/QC."""
    try:
        thumb = paths.thumbnail_path(idea_id, fmt)
        if os.path.exists(thumb):
            print(f"· {idea_id}/{fmt}: thumbnail exists — skipping auto-generation")
            return
        idea = q.get_by_id(idea_id) or {"id": idea_id}
        res = subject.source_subject(idea, fmt)        # Wikipedia → Pexels; human subject wins
        if not res.get("source"):
            print(f"⚠ {idea_id}/{fmt}: no subject photo found — thumbnail skipped "
                  f"(hand-source before approving)")
            return
        thumbnail.generate_thumbnail(idea, fmt)
        print(f"✓ {idea_id}/{fmt}: thumbnail composited via {res['source']}")
    except Exception as e:                              # never break the render/batch
        print(f"⚠ {idea_id}/{fmt}: thumbnail auto-generation failed — {e}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_run_auto_thumbnail.py -q`
Expected: PASS (all 4 new tests + the 2 pre-existing approve tests).

- [ ] **Step 6: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto_thumbnail.py
git commit -m "feat(thumbnail): self-stubbing _ensure_thumbnail helper for render chain"
```

---

## Task 2: Wire the helper into both render paths

**Files:**
- Modify: `engine/run_auto.py` — `_render_and_qc` (~line 78) and `_companion_short` (~line 118-121)
- Test: `tests/test_run_auto_thumbnail.py` (append wiring tests)

- [ ] **Step 1: Write the failing wiring tests**

Append to `tests/test_run_auto_thumbnail.py`:

```python
def test_render_and_qc_calls_ensure_thumbnail(monkeypatch):
    monkeypatch.setattr(run_auto, "_render_one", lambda i: True)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="long": {"passed": True, "checks": []})
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    from engine.pipeline import chapters
    monkeypatch.setattr(chapters, "sync_from_render", lambda i, fmt: False)
    monkeypatch.setattr(run_auto, "_companion_short", lambda i: None)
    seen = []
    monkeypatch.setattr(run_auto, "_ensure_thumbnail", lambda i, fmt: seen.append((i, fmt)))
    run_auto._render_and_qc("pubid")
    assert ("pubid", "long") in seen


def test_companion_short_calls_ensure_thumbnail(monkeypatch):
    monkeypatch.setattr(run_auto, "_produce_companion", lambda i: {"within_long": True})
    monkeypatch.setattr(run_auto, "_run", lambda *a, **k: 0)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="short": {"passed": True, "checks": []})
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    seen = []
    monkeypatch.setattr(run_auto, "_ensure_thumbnail", lambda i, fmt: seen.append((i, fmt)))
    run_auto._companion_short("pubid")
    assert ("pubid", "short") in seen
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_run_auto_thumbnail.py -k ensure_thumbnail -q`
Expected: FAIL — `_render_and_qc`/`_companion_short` don't call `_ensure_thumbnail` yet, so `seen` is empty.

- [ ] **Step 3: Wire into `_render_and_qc`**

In `engine/run_auto.py`, in `_render_and_qc`, immediately after the render-success guard:

```python
    if not _render_one(idea_id):
        print(f"· {idea_id}: render_failed")
        return
    _ensure_thumbnail(idea_id, _OVERNIGHT_FMT)   # NEW: auto-compose thumbnail on render
```

(Leave the existing chapter-sync / QC / `awaiting_approval` block below unchanged.)

- [ ] **Step 4: Wire into `_companion_short`**

In `engine/run_auto.py`, in `_companion_short`, inside the `if report["passed"]:` branch, before the `q.update_idea(... short_awaiting_approval ...)` call:

```python
        if report["passed"]:
            _ensure_thumbnail(idea_id, "short")   # NEW: auto-compose short thumbnail
            q.update_idea(idea_id, short_status="short_awaiting_approval",
                          short_video_path=os.path.relpath(
                              os.path.join(paths.video_dir(idea_id, "short"), "video.mp4"), _ROOT))
            print(f"· {idea_id}: companion short short_awaiting_approval")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_run_auto_thumbnail.py -q`
Expected: PASS (all thumbnail tests).

- [ ] **Step 6: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto_thumbnail.py
git commit -m "feat(thumbnail): auto-chain _ensure_thumbnail into long + short render paths"
```

---

## Task 3: Soft upload-time warning when thumbnail missing

**Files:**
- Modify: `engine/run_auto.py` — `cmd_approve` upload path (the `thumb`/`sthumb` resolution lines)
- Test: `tests/test_run_auto_thumbnail.py` (append warning test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_auto_thumbnail.py`:

```python
def test_cmd_approve_warns_when_thumbnail_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_auto, "_ROOT", str(tmp_path))
    idea = _idea(tmp_path)
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda _id: idea)
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    monkeypatch.setattr(run_auto, "_load_metadata", lambda p: {"title": "T", "description": "d", "tags": []})
    monkeypatch.setattr(run_auto.uploader, "upload", lambda video_path, **kw: "VID123")
    run_auto.cmd_approve("pubid", public=False, dry_run=False)
    out = capsys.readouterr().out
    assert "default" in out.lower()   # warns about default-frame upload
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_run_auto_thumbnail.py::test_cmd_approve_warns_when_thumbnail_absent -q`
Expected: FAIL — no warning printed yet (assert on "default" fails).

- [ ] **Step 3: Add the warning (long path)**

In `engine/run_auto.py`, in `cmd_approve`, replace the long-thumb resolution:

```python
        thumb = paths.thumbnail_path(idea_id, "long")
        thumb = thumb if os.path.exists(thumb) else None
```

with:

```python
        thumb = paths.thumbnail_path(idea_id, "long")
        if not os.path.exists(thumb):
            print(f"⚠ {idea_id}: no custom thumbnail — uploading with YouTube's default frame")
            thumb = None
```

- [ ] **Step 4: Add the warning (companion short path)**

In the same function, in the companion-short block, replace:

```python
                sthumb = paths.thumbnail_path(idea_id, "short")
                sthumb = sthumb if os.path.exists(sthumb) else None
```

with:

```python
                sthumb = paths.thumbnail_path(idea_id, "short")
                if not os.path.exists(sthumb):
                    print(f"⚠ {idea_id}: companion short has no custom thumbnail — uploading with default frame")
                    sthumb = None
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_run_auto_thumbnail.py -q`
Expected: PASS — including the pre-existing `test_cmd_approve_omits_thumbnail_when_absent` (still gets `thumbnail_path=None`) and the new warning test.

- [ ] **Step 6: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto_thumbnail.py
git commit -m "feat(thumbnail): warn at approve time when uploading without a custom thumbnail"
```

---

## Task 4: Docs sync

**Files:**
- Modify: `CLAUDE.md` (pipeline-layout row)
- Modify: `.claude/skills/thumbnail-assets/SKILL.md`

- [ ] **Step 1: Update `CLAUDE.md`**

In the `engine/pipeline/` Layout row, change the thumbnail-subject note from "must be sourced manually / by hand" framing to reflect auto-chaining. Replace the parenthetical:

> (thumbnail subjects can be auto-sourced via `run_subject` (Wikimedia Commons → Pexels), or dropped by hand at `produced/<id>/<fmt>/subject.png`)

with:

> (thumbnails are auto-composited on render — `run_auto` chains `run_subject` (Wikipedia → Pexels) + `run_thumbnail` after each render; a human `subject.png`/`thumbnail.jpg` always wins. `run_subject`/`run_thumbnail` remain the manual override / force-regen path.)

- [ ] **Step 2: Update the `thumbnail-assets` skill**

In `.claude/skills/thumbnail-assets/SKILL.md`, add a note near the top that thumbnails now auto-generate on render, so this skill is the **manual override / force-regen** path (delete `thumbnail.jpg` to force a regen; a hand-supplied `subject.png` or `thumbnail.jpg` always wins). Keep the existing command reference intact.

- [ ] **Step 3: Run the full suite (contract)**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (full suite green).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md .claude/skills/thumbnail-assets/SKILL.md
git commit -m "docs(thumbnail): note thumbnails auto-chain on render; skill is override path"
```

---

## Self-Review

**Spec coverage:**
- Q1=A trigger in `_render_and_qc` + `_companion_short` → Task 2. ✓
- Q2=A self-stub + warn → Task 1 (`source==None` branch, exception swallow) + soft upload warning → Task 3. ✓
- Q3=A skip-if-exists → Task 1 (skip branch + test 1). ✓
- In-process imports / two-venv split → Task 1 Step 3. ✓
- Tests 1-4 from spec → Task 1 Steps 1. ✓
- Docs (CLAUDE.md + skill) → Task 4. ✓

**Placeholder scan:** none — every step has concrete code/commands. ✓

**Type consistency:** helper is `_ensure_thumbnail(idea_id: str, fmt: str) -> None` everywhere; `source_subject(idea, fmt) -> dict` with `res["source"]` key matches `run_subject.py` usage; `generate_thumbnail(idea, fmt)` matches `run_thumbnail.py`. ✓

## Rollout

Ship via the `ship-video-change` rail: branch `feat/auto-thumbnail-render` off `main`, `python3 -m pytest tests/ -q`, dual adversarial review (Codex + Claude code-reviewer, gate 0 Critical + 0 Important from both), `gh pr create --base main` with `Adversarial-Reviewed: <agentId>` trailer, squash-merge.
