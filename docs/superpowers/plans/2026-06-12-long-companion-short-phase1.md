# Long + Companion-Short Pipeline — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship full long-form videos for the 5 already-published short topics, end-to-end (produce → fact-gate → render → upload unlisted), and back-link each existing published short to its new long.

**Architecture:** Introduce a format-namespaced artifact layout (`produced/<id>/long/` and `produced/<id>/short/`) via one central path module, thread a `fmt` ("long" default) through produce/video/factcheck/qc/run_auto, split the queue's single `youtube_url` into `long_youtube_url`/`short_youtube_url`, and add a YouTube description-patch capability so a long's URL can be appended to its already-published short's description.

**Tech Stack:** Python 3 (main env, `python3 -m pytest tests/ -q`), Remotion render via `.venv-video`, YouTube Data API v3 (`googleapiclient`), pytest + monkeypatch.

**Scope note:** This plan is Phase 1 only. Phase 2 (overnight `run_auto` auto-deriving companion shorts via `derive_short_tease`) is deferred to its own plan after the longs prove out. See `docs/superpowers/specs/2026-06-12-long-companion-short-pipeline-design.md`.

**Spec reference:** `docs/superpowers/specs/2026-06-12-long-companion-short-pipeline-design.md`

---

### Task 1: Central path module (`engine/paths.py`)

**Files:**
- Create: `engine/paths.py`
- Test: `tests/test_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paths.py
import os
import pytest
from engine import paths


def test_artifact_dir_is_format_namespaced():
    d = paths.artifact_dir("abc123", "long")
    assert d.endswith(os.path.join("produced", "abc123", "long"))


def test_artifact_dir_rejects_unknown_format():
    with pytest.raises(ValueError):
        paths.artifact_dir("abc123", "landscape")


def test_named_paths_sit_under_format_dir():
    assert paths.script_path("x", "short").endswith(
        os.path.join("produced", "x", "short", "script.md"))
    assert paths.metadata_path("x", "long").endswith(
        os.path.join("produced", "x", "long", "metadata.json"))
    assert paths.factcheck_path("x", "long").endswith(
        os.path.join("produced", "x", "long", "factcheck.json"))
    assert paths.qc_path("x", "long").endswith(
        os.path.join("produced", "x", "long", "qc.json"))
    assert paths.video_dir("x", "long").endswith(
        os.path.join("produced", "x", "long", "video"))


def test_all_paths_share_artifact_dir_root():
    base = paths.artifact_dir("x", "long")
    for p in (paths.script_path("x", "long"), paths.metadata_path("x", "long"),
              paths.video_dir("x", "long")):
        assert p.startswith(base)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_paths.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.paths'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/paths.py
"""Single source of truth for produced-artifact locations.

Artifacts are namespaced by output format so a long and its companion short can
coexist for one idea without clobbering each other:

    produced/<id>/long/   script.md  metadata.json  factcheck.json  qc.json  video/
    produced/<id>/short/  script.md  metadata.json  factcheck.json  qc.json  video/
"""
from __future__ import annotations
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCED_DIR = os.path.join(_ROOT, "produced")
FORMATS = ("long", "short")


def artifact_dir(idea_id: str, fmt: str) -> str:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    return os.path.join(PRODUCED_DIR, idea_id, fmt)


def script_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "script.md")


def metadata_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "metadata.json")


def factcheck_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "factcheck.json")


def qc_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "qc.json")


def video_dir(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "video")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_paths.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/paths.py tests/test_paths.py
git commit -m "feat(paths): format-namespaced produced-artifact path helpers"
```

---

### Task 2: Queue field split + migration (`engine/queue_manager.py`)

The queue stores a single `youtube_url`. For back-linking we need to know which URL is the long and which is the short. Split into `long_youtube_url` / `short_youtube_url`. The existing 5 published uploads are shorts, so migration moves any legacy `youtube_url` → `short_youtube_url`.

