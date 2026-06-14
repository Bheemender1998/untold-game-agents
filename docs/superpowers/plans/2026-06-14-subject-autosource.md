# Auto-source Subject Photos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `run_subject --id <id> --format <fmt>` populates `produced/<id>/<fmt>/subject.png` automatically — the person's Wikipedia lead image, else a generic Pexels stock photo — without overwriting a human-supplied photo, capturing attribution.

**Architecture:** Reuse the existing Wikipedia API module + Pexels key. New `wikipedia.lead_image`, `footage.fetch_photo`, an orchestrator `engine/pipeline/subject.py`, and a `run_subject` CLI. Everything self-stubs on failure.

**Tech Stack:** Python 3, `requests` (Wikipedia), `urllib` (Pexels), `anthropic` (subject extraction), Pillow downstream. `python3 -m pytest tests/ -q`.

**Spec:** `docs/superpowers/specs/2026-06-14-subject-autosource-design.md`
**Branch:** `feat/subject-autosource` (checked out).

**Conventions:** `python3` only; absolute `engine.*` imports; PostToolUse hook runs pytest (TDD-red OK mid-task); network/LLM are NEVER test gates — mock them.

---

## Task 1: `wikipedia.lead_image` + `_image_credit`

**Files:** Modify `engine/ideate/wikipedia.py`. Test: `tests/test_wikipedia.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_wikipedia.py`:

```python
def test_lead_image_returns_url_and_credit(monkeypatch):
    from engine.ideate import wikipedia

    class _Resp:
        def __init__(self, data): self._d = data
        def json(self): return self._d

    calls = {"n": 0}
    def fake_get(url, **kw):
        params = kw.get("params", {})
        if params.get("list") == "search":   # search_title
            return _Resp({"query": {"search": [{"title": "Felipe Massa"}]}})
        if params.get("prop") == "pageimages":
            return _Resp({"query": {"pages": {"1": {
                "original": {"source": "https://up.wikimedia.org/massa.jpg", "width": 2000},
                "pageimage": "Felipe_Massa.jpg"}}}})
        if params.get("prop") == "imageinfo":
            return _Resp({"query": {"pages": {"1": {"imageinfo": [{"extmetadata": {
                "Artist": {"value": "<a href='x'>Jane Doe</a>"},
                "LicenseShortName": {"value": "CC BY 2.0"}}}]}}}})
        return _Resp({})
    monkeypatch.setattr(wikipedia.requests, "get", fake_get)

    out = wikipedia.lead_image("Felipe Massa")
    assert out is not None
    url, credit = out
    assert url == "https://up.wikimedia.org/massa.jpg"
    assert "Jane Doe" in credit and "CC BY 2.0" in credit and "Wikimedia Commons" in credit
    assert "<a" not in credit  # HTML stripped


def test_lead_image_none_when_no_image(monkeypatch):
    from engine.ideate import wikipedia
    class _Resp:
        def __init__(self, d): self._d = d
        def json(self): return self._d
    def fake_get(url, **kw):
        if kw.get("params", {}).get("list") == "search":
            return _Resp({"query": {"search": [{"title": "Obscure Thing"}]}})
        return _Resp({"query": {"pages": {"1": {}}}})  # no 'original'
    monkeypatch.setattr(wikipedia.requests, "get", fake_get)
    assert wikipedia.lead_image("Obscure Thing") is None


def test_lead_image_rejects_svg(monkeypatch):
    from engine.ideate import wikipedia
    class _Resp:
        def __init__(self, d): self._d = d
        def json(self): return self._d
    def fake_get(url, **kw):
        if kw.get("params", {}).get("list") == "search":
            return _Resp({"query": {"search": [{"title": "Logo Page"}]}})
        return _Resp({"query": {"pages": {"1": {"original": {"source": "https://x/logo.svg", "width": 3000}}}}})
    monkeypatch.setattr(wikipedia.requests, "get", fake_get)
    assert wikipedia.lead_image("Logo Page") is None  # SVG → Pillow can't open → reject
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_wikipedia.py::test_lead_image_returns_url_and_credit -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'lead_image'`.

