# Thumbnail Generation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Pillow compositor that turns a human-supplied subject photo + a withholding tension line into a 1280×720 "Prestige Feed Killer" thumbnail, and wire it into publish.

**Architecture:** Pure-`python3` Pillow pipeline (no Remotion, no ML). A constant *asset layer* (archival grade, film grain, vignette, serif UNTOLD stamp) plus a variable *tension layer* (auto-fit withholding text + a red marker anchored to the text's bounding box). Subject photo is human-supplied; the tension line is auto-generated under the shipped withholding rule (digit-backstopped) with a human override. Self-stubs when the subject photo is missing. The uploader already supports `thumbnail_path`, so publish wiring is a present-only-if-exists kwarg.

**Tech Stack:** Python 3 (main env), Pillow, Anthropic structured outputs, bundled OFL fonts (Anton, Playfair Display).

Spec: `docs/superpowers/specs/2026-06-13-thumbnail-engine-design.md`

---

## File Structure

- `requirements.txt` (or equivalent) — add `Pillow`.
- `engine/pipeline/assets/fonts/` — bundled `Anton-Regular.ttf`, `PlayfairDisplay.ttf`, `OFL-Anton.txt`, `OFL-PlayfairDisplay.txt`.
- `engine/paths.py` — add `subject_path`, `thumbnail_path`.
- `engine/pipeline/thumbnail.py` — replaces the stub: constants, `_wrap`, `_layout_tension`, `_draw_stamp`, `_draw_tension`, `compose`, `_thumbnail_text_llm`, `_thumbnail_text`, `generate_thumbnail`, `run`.
- `engine/run_thumbnail.py` — CLI entrypoint.
- `engine/run_auto.py` — `cmd_approve`: pass `thumbnail_path` when the file exists.
- `tests/test_thumbnail.py`, `tests/test_paths.py` (append), `tests/test_run_auto_thumbnail.py`.

---

## Task 1: Pillow dependency + bundled fonts

**Files:**
- Modify: `requirements.txt`
- Create: `engine/pipeline/assets/fonts/Anton-Regular.ttf`, `.../PlayfairDisplay.ttf`, `.../OFL-Anton.txt`, `.../OFL-PlayfairDisplay.txt`
- Test: `tests/test_thumbnail.py`

- [ ] **Step 1: Install Pillow + record the dependency**

```bash
python3 -m pip install Pillow
grep -qi '^Pillow' requirements.txt || echo "Pillow>=10.0" >> requirements.txt
python3 -c "import PIL; print('PIL', PIL.__version__)"
```
Expected: prints a PIL version (no ImportError).

- [ ] **Step 2: Download + commit the OFL fonts and their licenses**

```bash
mkdir -p engine/pipeline/assets/fonts
cd engine/pipeline/assets/fonts
curl -fsSL -o Anton-Regular.ttf        "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf"
curl -fsSL -o OFL-Anton.txt            "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/OFL.txt"
curl -fsSL -o "PlayfairDisplay.ttf"    "https://raw.githubusercontent.com/google/fonts/main/ofl/playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf"
curl -fsSL -o OFL-PlayfairDisplay.txt  "https://raw.githubusercontent.com/google/fonts/main/ofl/playfairdisplay/OFL.txt"
cd -
ls -la engine/pipeline/assets/fonts/
```
Expected: four files, the two `.ttf` non-empty (> 20 KB each). If a download fails (network blocked), STOP and report BLOCKED — do not fabricate font files.

- [ ] **Step 3: Write the failing test (fonts load)**

Add to a new `tests/test_thumbnail.py`:
```python
import os
from PIL import ImageFont
from engine.pipeline import thumbnail


def test_bundled_fonts_load():
    for path in (thumbnail.TENSION_FONT, thumbnail.STAMP_FONT):
        assert os.path.exists(path), f"missing bundled font: {path}"
        ImageFont.truetype(path, 40)  # raises if the file isn't a valid font
```

- [ ] **Step 4: Run it, verify it FAILS**

Run: `python3 -m pytest tests/test_thumbnail.py::test_bundled_fonts_load -v`
Expected: FAIL — `thumbnail` has no attribute `TENSION_FONT` (constants added in Task 3).

- [ ] **Step 5: Add the font-path constants to `engine/pipeline/thumbnail.py`**

Replace the entire stub file contents with just the module header + constants for now (the rest is added in later tasks):
```python
"""Stage 2 — THUMBNAIL: deterministic Pillow compositor for the channel's
"Prestige Feed Killer" thumbnail template (asset layer + tension layer)."""
from __future__ import annotations
import os

_FONTS = os.path.join(os.path.dirname(__file__), "assets", "fonts")
TENSION_FONT = os.path.join(_FONTS, "Anton-Regular.ttf")
STAMP_FONT = os.path.join(_FONTS, "PlayfairDisplay.ttf")
```

- [ ] **Step 6: Run it, verify it PASSES**

Run: `python3 -m pytest tests/test_thumbnail.py::test_bundled_fonts_load -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git branch --show-current   # MUST be feat/thumbnail-engine; if not, STOP
git add requirements.txt engine/pipeline/assets/fonts engine/pipeline/thumbnail.py tests/test_thumbnail.py
git commit -m "feat(thumbnail): add Pillow dep + bundled OFL fonts (Anton, Playfair)"
```

---

## Task 2: Path helpers for subject + thumbnail

**Files:**
- Modify: `engine/paths.py` (after `video_dir`)
- Test: `tests/test_paths.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_paths.py` (or append if it exists):
```python
import os
from engine import paths


def test_thumbnail_path_under_artifact_dir():
    p = paths.thumbnail_path("abc123", "short")
    assert p == os.path.join(paths.artifact_dir("abc123", "short"), "thumbnail.jpg")


def test_subject_path_prefers_png_then_jpg(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    d = paths.artifact_dir("id1", "long")
    os.makedirs(d, exist_ok=True)
    # nothing present yet -> default .png path
    assert paths.subject_path("id1", "long").endswith("subject.png")
    # a .jpg present and no .png -> returns the .jpg
    open(os.path.join(d, "subject.jpg"), "w").close()
    assert paths.subject_path("id1", "long").endswith("subject.jpg")
    # a .png present -> .png wins
    open(os.path.join(d, "subject.png"), "w").close()
    assert paths.subject_path("id1", "long").endswith("subject.png")
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python3 -m pytest tests/test_paths.py -v`
Expected: FAIL — `paths` has no attribute `thumbnail_path`.

- [ ] **Step 3: Implement the helpers in `engine/paths.py`** (append after `video_dir`):
```python
def thumbnail_path(idea_id: str, fmt: str) -> str:
    return os.path.join(artifact_dir(idea_id, fmt), "thumbnail.jpg")


def subject_path(idea_id: str, fmt: str) -> str:
    """The human-supplied subject photo. Prefers subject.png, then subject.jpg;
    returns the .png path (which may not exist yet) when neither is present."""
    d = artifact_dir(idea_id, fmt)
    png = os.path.join(d, "subject.png")
    jpg = os.path.join(d, "subject.jpg")
    if os.path.exists(png):
        return png
    if os.path.exists(jpg):
        return jpg
    return png
```

- [ ] **Step 4: Run, verify PASS**

Run: `python3 -m pytest tests/test_paths.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # MUST be feat/thumbnail-engine
git add engine/paths.py tests/test_paths.py
git commit -m "feat(thumbnail): paths.subject_path + paths.thumbnail_path"
```

---

## Task 3: Tension-text layout (auto-fit, wrap, marker anchored to text bbox)

**Files:**
- Modify: `engine/pipeline/thumbnail.py`
- Test: `tests/test_thumbnail.py`

This is the locked layout rule: the red marker's top sits a fixed gap below the rendered text block's bbox bottom — for 1 line or 3 lines — so the text+marker stay one unit and never drift into the subject.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_thumbnail.py`:
```python
from PIL import Image, ImageDraw
from engine.pipeline import thumbnail as tn


def _draw():
    return ImageDraw.Draw(Image.new("RGB", (tn.W, tn.H)))


def test_marker_anchored_to_text_block_one_and_three_lines():
    d = _draw()
    f1, lines1, box1, marker1, _, _ = tn._layout_tension("GONE", d)
    f3, lines3, box3, marker3, _, _ = tn._layout_tension("THE NIGHT HE NEVER MADE IT HOME", d)
    assert len(lines1) == 1 and len(lines3) >= 2
    # marker top is exactly MARKER_GAP below the text block's bottom in BOTH cases
    assert marker1[1] - box1[3] == tn.MARKER_GAP
    assert marker3[1] - box3[3] == tn.MARKER_GAP
    # three-line block sits lower-bottom than one-line, and its marker follows it down
    assert marker3[1] > marker1[1]


def test_layout_wraps_to_at_most_three_lines_and_fits_width():
    d = _draw()
    _, lines, box, _, _, _ = tn._layout_tension("THE NIGHT HE NEVER MADE IT HOME", d)
    assert len(lines) <= 3
    assert (box[2] - box[0]) <= tn.MAX_TEXT_W
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python3 -m pytest tests/test_thumbnail.py -k layout -v`
Expected: FAIL — `_layout_tension` not defined / no `W`.

- [ ] **Step 3: Add canvas constants + layout code to `engine/pipeline/thumbnail.py`**

Add the imports and constants near the top (after the existing font constants), then the two functions:
```python
from PIL import ImageFont

W, H = 1280, 720
RIGHT_MARGIN = 40
MAX_TEXT_W = int(W * 0.56)
MAX_TEXT_H = int(H * 0.62)
MAX_FONT, MIN_FONT = 150, 40
MARKER_GAP = 14          # px below the text block bbox — LOCKED: anchors to text, not frame
MARKER_H = 8
MARKER_MAX_W = 170
RED = (224, 48, 30)


def _wrap(text, font, draw, max_w):
    """Greedy word-wrap to fit max_w; a single over-wide word stays on its own line."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if not cur or draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _layout_tension(text, draw):
    """Pick the largest font (MAX_FONT..MIN_FONT) whose wrapped text fits the text
    box in <=3 lines. Return (font, lines, block_box, marker_rect, line_h, widths).
    block_box is right-aligned and vertically centred (nudged up to leave marker room);
    marker_rect top is exactly MARKER_GAP below block_box bottom (the locked rule)."""
    font = ImageFont.truetype(TENSION_FONT, MIN_FONT)
    lines = _wrap(text, font, draw, MAX_TEXT_W)
    for size in range(MAX_FONT, MIN_FONT - 1, -2):
        font = ImageFont.truetype(TENSION_FONT, size)
        lines = _wrap(text, font, draw, MAX_TEXT_W)
        if len(lines) > 3:
            continue
        ascent, descent = font.getmetrics()
        line_h = ascent + descent
        widths = [draw.textlength(ln, font=font) for ln in lines]
        if max(widths) <= MAX_TEXT_W and line_h * len(lines) <= MAX_TEXT_H:
            break
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    widths = [draw.textlength(ln, font=font) for ln in lines]
    block_w, block_h = max(widths), line_h * len(lines)
    right = W - RIGHT_MARGIN
    top = (H - block_h) // 2 - 28
    block_box = (right - block_w, top, right, top + block_h)
    marker_top = top + block_h + MARKER_GAP
    marker_w = min(int(block_w), MARKER_MAX_W)
    marker_rect = (right - marker_w, marker_top, right, marker_top + MARKER_H)
    return font, lines, block_box, marker_rect, line_h, widths
```

- [ ] **Step 4: Run, verify PASS**

Run: `python3 -m pytest tests/test_thumbnail.py -k layout -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # MUST be feat/thumbnail-engine
git add engine/pipeline/thumbnail.py tests/test_thumbnail.py
git commit -m "feat(thumbnail): auto-fit tension-text layout with text-anchored red marker"
```

---

## Task 4: `compose()` — full asset + tension render to 1280×720 JPEG

**Files:**
- Modify: `engine/pipeline/thumbnail.py`
- Test: `tests/test_thumbnail.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_thumbnail.py`:
```python
def test_compose_writes_1280x720_jpeg(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (900, 1200), (120, 90, 70)).save(subj)   # synthetic portrait
    out = tmp_path / "thumbnail.jpg"
    tn.compose(str(subj), "10 DAYS LATER", str(out))
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (1280, 720)
        assert im.format == "JPEG"
    assert out.stat().st_size < 2_000_000   # YouTube's 2 MB limit


def test_compose_handles_empty_tension_text(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1280, 720), (90, 90, 90)).save(subj)
    out = tmp_path / "thumb2.jpg"
    tn.compose(str(subj), "", str(out))   # asset layer only, no crash
    with Image.open(out) as im:
        assert im.size == (1280, 720)
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python3 -m pytest tests/test_thumbnail.py -k compose -v`
Expected: FAIL — `compose` not defined.

- [ ] **Step 3: Implement `_draw_stamp`, `_draw_tension`, `compose`**

Extend the PIL import line in `engine/pipeline/thumbnail.py` to:
```python
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageOps
```
Then add:
```python
def _draw_stamp(draw):
    """Serif UNTOLD stamp in a bordered box, top-right — the constant brand mark."""
    font = ImageFont.truetype(STAMP_FONT, 26)
    text, pad, cream = "UNTOLD", 10, (216, 201, 166)
    tb = draw.textbbox((0, 0), text, font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    x2, y0 = W - 28, 22
    x1, y2 = x2 - tw - 2 * pad, y0 + th + 2 * pad
    draw.rectangle([x1, y0, x2, y2], outline=cream, width=2)
    draw.text((x1 + pad - tb[0], y0 + pad - tb[1]), text, font=font, fill=cream)


def _draw_tension(draw, text):
    """Right-aligned condensed withholding text + the text-anchored red marker."""
    font, lines, box, marker, line_h, widths = _layout_tension(text, draw)
    right, top = box[2], box[1]
    for i, ln in enumerate(lines):
        x, y = right - widths[i], top + i * line_h
        draw.text((x + 3, y + 3), ln, font=font, fill=(0, 0, 0))      # shadow
        draw.text((x, y), ln, font=font, fill=(255, 255, 255))
    draw.rectangle(list(marker), fill=RED)


def compose(subject_path: str, tension_text: str, out_path: str) -> None:
    """Render the 1280x720 'Prestige Feed Killer' thumbnail to out_path (JPEG)."""
    base = ImageOps.fit(Image.open(subject_path).convert("RGB"), (W, H), Image.LANCZOS)
    # archival grade: desaturate + warm sepia duotone, then trim brightness / lift contrast
    desat = ImageEnhance.Color(base).enhance(0.35)
    sepia = ImageOps.colorize(ImageOps.grayscale(base), black=(26, 18, 10), white=(236, 222, 196))
    graded = Image.blend(desat, sepia, 0.5)
    graded = ImageEnhance.Contrast(ImageEnhance.Brightness(graded).enhance(0.92)).enhance(1.08)
    # warm side-light from the lower-left (subject side)
    blob = ImageOps.invert(Image.radial_gradient("L")).resize((int(W * 1.4), int(H * 1.4)))
    light = Image.new("L", (W, H), 0)
    light.paste(blob, (int(0.28 * W) - blob.width // 2, int(0.62 * H) - blob.height // 2))
    warm = Image.new("RGB", (W, H), (232, 180, 110))
    graded = Image.composite(ImageChops.screen(graded, warm), graded, light.point(lambda v: int(v * 0.30)))
    # film grain
    noise = Image.effect_noise((W, H), 30).convert("RGB")
    graded = Image.blend(graded, noise, 0.07)
    # vignette (bright centre -> dark edges, floored so edges darken to ~0.31)
    vig = ImageOps.invert(Image.radial_gradient("L")).resize((W, H)).point(lambda v: int(80 + v * 0.69))
    graded = ImageChops.multiply(graded, Image.merge("RGB", (vig, vig, vig)))
    # layers on top
    draw = ImageDraw.Draw(graded)
    _draw_stamp(draw)
    if tension_text:
        _draw_tension(draw, tension_text)
    graded.save(out_path, "JPEG", quality=88)
```

- [ ] **Step 4: Run, verify PASS**

Run: `python3 -m pytest tests/test_thumbnail.py -k compose -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # MUST be feat/thumbnail-engine
git add engine/pipeline/thumbnail.py tests/test_thumbnail.py
git commit -m "feat(thumbnail): compose() — archival asset layer + tension layer -> 1280x720 JPEG"
```

---

## Task 5: Tension-line generator (auto-generate, human override, digit-backstopped)

**Files:**
- Modify: `engine/pipeline/thumbnail.py`
- Test: `tests/test_thumbnail.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_thumbnail.py`:
```python
def test_thumbnail_text_uses_human_override(monkeypatch):
    # override present -> used verbatim, no LLM call
    monkeypatch.setattr(tn, "_thumbnail_text_llm", lambda i, s: (_ for _ in ()).throw(AssertionError("LLM should not be called")))
    assert tn._thumbnail_text({"thumbnail_text": "10 DAYS LATER"}, "script") == "10 DAYS LATER"


def test_thumbnail_text_uses_llm_when_clean(monkeypatch):
    monkeypatch.setattr(tn, "_thumbnail_text_llm", lambda i, s: "THEN HE VANISHED")
    assert tn._thumbnail_text({}, "He retired one season short of the record.") == "THEN HE VANISHED"


def test_thumbnail_text_rejects_fabricated_number(monkeypatch):
    # '1500' is not in the script -> digit backstop rejects -> empty (no override)
    monkeypatch.setattr(tn, "_thumbnail_text_llm", lambda i, s: "1500 YARDS SHORT")
    assert tn._thumbnail_text({}, "He retired 1457 yards short.") == ""


def test_thumbnail_text_falls_back_to_empty_on_llm_error(monkeypatch):
    def boom(i, s):
        raise RuntimeError("down")
    monkeypatch.setattr(tn, "_thumbnail_text_llm", boom)
    assert tn._thumbnail_text({}, "script") == ""
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python3 -m pytest tests/test_thumbnail.py -k thumbnail_text -v`
Expected: FAIL — `_thumbnail_text` / `_thumbnail_text_llm` not defined.

- [ ] **Step 3: Implement the generator in `engine/pipeline/thumbnail.py`**

Add these imports near the top:
```python
import json
import anthropic
from engine.config import MODEL
from engine.pipeline.script import title_numbers_within
```
Then add:
```python
_THUMB_TEXT_SYSTEM = """You write the on-thumbnail TENSION LINE for a YouTube sports-history
SHORT/video. 2-4 words, UPPERCASE, ultra-condensed punch. Open the gap by withholding the
resolution — never editorialize, never state the payoff. Use ONLY facts in the script; introduce
no name, number, or date that isn't there. Any specific must be the EXACT value from the script:
never round, never invent a superlative. Output only the line — no quotes, punctuation, or labels."""

_THUMB_TEXT_SCHEMA = {
    "type": "object",
    "properties": {"line": {"type": "string"}},
    "required": ["line"],
    "additionalProperties": False,
}


def _thumbnail_text_llm(idea: dict, script: str) -> str:
    """One structured call -> a 2-4 word withholding tension line. Raises on failure."""
    client = anthropic.Anthropic(max_retries=5)
    resp = client.messages.create(
        model=MODEL, max_tokens=32, system=_THUMB_TEXT_SYSTEM,
        messages=[{"role": "user", "content": f"SCRIPT:\n{script}\n\nWrite the tension line."}],
        output_config={"format": {"type": "json_schema", "schema": _THUMB_TEXT_SCHEMA}},
    )
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return data["line"].strip().upper()


def _thumbnail_text(idea: dict, script: str) -> str:
    """Resolve the tension line: human override wins; else the LLM line guarded by the digit
    backstop; on failure / empty / backstop-reject, fall back to the override or "" (asset-only)."""
    override = (idea.get("thumbnail_text") or "").strip()
    if override:
        return override
    try:
        line = _thumbnail_text_llm(idea, script)
    except Exception:
        return ""
    if not line:
        return ""
    ok, _ = title_numbers_within(line, script)
    return line if ok else ""
```

- [ ] **Step 4: Run, verify PASS**

Run: `python3 -m pytest tests/test_thumbnail.py -k thumbnail_text -v`
Expected: PASS (all four).

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # MUST be feat/thumbnail-engine
git add engine/pipeline/thumbnail.py tests/test_thumbnail.py
git commit -m "feat(thumbnail): withholding tension-line generator (override + digit backstop)"
```

---

## Task 6: `generate_thumbnail` orchestration + self-stub

**Files:**
- Modify: `engine/pipeline/thumbnail.py`
- Test: `tests/test_thumbnail.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_thumbnail.py`:
```python
import os as _os


def test_generate_thumbnail_self_stubs_without_subject(tmp_path, monkeypatch):
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    _os.makedirs(paths.artifact_dir("id9", "short"), exist_ok=True)
    idea = {"id": "id9"}
    out = tn.generate_thumbnail(idea, "short")   # no subject photo present
    assert out is idea                            # returned unchanged
    assert not _os.path.exists(paths.thumbnail_path("id9", "short"))   # no file, no crash


def test_generate_thumbnail_composites_when_subject_present(tmp_path, monkeypatch):
    from engine import paths
    from PIL import Image
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    d = paths.artifact_dir("id8", "long")
    _os.makedirs(d, exist_ok=True)
    Image.new("RGB", (1000, 1000), (100, 80, 60)).save(_os.path.join(d, "subject.png"))
    monkeypatch.setattr(tn, "_thumbnail_text", lambda idea, script: "THEN HE VANISHED")
    idea = {"id": "id8", "script": "He retired one season short."}
    tn.generate_thumbnail(idea, "long")
    assert _os.path.exists(paths.thumbnail_path("id8", "long"))
    with Image.open(paths.thumbnail_path("id8", "long")) as im:
        assert im.size == (1280, 720)
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python3 -m pytest tests/test_thumbnail.py -k generate_thumbnail -v`
Expected: FAIL — `generate_thumbnail` not defined.

- [ ] **Step 3: Implement `generate_thumbnail` + `run` in `engine/pipeline/thumbnail.py`**

Add this import near the top:
```python
from engine import paths
```
Then add (replacing any leftover stub `run`):
```python
def generate_thumbnail(idea: dict, fmt: str) -> dict:
    """Composite the thumbnail for an idea+format from its human-supplied subject photo.
    Self-stubs (logs, returns the idea unchanged, writes nothing) when no subject photo is
    present — an idea must never crash the run over a missing optional asset."""
    idea_id = idea["id"]
    subject = paths.subject_path(idea_id, fmt)
    if not os.path.exists(subject):
        print(f"  · thumbnail skipped for [{idea_id}/{fmt}] — no subject photo at {subject}")
        return idea
    text = _thumbnail_text(idea, idea.get("script", ""))
    out = paths.thumbnail_path(idea_id, fmt)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    compose(subject, text, out)
    print(f"  ✓ thumbnail.jpg for [{idea_id}/{fmt}]" + (f' — "{text}"' if text else " (no tension text)"))
    return idea


def run(idea: dict, fmt: str = "long") -> dict:
    """Pipeline stage: generate the thumbnail (self-stubbing on a missing subject photo)."""
    return generate_thumbnail(idea, fmt)
```

- [ ] **Step 4: Run, verify PASS**

Run: `python3 -m pytest tests/test_thumbnail.py -k generate_thumbnail -v`
Expected: PASS.

- [ ] **Step 5: Run the whole thumbnail test file**

Run: `python3 -m pytest tests/test_thumbnail.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # MUST be feat/thumbnail-engine
git add engine/pipeline/thumbnail.py tests/test_thumbnail.py
git commit -m "feat(thumbnail): generate_thumbnail orchestration with self-stub on missing subject"
```

---

## Task 7: `run_thumbnail` CLI

**Files:**
- Create: `engine/run_thumbnail.py`
- Test: `tests/test_thumbnail.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_thumbnail.py`:
```python
def test_run_thumbnail_main_errors_without_subject(tmp_path, monkeypatch, capsys):
    import sys
    from engine import paths, queue_manager
    from engine import run_thumbnail
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    _os.makedirs(paths.artifact_dir("idz", "short"), exist_ok=True)
    monkeypatch.setattr(queue_manager, "get_by_id", lambda _id: {"id": "idz", "script": "s"})
    monkeypatch.setattr(sys, "argv", ["run_thumbnail", "--id", "idz", "--format", "short"])
    import pytest
    with pytest.raises(SystemExit) as e:
        run_thumbnail.main()
    assert e.value.code != 0
    assert "no subject photo" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python3 -m pytest tests/test_thumbnail.py -k run_thumbnail -v`
Expected: FAIL — no module `engine.run_thumbnail`.

- [ ] **Step 3: Create `engine/run_thumbnail.py`**
```python
"""The Untold Game — THUMBNAIL stage entrypoint.

Composite the 'Prestige Feed Killer' thumbnail for a produced idea from its
human-supplied subject photo (produced/<id>/<fmt>/subject.png|jpg).

Usage:
  python3 -m engine.run_thumbnail --id 2922268d
  python3 -m engine.run_thumbnail --id 2922268d --format short
"""
from __future__ import annotations
import argparse
import os
import sys

from engine import paths, queue_manager as q
from engine.pipeline import thumbnail


def main() -> None:
    ap = argparse.ArgumentParser(description="The Untold Game — generate a video thumbnail")
    ap.add_argument("--id", required=True, help="idea id")
    ap.add_argument("--format", choices=["long", "short"], default="long")
    args = ap.parse_args()

    idea = q.get_by_id(args.id) or {"id": args.id}
    subject = paths.subject_path(args.id, args.format)
    if not os.path.exists(subject):
        sys.exit(f"No subject photo for [{args.id}/{args.format}]. Drop one at: {subject}")
    thumbnail.generate_thumbnail(idea, args.format)
    print(f"✓ thumbnail at {paths.thumbnail_path(args.id, args.format)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, verify PASS**

Run: `python3 -m pytest tests/test_thumbnail.py -k run_thumbnail -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git branch --show-current   # MUST be feat/thumbnail-engine
git add engine/run_thumbnail.py tests/test_thumbnail.py
git commit -m "feat(thumbnail): run_thumbnail CLI entrypoint"
```

---

## Task 8: Publish wiring — `cmd_approve` sets the thumbnail when present

**Files:**
- Modify: `engine/run_auto.py` (`cmd_approve`, ~lines 231-264)
- Test: `tests/test_run_auto_thumbnail.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_auto_thumbnail.py`:
```python
import os
from engine import run_auto, paths


def _idea(tmp):
    d = paths.artifact_dir("pubid", "long")
    os.makedirs(os.path.join(d, "video"), exist_ok=True)
    open(os.path.join(d, "video", "final.mp4"), "w").close()
    open(paths.metadata_path("pubid", "long"), "w").write('{"title":"T","description":"d","tags":[]}')
    return {"id": "pubid", "status": "awaiting_approval",
            "metadata_path": os.path.relpath(paths.metadata_path("pubid", "long"),
                                             os.path.dirname(paths.PRODUCED_DIR)),
            "video_path": os.path.relpath(os.path.join(d, "video", "final.mp4"),
                                          os.path.dirname(paths.PRODUCED_DIR))}


def test_cmd_approve_passes_thumbnail_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_auto, "_ROOT", str(tmp_path))
    idea = _idea(tmp_path)
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda _id: idea)
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    monkeypatch.setattr(run_auto, "_load_metadata", lambda p: {"title": "T", "description": "d", "tags": []})
    from PIL import Image
    Image.new("RGB", (1280, 720), (0, 0, 0)).save(paths.thumbnail_path("pubid", "long"))
    captured = {}
    def fake_upload(video_path, **kw):
        captured.update(kw)
        return "VID123"
    monkeypatch.setattr(run_auto.uploader, "upload", fake_upload)
    run_auto.cmd_approve("pubid", public=False, dry_run=False)
    assert captured.get("thumbnail_path") == paths.thumbnail_path("pubid", "long")


def test_cmd_approve_omits_thumbnail_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    monkeypatch.setattr(run_auto, "_ROOT", str(tmp_path))
    idea = _idea(tmp_path)
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda _id: idea)
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    monkeypatch.setattr(run_auto, "_load_metadata", lambda p: {"title": "T", "description": "d", "tags": []})
    captured = {}
    monkeypatch.setattr(run_auto.uploader, "upload", lambda video_path, **kw: captured.update(kw) or "VID123")
    run_auto.cmd_approve("pubid", public=False, dry_run=False)
    assert captured.get("thumbnail_path") is None
```

> Note: the exact `_idea` fixture wiring (relpath bases) may need a small adjustment to match how `cmd_approve` resolves `video_path`/`metadata_path` against `_ROOT`. Read `engine/run_auto.py:231-251` and align the fixture so the non-thumbnail parts of `cmd_approve` run; the assertion under test is only the `thumbnail_path` kwarg.

- [ ] **Step 2: Run, verify FAIL**

Run: `python3 -m pytest tests/test_run_auto_thumbnail.py -v`
Expected: FAIL — `thumbnail_path` not passed (kwarg missing).

- [ ] **Step 3: Wire the thumbnail into `cmd_approve` in `engine/run_auto.py`**

Add `from engine import paths` to the imports if not present. Determine the format the long is published under (`"long"`). Just before the `uploader.upload(...)` call for the long video, compute the thumbnail path:
```python
    thumb = paths.thumbnail_path(idea_id, "long")
    thumb = thumb if os.path.exists(thumb) else None
```
Then pass `thumbnail_path=thumb` to the long `uploader.upload(...)` call. For the companion short upload (inside the `short_status == "short_awaiting_approval"` block), compute `sthumb = paths.thumbnail_path(idea_id, "short")` (→ `None` if absent) and pass `thumbnail_path=sthumb` to that `uploader.upload(...)`.

- [ ] **Step 4: Run, verify PASS**

Run: `python3 -m pytest tests/test_run_auto_thumbnail.py -v`
Expected: PASS (both).

- [ ] **Step 5: Run the FULL suite (the contract)**

Run: `python3 -m pytest tests/ -q`
Expected: all pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git branch --show-current   # MUST be feat/thumbnail-engine
git add engine/run_auto.py tests/test_run_auto_thumbnail.py
git commit -m "feat(thumbnail): cmd_approve sets the custom thumbnail when present"
```

---

## Manual usage (after merge — not a coding task)

Per video: drop the curated subject photo at `produced/<id>/<fmt>/subject.png`, then:
```bash
python3 -m engine.run_thumbnail --id <id>                  # long
python3 -m engine.run_thumbnail --id <id> --format short   # short
```
Optionally set a human tension line by adding `"thumbnail_text": "10 DAYS LATER"` to the idea record (otherwise it's auto-generated under the withholding rule). The thumbnail is set automatically at `--approve`.