**Files:**
- Modify: `engine/queue_manager.py` (add `split_youtube_url_field` after `update_idea`, ~line 161)
- Test: `tests/test_queue_migration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_queue_migration.py
import json
from engine import queue_manager as q


def _seed(tmp_path, monkeypatch, ideas):
    qf = tmp_path / "idea_queue.json"
    qf.write_text(json.dumps(ideas))
    monkeypatch.setattr(q, "QUEUE_FILE", str(qf))
    return qf


def test_migration_moves_youtube_url_to_short(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [
        {"id": "a", "status": "published", "youtube_url": "https://youtu.be/AAA"},
    ])
    moved = q.split_youtube_url_field()
    assert moved == 1
    idea = q.get_by_id("a")
    assert idea["short_youtube_url"] == "https://youtu.be/AAA"


def test_migration_is_idempotent_and_skips_when_short_set(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, [
        {"id": "a", "youtube_url": "https://youtu.be/AAA",
         "short_youtube_url": "https://youtu.be/EXISTING"},
        {"id": "b", "status": "pending"},
    ])
    moved = q.split_youtube_url_field()
    assert moved == 0
    assert q.get_by_id("a")["short_youtube_url"] == "https://youtu.be/EXISTING"
```

> Note: `queue_manager` reads `QUEUE_FILE` from `engine.config` at import as a module global, so the test monkeypatches `q.QUEUE_FILE` directly (the `_load`/`_save` functions reference the module-level name).

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_queue_migration.py -q`
Expected: FAIL — `AttributeError: module 'engine.queue_manager' has no attribute 'split_youtube_url_field'`

- [ ] **Step 3: Write minimal implementation**

Add after `update_idea` (after line 161):

```python
def split_youtube_url_field() -> int:
    """One-time migration: move a legacy single `youtube_url` to `short_youtube_url`
    (the existing published uploads are all shorts). Idempotent — skips any idea that
    already has `short_youtube_url`. Returns the number of ideas migrated."""
    ideas = _load()
    moved = 0
    for idea in ideas:
        if idea.get("youtube_url") and not idea.get("short_youtube_url"):
            idea["short_youtube_url"] = idea["youtube_url"]
            moved += 1
    if moved:
        _save(ideas)
    return moved
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_queue_migration.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/queue_manager.py tests/test_queue_migration.py
git commit -m "feat(queue): split youtube_url into long/short + migration"
```

---

### Task 3: YouTube description patch (`engine/publish/uploader.py`)

`videos().update(part="snippet")` requires the **full** snippet — sending only `description` clears `title`/`categoryId`. So we `list` the current snippet, mutate description, and send the whole snippet back. `append_to_description` builds on that for back-linking.

**Files:**
- Modify: `engine/publish/uploader.py` (add after `upload`, ~line 94)
- Test: `tests/test_uploader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_uploader.py
from engine.publish import uploader


class _FakeReq:
    def __init__(self, result): self._result = result
    def execute(self): return self._result


class _FakeVideos:
    def __init__(self, snippet):
        self._snippet = snippet
        self.update_body = None
    def list(self, part, id):
        return _FakeReq({"items": [{"snippet": dict(self._snippet)}]})
    def update(self, part, body):
        self.update_body = body
        return _FakeReq(body)


class _FakeYouTube:
    def __init__(self, snippet): self._videos = _FakeVideos(snippet)
    def videos(self): return self._videos


def test_update_description_preserves_title_and_category():
    yt = _FakeYouTube({"title": "T", "categoryId": "17", "description": "old"})
    uploader.update_description("vid1", "brand new", service=yt)
    body = yt._videos.update_body
    assert body["id"] == "vid1"
    assert body["snippet"]["description"] == "brand new"
    assert body["snippet"]["title"] == "T"          # not clobbered
    assert body["snippet"]["categoryId"] == "17"    # not clobbered


def test_append_to_description_appends_suffix():
    yt = _FakeYouTube({"title": "T", "categoryId": "17", "description": "watch this"})
    new_desc = uploader.append_to_description("vid1", "Full story: https://youtu.be/LLL",
                                              service=yt)
    assert new_desc.startswith("watch this")
    assert "Full story: https://youtu.be/LLL" in new_desc
    assert yt._videos.update_body["snippet"]["description"] == new_desc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_uploader.py -q`
Expected: FAIL — `AttributeError: module 'engine.publish.uploader' has no attribute 'update_description'`

- [ ] **Step 3: Write minimal implementation**

Add after `upload` (after line 94):

```python
def _service(service):
    if service is not None:
        return service
    from engine.publish.auth import get_service
    return get_service()