- [ ] **Step 3: Implement**

Add to `engine/ideate/wikipedia.py` (after `extract`); add `import re` at the top with the other imports:

```python
def lead_image(query: str, min_width: int = 600) -> tuple[str, str] | None:
    """The lead/infobox image URL + attribution for the best-matching Wikipedia page, or None.
    Rejects SVGs (Pillow can't open them) and images narrower than `min_width`. Never raises."""
    try:
        title = search_title(query)
        if not title:
            return None
        headers = {"User-Agent": _UA}
        r = requests.get(_API, timeout=_TIMEOUT, headers=headers, params={
            "action": "query", "titles": title, "prop": "pageimages",
            "piprop": "original|name", "format": "json"})
        page = next(iter(r.json().get("query", {}).get("pages", {}).values()), {}) or {}
        original = page.get("original") or {}
        url = original.get("source")
        if not url or url.lower().endswith(".svg") or (original.get("width") or 0) < min_width:
            return None
        return url, _image_credit(page.get("pageimage"), headers)
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return None


def _image_credit(file_name: str | None, headers: dict) -> str:
    """'<artist> / <license> via Wikimedia Commons' for a File: name; best-effort, never raises."""
    base = "via Wikimedia Commons"
    if not file_name:
        return base
    try:
        r = requests.get(_API, timeout=_TIMEOUT, headers=headers, params={
            "action": "query", "titles": f"File:{file_name}", "prop": "imageinfo",
            "iiprop": "extmetadata", "format": "json"})
        page = next(iter(r.json().get("query", {}).get("pages", {}).values()), {}) or {}
        meta = (page.get("imageinfo") or [{}])[0].get("extmetadata", {}) or {}
        artist = re.sub(r"<[^>]+>", "", (meta.get("Artist", {}) or {}).get("value", "")).strip()
        lic = ((meta.get("LicenseShortName", {}) or {}).get("value", "")).strip()
        parts = [p for p in (artist, lic) if p]
        return (" / ".join(parts) + " " + base) if parts else base
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return base
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_wikipedia.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/ideate/wikipedia.py tests/test_wikipedia.py
git commit -m "feat(subject): wikipedia.lead_image — lead portrait + attribution"
```

---

## Task 2: `footage.fetch_photo`

**Files:** Modify `engine/video/footage.py`. Test: `tests/test_footage.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_footage.py`:

```python
def test_fetch_photo_returns_credit(monkeypatch, tmp_path):
    import io, json as _json
    from engine.video import footage
    monkeypatch.setenv("PEXELS_API_KEY", "k")

    class _R:
        def __init__(self, payload): self._b = _json.dumps(payload).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._b
    payload = {"photos": [{"photographer": "Ann Lee",
                           "src": {"large2x": "https://img/x.jpg", "original": "https://img/o.jpg"}}]}
    monkeypatch.setattr(footage.urllib.request, "urlopen", lambda req, timeout=30: _R(payload))
    monkeypatch.setattr(footage, "_download", lambda link, out: True)

    out = tmp_path / "subject.png"
    credit = footage.fetch_photo("fifa world cup trophy", str(out))
    assert credit and "Ann Lee" in credit and "Pexels" in credit


def test_fetch_photo_none_without_key(monkeypatch, tmp_path):
    from engine.video import footage
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert footage.fetch_photo("anything", str(tmp_path / "s.png")) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_footage.py::test_fetch_photo_returns_credit -v`
Expected: FAIL — `AttributeError: ... no attribute 'fetch_photo'`.

- [ ] **Step 3: Implement**

In `engine/video/footage.py`, add near the other Pexels constants (after `_SEARCH = ...`):

```python
_PHOTO_SEARCH = "https://api.pexels.com/v1/search"
```

and add the function (after `fetch_clip`):