def update_description(video_id: str, new_description: str, *, service=None) -> str:
    """Replace a live video's description. videos.update needs the FULL snippet, so
    we list the current snippet, swap only the description, and send it all back —
    sending description alone would wipe title/categoryId. Returns the new description."""
    youtube = _service(service)
    snippet = youtube.videos().list(part="snippet", id=video_id).execute()["items"][0]["snippet"]
    snippet["description"] = new_description[:5000]
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    return snippet["description"]


def append_to_description(video_id: str, suffix: str, *, service=None) -> str:
    """Append `suffix` (e.g. a companion-long link) to a live video's existing
    description, preserving the rest of the snippet. Returns the new description."""
    youtube = _service(service)
    snippet = youtube.videos().list(part="snippet", id=video_id).execute()["items"][0]["snippet"]
    base = (snippet.get("description") or "").rstrip()
    new_desc = (f"{base}\n\n{suffix}" if base else suffix)[:5000]
    snippet["description"] = new_desc
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    return new_desc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_uploader.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/publish/uploader.py tests/test_uploader.py
git commit -m "feat(uploader): update_description + append_to_description (full-snippet safe)"
```

---

### Task 4: Thread `fmt` through `run_produce`

Replace the `--short` flag with `--format {long,short}` (default `long`), keep `--short` as a back-compat alias, and route all artifact paths through `engine.paths`.

**Files:**
- Modify: `engine/run_produce.py`
- Test: `tests/test_run_produce.py` (update existing)

- [ ] **Step 1: Read the existing test to learn the produce fixture pattern**

Run: `sed -n '1,60p' tests/test_run_produce.py`
Note how it monkeypatches `generate_script`/`generate_short_script`, `generate_metadata`/`generate_short_metadata`, `factcheck`, and `q.update_idea`, and how it sets the produced root.

- [ ] **Step 2: Add a failing test for the new layout**

Add to `tests/test_run_produce.py`:

```python
def test_produce_writes_under_long_subdir(tmp_path, monkeypatch):
    from engine import run_produce, paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_produce.q, "update_idea", lambda i, **f: True)
    monkeypatch.setattr(run_produce, "generate_script", lambda idea: "Long body words here.")
    monkeypatch.setattr(run_produce, "generate_metadata",
                        lambda idea, s: {"title": "T", "description": "D", "tags": []})
    idea = {"id": "zz", "title_variants": ["My Title"]}
    run_produce.produce(idea, factcheck_enabled=False, fmt="long")
    assert (tmp_path / "produced" / "zz" / "long" / "script.md").exists()
    assert (tmp_path / "produced" / "zz" / "long" / "metadata.json").exists()
```

> If existing tests call `produce(..., short=True)`, update those call sites to `fmt="short"` in the same edit.

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_run_produce.py::test_produce_writes_under_long_subdir -q`
Expected: FAIL — `produce()` has no `fmt` kwarg / writes to flat path.

- [ ] **Step 4: Edit `run_produce.py`**

Add the import near the top imports (after line 22):
```python
from engine import paths
```

Change the `produce` signature (line 57-58) from `short: bool = False` to:
```python
def produce(idea: dict, metadata_only: bool = False, factcheck_enabled: bool = True,
            autofix: bool = True, max_claims: int = 25, fmt: str = "long") -> dict:
```

At the top of the body, derive `short` and the artifact dir; replace line 67 (`out_dir = os.path.join(PRODUCED_DIR, idea_id)`):
```python
    short = fmt == "short"
    out_dir = paths.artifact_dir(idea_id, fmt)
```

Replace every artifact path that used `out_dir`/`os.path.join(out_dir, ...)` so they go through `paths` (these already resolve under `out_dir`, so they are correct once `out_dir = artifact_dir(...)` — no further change needed for `script_file`, `metadata_file`, `factcheck.json`). Confirm `os.makedirs(out_dir, exist_ok=True)` (line 86) stays.

In `main()`, replace the `--short` arg (lines 167-168) with:
```python
    ap.add_argument("--format", choices=["long", "short"], default="long",
                    help="output format (default: long-form)")
    ap.add_argument("--short", action="store_true",
                    help="alias for --format short (back-compat)")
```