```python
def fetch_photo(query: str, out_path: str, api_key: str | None = None,
                min_width: int = 1080) -> str | None:
    """Download one high-res Pexels PHOTO for `query` to out_path. Returns a photographer
    credit on success, else None (missing key / no result / download fail). Never raises."""
    api_key = api_key or os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return None
    params = urllib.parse.urlencode({"query": query, "per_page": 15,
                                     "orientation": "portrait", "size": "large"})
    req = urllib.request.Request(
        f"{_PHOTO_SEARCH}?{params}",
        headers={"Authorization": api_key, "User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            photos = json.load(r).get("photos") or []
    except Exception:
        return None
    for p in photos:
        src = p.get("src") or {}
        link = src.get("large2x") or src.get("original")
        if link and _download(link, out_path):
            return f"Photo by {p.get('photographer', 'Pexels')} on Pexels"
    return None
```

(Note: the test stubs `urlopen` to return JSON via `json.load(r)` — `_R.read()` returns the bytes `json.load` consumes.)

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_footage.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/video/footage.py tests/test_footage.py
git commit -m "feat(subject): footage.fetch_photo — Pexels stock photo fallback"
```

---

## Task 3: `engine/pipeline/subject.py`

**Files:** Create `engine/pipeline/subject.py`. Test: `tests/test_subject.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_subject.py`:

```python
import os
from PIL import Image
from engine.pipeline import subject as S
from engine import paths