And the produce call (lines 181-184) — compute fmt from args:
```python
            fmt = "short" if (args.short or args.format == "short") else "long"
            r = produce(idea, metadata_only=args.metadata_only,
                        factcheck_enabled=not args.no_factcheck,
                        autofix=not args.no_autofix, max_claims=args.max_claims,
                        fmt=fmt)
```

- [ ] **Step 5: Run the produce tests**

Run: `python3 -m pytest tests/test_run_produce.py -q`
Expected: PASS (all, including the new test)

- [ ] **Step 6: Commit**

```bash
git add engine/run_produce.py tests/test_run_produce.py
git commit -m "feat(produce): --format long|short writes under produced/<id>/<fmt>/"
```

---

### Task 5: Thread `fmt` through `run_video`

`--format` currently selects dimensions (`landscape|short`). Change choices to `{long,short}` (default `long`), make `long` mean landscape dimensions, and route `script_file`/`video_dir` through `engine.paths`.

**Files:**
- Modify: `engine/run_video.py`

- [ ] **Step 1: Edit the imports**

Add after line 29 (`from engine import queue_manager as q`):
```python
from engine import paths
```

- [ ] **Step 2: Change the `--format` argument (lines 49-50)**

```python
    ap.add_argument("--format", choices=["long", "short"], default="long",
                    help="output format: long (1920×1080 landscape, default) or "
                    "short (1080×1920 vertical)")
```

- [ ] **Step 3: Route artifact paths through `paths` (lines 57 and 64)**

Replace:
```python
    script_file = os.path.join(_ROOT, "produced", args.id, "script.md")
```
with:
```python
    script_file = paths.script_path(args.id, args.format)
```

Replace:
```python
    video_dir = os.path.join(_ROOT, "produced", args.id, "video")
```
with:
```python
    video_dir = paths.video_dir(args.id, args.format)
```

- [ ] **Step 4: Update the dimension flag (line 102)**

Replace:
```python
        is_short = args.format == "short"
```
with (semantically identical, kept explicit for clarity):
```python
        is_short = args.format == "short"
```
> No change needed — `is_short` already keys off `"short"`, and `long` falls through to landscape dimensions. The metadata path derivation at line 139 (`dirname(abspath(video_dir))`) now resolves to `produced/<id>/<fmt>/metadata.json`, matching what `run_produce` wrote.

- [ ] **Step 5: Sanity-check compose imports (no functional change)**

Run: `python3 -c "import engine.run_video"`
Expected: no error.

- [ ] **Step 6: Commit**

```bash
git add engine/run_video.py
git commit -m "feat(video): --format long|short reads/writes produced/<id>/<fmt>/"
```

---

### Task 6: Thread `fmt` through `run_factcheck`, `qc`, and `run_auto`

Keep the overnight job and approval flow consistent with the new layout (default `long`). Update the one approve test that asserts `youtube_url`.

**Files:**
- Modify: `engine/run_factcheck.py`, `engine/pipeline/qc.py`, `engine/run_auto.py`
- Test: `tests/test_run_auto.py`, `tests/test_qc.py` (update existing)

- [ ] **Step 1: `run_factcheck.py` — add `--format`, route via paths**

Add after line 21 (`from engine.pipeline import factcheck`):
```python
from engine import paths
```
Add the arg after line 47 (`ap.add_argument("--id", required=True)`):
```python
    ap.add_argument("--format", choices=["long", "short"], default="long")
```
Replace lines 52-53:
```python
    script_file = os.path.join(_ROOT, "produced", args.id, "script.md")
    fc_path = os.path.join(_ROOT, "produced", args.id, "factcheck.json")
```
with:
```python
    script_file = paths.script_path(args.id, args.format)
    fc_path = paths.factcheck_path(args.id, args.format)
```

- [ ] **Step 2: `qc.py` — `qc_video(idea_id, fmt="long")`**

Add at top imports (after line 9, `from engine import config`):
```python
from engine import paths
```
Change `qc_video` (line 108) signature and the path block (lines 111-115):
```python
def qc_video(idea_id: str, fmt: str = "long") -> dict:
    """Run all local checks on produced/<id>/<fmt>/video and write that dir's qc.json.
    Returns {'passed': bool, 'checks': [...]}. Never raises — missing inputs fail a check."""
    base = paths.artifact_dir(idea_id, fmt)
    vdir = paths.video_dir(idea_id, fmt)
    video = os.path.join(vdir, "video.mp4")
    audio = os.path.join(vdir, "narration.wav")
    props = os.path.join(vdir, "props.json")
    audio_dur = _ffprobe_duration(audio) or 0.0
```
> The `os.makedirs(base, ...)` and `qc.json` write at lines 124-126 already use `base`, now the `<fmt>` dir — correct.

- [ ] **Step 3: Add failing test for `run_auto` long_youtube_url + verify qc fmt**

In `tests/test_run_auto.py`, update `test_cmd_approve_uploads_and_marks_published` to assert the new field:
```python
    run_auto.cmd_approve("x", public=False, dry_run=False)
    assert calls["privacy"] == "unlisted"
    assert seen["status"] == "published"
    assert "yt123" in seen["long_youtube_url"]   # was youtube_url
```

In `tests/test_qc.py`, ensure any direct `qc_video("id")` call still passes (default fmt="long"); add:
```python
def test_qc_video_uses_format_subdir(monkeypatch, tmp_path):
    from engine.pipeline import qc
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    import os
    vdir = tmp_path / "produced" / "x" / "long" / "video"
    vdir.mkdir(parents=True)
    report = qc.qc_video("x", "long")           # no inputs → checks fail, but no crash
    assert "passed" in report
    assert (tmp_path / "produced" / "x" / "long" / "qc.json").exists()
```

- [ ] **Step 4: Run to verify the approve test fails**

Run: `python3 -m pytest tests/test_run_auto.py::test_cmd_approve_uploads_and_marks_published -q`
Expected: FAIL — code still writes `youtube_url`.

- [ ] **Step 5: `run_auto.py` — thread fmt + write long_youtube_url**

Add after line 13 (`from engine import queue_manager as q`):
```python
from engine import paths
```
`_produce_one` (line 43) — pass `--format long`:
```python
    rc = _run([sys.executable, "-m", "engine.run_produce", "--id", idea_id,
               "--format", "long"],
              timeout=config.PRODUCE_TIMEOUT_S)
```
`_render_one` (lines 54-55) — pass `--format long`:
```python
    rc = _run([_VENV_PY, "-m", "engine.run_video", "--id", idea_id,
               "--render", "--mode", "narrated", "--format", "long"],
              timeout=config.RENDER_TIMEOUT_S)
```
`_render_and_qc` (line 73) — `qc.qc_video(idea_id, "long")`.
`_qc_summary` (line 130) — replace path:
```python
    path = paths.qc_path(idea_id, "long")
```
`cmd_approve` (lines 195-196) — write the long field:
```python
    q.update_idea(idea_id, status="published",
                  long_youtube_url=f"https://youtu.be/{yt_id}")
```

- [ ] **Step 6: Run the full suites**

Run: `python3 -m pytest tests/test_run_auto.py tests/test_qc.py tests/test_run_produce.py -q`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add engine/run_factcheck.py engine/pipeline/qc.py engine/run_auto.py tests/test_run_auto.py tests/test_qc.py
git commit -m "feat(auto): thread fmt=long through factcheck/qc/run_auto; write long_youtube_url"
```

---

### Task 7: Back-link command (`run_auto --backlink <id>`)

Append the long's URL to its already-published short's YouTube description.

**Files:**
- Modify: `engine/run_auto.py`
- Test: `tests/test_run_auto.py`

- [ ] **Step 1: Write the failing test**

```python
def test_cmd_backlink_appends_long_url_to_short(monkeypatch):
    idea = {"id": "x",
            "long_youtube_url": "https://youtu.be/LONG",
            "short_youtube_url": "https://youtu.be/SHORT"}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    calls = {}
    monkeypatch.setattr(run_auto.uploader, "append_to_description",
                        lambda vid, suffix, **k: calls.update(vid=vid, suffix=suffix) or "newdesc")
    run_auto.cmd_backlink("x")
    assert calls["vid"] == "SHORT"            # extracted the short's video id
    assert "https://youtu.be/LONG" in calls["suffix"]