def _mk(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    d = paths.artifact_dir("idA", "short")
    os.makedirs(d, exist_ok=True)
    return d


def test_human_photo_wins(tmp_path, monkeypatch):
    d = _mk(tmp_path, monkeypatch)
    Image.new("RGB", (100, 100), (1, 2, 3)).save(os.path.join(d, "subject.png"))
    called = {"q": False}
    monkeypatch.setattr(S, "_subject_query", lambda *a: (called.__setitem__("q", True), ("", ""))[1])
    res = S.source_subject({"id": "idA"}, "short")
    assert res["source"] == "human"
    assert called["q"] is False  # never even queried


def test_person_uses_wikipedia(tmp_path, monkeypatch):
    _mk(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "_subject_query", lambda idea, script: ("Felipe Massa", "formula 1 car"))
    monkeypatch.setattr(S.wikipedia, "lead_image", lambda q: ("http://x/m.jpg", "Jane / CC BY via Wikimedia Commons"))
    monkeypatch.setattr(S, "_download", lambda url, out: (open(out, "wb").write(b"x"), True)[1])
    res = S.source_subject({"id": "idA"}, "short")
    assert res["source"] == "wikipedia"
    assert "Jane" in res["credit"]
    assert os.path.exists(os.path.join(paths.artifact_dir("idA", "short"), "subject_credit.txt"))


def test_no_person_falls_back_to_pexels(tmp_path, monkeypatch):
    _mk(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "_subject_query", lambda idea, script: ("", "fifa world cup trophy"))
    monkeypatch.setattr(S.wikipedia, "lead_image", lambda q: None)
    monkeypatch.setattr(S.footage, "fetch_photo", lambda q, out, **k: (open(out, "wb").write(b"x"), "Photo by Ann on Pexels")[1])
    res = S.source_subject({"id": "idA"}, "short")
    assert res["source"] == "pexels" and "Ann" in res["credit"]


def test_nothing_found_returns_none(tmp_path, monkeypatch):
    _mk(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "_subject_query", lambda idea, script: ("", ""))
    res = S.source_subject({"id": "idA"}, "short")
    assert res["source"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_subject.py -q`
Expected: FAIL — `ModuleNotFoundError: engine.pipeline.subject`.

- [ ] **Step 3: Implement**

Create `engine/pipeline/subject.py`:

```python
"""Auto-source a subject photo for a thumbnail: the person's Wikipedia lead image, else a
generic Pexels stock photo for a fallback concept. A human-supplied subject.png always wins.
Self-stubs on any failure — never crashes a run."""
from __future__ import annotations
import json
import os
import shutil
import urllib.request

import anthropic
from engine.config import MODEL
from engine import paths
from engine.ideate import wikipedia
from engine.video import footage

_SUBJECT_SYSTEM = """Identify the single best on-screen SUBJECT for a sports-history video
thumbnail. Return JSON {"person": <the one real person to show, exact full name for a Wikipedia
search, or "" if the story has no single person>, "concept": <a short generic stock-photo query
for the topic when there is no person, e.g. "fifa world cup trophy", "formula 1 car", "cricket
stadium">}. Use only what the script supports; never invent a person."""

_SUBJECT_SCHEMA = {"type": "object",
                   "properties": {"person": {"type": "string"}, "concept": {"type": "string"}},
                   "required": ["person", "concept"], "additionalProperties": False}


def _subject_query(idea: dict, script: str) -> tuple[str, str]:
    """(person, concept) via one structured LLM call; ('', '') on any failure."""
    try:
        client = anthropic.Anthropic(max_retries=5)
        title = (idea.get("title_variants") or [idea.get("title", "")])[0]
        resp = client.messages.create(
            model=MODEL, max_tokens=64, system=_SUBJECT_SYSTEM,
            messages=[{"role": "user",
                       "content": f"TITLE: {title}\n\nSCRIPT:\n{script[:4000]}\n\nIdentify the subject."}],
            output_config={"format": {"type": "json_schema", "schema": _SUBJECT_SCHEMA}})
        data = json.loads(next(b.text for b in resp.content if b.type == "text"))
        return (data.get("person", "") or "").strip(), (data.get("concept", "") or "").strip()
    except Exception:
        return "", ""


def _read_script(idea_id: str, fmt: str) -> str:
    for f in (fmt, "long", "short"):
        p = paths.script_path(idea_id, f)
        if os.path.exists(p):
            try:
                return open(p).read()
            except OSError:
                return ""
    return ""


def _download(url: str, out_path: str) -> bool:
    """Download url → out_path. Never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TheUntoldGame/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(out_path, "wb") as f:
            shutil.copyfileobj(r, f)
        return True
    except Exception:
        return False


def _write_credit(idea_id: str, fmt: str, credit: str) -> None:
    try:
        with open(os.path.join(paths.artifact_dir(idea_id, fmt), "subject_credit.txt"), "w") as f:
            f.write(credit + "\n")
    except OSError:
        pass


def source_subject(idea: dict, fmt: str) -> dict:
    """Populate produced/<id>/<fmt>/subject.png. Order: existing human photo (untouched) →
    Wikipedia lead image of the person → Pexels stock for the fallback concept → none.
    Returns {'source', 'path', 'credit'}."""
    idea_id = idea["id"]
    target = paths.subject_path(idea_id, fmt)
    if os.path.exists(target):
        return {"source": "human", "path": target, "credit": ""}
    out = os.path.join(paths.artifact_dir(idea_id, fmt), "subject.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    script = idea.get("script") or _read_script(idea_id, fmt)
    person, concept = _subject_query(idea, script)

    if person:
        hit = wikipedia.lead_image(person)
        if hit and _download(hit[0], out):
            _write_credit(idea_id, fmt, hit[1])
            return {"source": "wikipedia", "path": out, "credit": hit[1]}
    if concept:
        credit = footage.fetch_photo(concept, out)
        if credit:
            _write_credit(idea_id, fmt, credit)
            return {"source": "pexels", "path": out, "credit": credit}
    return {"source": None, "path": out, "credit": ""}
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_subject.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/subject.py tests/test_subject.py
git commit -m "feat(subject): source_subject orchestrator (wikipedia -> pexels, human wins)"
```

---

## Task 4: `engine/run_subject.py` CLI

**Files:** Create `engine/run_subject.py`. Test: `tests/test_subject.py` (append).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_subject.py`:

```python
def test_run_subject_main_reports(tmp_path, monkeypatch, capsys):
    import sys
    from engine import queue_manager, run_subject
    from engine.pipeline import subject as S2
    monkeypatch.setattr(queue_manager, "get_by_id", lambda i: {"id": i})
    monkeypatch.setattr(S2, "source_subject",
                        lambda idea, fmt: {"source": "wikipedia", "path": "p", "credit": "Jane / CC"})
    monkeypatch.setattr(sys, "argv", ["run_subject", "--id", "idA", "--format", "short"])
    run_subject.main()
    out = capsys.readouterr().out.lower()
    assert "wikipedia" in out and "jane" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_subject.py::test_run_subject_main_reports -v`
Expected: FAIL — `ModuleNotFoundError: engine.run_subject`.

- [ ] **Step 3: Implement**

Create `engine/run_subject.py`:

```python
"""The Untold Game — auto-source a subject photo (Wikipedia lead image → Pexels fallback)
for a video's thumbnail. A human-supplied subject.png always wins.

Usage:
  python3 -m engine.run_subject --id 648d57e6 --format short
"""
from __future__ import annotations
import argparse

from engine import queue_manager as q
from engine.pipeline import subject


def main() -> None:
    ap = argparse.ArgumentParser(description="The Untold Game — source a subject photo")
    ap.add_argument("--id", required=True, help="idea id")
    ap.add_argument("--format", choices=["long", "short"], default="long")
    args = ap.parse_args()

    idea = q.get_by_id(args.id) or {"id": args.id}
    res = subject.source_subject(idea, args.format)
    src = res["source"]
    if src == "human":
        print(f"· [{args.id}/{args.format}] already has a subject photo — left untouched")
    elif src:
        print(f"✓ [{args.id}/{args.format}] subject.png via {src} — {res['credit']}")
    else:
        print(f"✗ [{args.id}/{args.format}] no photo found — drop one at {res['path']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/run_subject.py tests/test_subject.py
git commit -m "feat(subject): run_subject CLI entrypoint"
```

---

## Task 5: Docs sync (required by the docs-staleness gate)

**Files:** Modify `CLAUDE.md`, `README.md`.

- [ ] **Step 1: CLAUDE.md** — in the `## Entrypoints` fenced block, add after the `run_thumbnail` line:

```
python3 -m engine.run_subject --id <id> [--format short]   # auto-source subject.png (Wikipedia lead image → Pexels fallback; human photo wins)
```

- [ ] **Step 2: CLAUDE.md** — in the layout table `engine/pipeline/` row or the thumbnail conventions, add a note: "thumbnail subjects can be auto-sourced via `run_subject` (Wikipedia Commons → Pexels), or dropped by hand at `produced/<id>/<fmt>/subject.png`."

- [ ] **Step 3: README.md** — add the same `run_subject` entrypoint line wherever `run_thumbnail` is listed (search README for `run_thumbnail`; mirror its formatting).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: run_subject entrypoint (auto-source subject photos)"
```

---

## Task 6: Proof + ship

- [ ] **Step 1:** `python3 -m pytest tests/ -q` — all green.
- [ ] **Step 2:** `python3 -m engine.run_subject --id 648d57e6 --format short` — confirm it fetches Felipe Massa's Wikipedia portrait → `produced/648d57e6/short/subject.png` + `subject_credit.txt`. Open the image to eyeball.
- [ ] **Step 3 (controller):** run it across the 8 published shorts, review the fetched photos, then `run_thumbnail --format short` for each → covers.
- [ ] **Ship:** dual adversarial review (Codex + Claude) → PR with `Adversarial-Reviewed:` trailer. The docs-staleness gate must pass (Task 5 satisfies it); pr-review-gate needs the trailer (engine/*.py changed).

## Self-Review (done at write time)

- **Spec coverage:** lead_image+credit → T1; fetch_photo → T2; orchestrator+extraction+human-wins+attribution → T3; CLI → T4; docs sync → T5; proof → T6. All mapped.
- **Name consistency:** `wikipedia.lead_image(query)->(url,credit)|None`, `footage.fetch_photo(query,out)->credit|None`, `subject.source_subject(idea,fmt)->{source,path,credit}`, `subject._subject_query`, `_download`, `_write_credit`, `run_subject.main`. Consumers match producers across tasks.
- **No placeholders:** every step has real code + command + expected result.
- **Mocking:** all network/LLM mocked (`requests.get`, `urllib.request.urlopen`, `_download`, `_subject_query`, `wikipedia.lead_image`, `footage.fetch_photo`) — no live calls in tests.
- **Integrity:** real licensed photos only (Wikipedia/Pexels), attribution captured, human override never overwritten.