def test_cmd_backlink_refuses_without_both_urls(monkeypatch):
    monkeypatch.setattr(run_auto.q, "get_by_id",
                        lambda i: {"id": "x", "short_youtube_url": "https://youtu.be/SHORT"})
    import pytest
    with pytest.raises(SystemExit):
        run_auto.cmd_backlink("x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_run_auto.py::test_cmd_backlink_appends_long_url_to_short -q`
Expected: FAIL — `cmd_backlink` not defined.

- [ ] **Step 3: Implement `cmd_backlink` and wire the CLI**

Add after `cmd_approve` (after line 197):
```python
def _video_id(url: str) -> str:
    """Extract the YouTube video id from a youtu.be/<id> or watch?v=<id> URL."""
    url = url.strip()
    if "watch?v=" in url:
        return url.split("watch?v=")[1].split("&")[0]
    return url.rstrip("/").split("/")[-1].split("?")[0]


def cmd_backlink(idea_id: str) -> None:
    """Append the idea's long URL to its already-published short's description."""
    idea = q.get_by_id(idea_id) or {}
    long_url = idea.get("long_youtube_url")
    short_url = idea.get("short_youtube_url")
    if not (long_url and short_url):
        sys.exit(f"{idea_id}: need both long_youtube_url and short_youtube_url "
                 f"(long={long_url!r}, short={short_url!r})")
    suffix = f"▶ Full story on our channel: {long_url}"
    uploader.append_to_description(_video_id(short_url), suffix)
    q.update_idea(idea_id, short_backlinked=True)
    print(f"✓ {idea_id}: back-linked short {short_url} → {long_url}")
```

Add the CLI arg after line 211 (`--reject`):
```python
    ap.add_argument("--backlink", metavar="ID",
                    help="append the long's URL to its published short's description")
```
And the dispatch after the `--approve` branch (after line 222):
```python
    elif args.backlink:
        cmd_backlink(args.backlink)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_run_auto.py -q`
Expected: PASS (all, including 2 new)

- [ ] **Step 5: Full suite + commit**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (whole suite green)

```bash
git add engine/run_auto.py tests/test_run_auto.py
git commit -m "feat(auto): --backlink appends long URL to published short description"
```

---

### Task 8: Produce → fact-gate → render ONE long (Senna) — REVIEW GATE

Runbook task. No code; uses the CLI built above. **Stops for the user to watch the Senna long and decide before the other four.**

- [ ] **Step 1: Migrate the 5's youtube_url → short_youtube_url**

Run:
```bash
python3 -c "from engine import queue_manager as q; print('migrated', q.split_youtube_url_field())"
```
Expected: prints `migrated 4` (the 4 with `youtube_url`; `0c76c4c4` is `in_production` and may already differ — verify below).

Verify all 5 now have `short_youtube_url`:
```bash
python3 -c "
from engine import queue_manager as q
for i in ('0c76c4c4','46dbfcda','0eaa1b66','5b98b1fc','a31759e2'):
    d=q.get_by_id(i); print(i, d.get('short_youtube_url'))
"
```
Expected: each prints its `https://youtu.be/...` short URL. If any is `None`, set it explicitly from the spec's table before continuing:
```bash
python3 -c "from engine import queue_manager as q; q.update_idea('0c76c4c4', short_youtube_url='https://youtu.be/yhClmmEGEHM')"
```

- [ ] **Step 2: Produce the Senna long (with fact-gate)**

Run:
```bash
python3 -m engine.run_produce --id 0c76c4c4 --format long
```
Expected: writes `produced/0c76c4c4/long/script.md` (~1,000–1,500 words), `metadata.json`, `factcheck.json`; idea status → `in_production` (fact-gate passed) or `needs_review`.

- [ ] **Step 3: If needs_review, fact-review before rendering**

If status is `needs_review`, run the standalone gate and resolve per the integrity rule (do NOT render an unverified long):
```bash
python3 -m engine.run_factcheck --id 0c76c4c4 --format long --fix
```
Re-run until it exits 0, or use the `fact-review` skill. Then mark cleared if hand-fixed:
```bash
python3 -m engine.run_auto --review 0c76c4c4 --note "fact-reviewed long"
```

- [ ] **Step 4: Render the Senna long (local, ~45 min)**

Run (video venv — required, per CLAUDE.md):
```bash
.venv-video/bin/python -m engine.run_video --id 0c76c4c4 --mode narrated --format long --render
```
Expected: `produced/0c76c4c4/long/video/video.mp4` written; queue `video_path` updated.

- [ ] **Step 5: STOP — hand off to the user**

Tell the user the long is rendered at `produced/0c76c4c4/long/video/video.mp4` and ask them to watch and decide. **Do not proceed to Task 9 until the user approves the quality.**

---

### Task 9: The other 4 longs + upload + back-link all 5

Runbook task. Only after the user approves the Senna long in Task 8.

- [ ] **Step 1: Produce the other 4 longs**

Run (sequential — respects API rate limit):
```bash
for id in 46dbfcda 0eaa1b66 5b98b1fc a31759e2; do
  python3 -m engine.run_produce --id "$id" --format long
done
```
Expected: each writes `produced/<id>/long/{script.md,metadata.json,factcheck.json}`. Resolve any `needs_review` per Task 8 Step 3 before rendering that idea.

- [ ] **Step 2: Render the other 4 longs (local, ~45 min each)**

Run:
```bash
for id in 46dbfcda 0eaa1b66 5b98b1fc a31759e2; do
  .venv-video/bin/python -m engine.run_video --id "$id" --mode narrated --format long --render
done
```

- [ ] **Step 3: QC + mark awaiting_approval, then upload each long unlisted**

For each of the 5 ids, set `awaiting_approval` (run_auto's approve refuses any other status) then approve (unlisted — NEVER `--public`):
```bash
for id in 0c76c4c4 46dbfcda 0eaa1b66 5b98b1fc a31759e2; do
  python3 -c "from engine import queue_manager as q; q.update_idea('$id', status='awaiting_approval')"
  python3 -m engine.run_auto --approve "$id"   # uploads long unlisted → long_youtube_url
done
```
Expected: each prints `✓ published <id> → https://youtu.be/... (unlisted)` and sets `long_youtube_url`.

> If QC is desired first, run `python3 -c "from engine.pipeline import qc; print(qc.qc_video('<id>','long'))"` and inspect `passed` before approving.

- [ ] **Step 4: Back-link all 5 published shorts to their new longs**

```bash
for id in 0c76c4c4 46dbfcda 0eaa1b66 5b98b1fc a31759e2; do
  python3 -m engine.run_auto --backlink "$id"
done
```
Expected: each prints `✓ <id>: back-linked short ... → ...`; the 5 published shorts' YouTube descriptions now carry `▶ Full story on our channel: <long_url>`.

- [ ] **Step 5: Final verification + hand off**

Run: `python3 -m pytest tests/ -q` (contract) and confirm the 5 longs are unlisted on the channel and the 5 shorts' descriptions show the long link. Report results to the user.

---

## Self-Review

**Spec coverage:**
- Artifact split (`engine/paths.py`) → Task 1; threaded through produce/video/factcheck/qc/run_auto → Tasks 4-6. ✅
- Queue `long_youtube_url`/`short_youtube_url` + migration → Task 2. ✅
- `update_description` (full-snippet safe) → Task 3. ✅
- Cross-link/back-link op → Task 7; applied to the 5 → Task 9 Step 4. ✅
- 5 longs end-to-end with one-then-four review gate → Tasks 8-9. ✅
- Phase 2 (`derive_short_tease`, short EndCTA, overnight companion) → explicitly deferred to its own plan (scope note). ✅
- Integrity gate respected (fact-review before rendering needs_review) → Task 8 Step 3, Task 9 Step 1. ✅
- Unlisted-only, never `--public` → Task 9 Step 3. ✅

**Placeholder scan:** No TBD/TODO; every code step shows full code or an exact edit; every command has expected output. ✅

**Type consistency:** `fmt` ("long"/"short") used uniformly across `paths.*`, `produce(fmt=...)`, `run_video --format`, `qc_video(idea_id, fmt)`. Field names `long_youtube_url`/`short_youtube_url` consistent across Tasks 2, 6, 7, 9. `append_to_description(video_id, suffix, *, service)` signature matches its caller in `cmd_backlink` and its test. ✅
