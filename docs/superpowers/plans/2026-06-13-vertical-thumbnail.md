# Vertical 9:16 Thumbnail — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `run_thumbnail --format short` produces a bold 1080×1920 cover (subject photo + giant bottom-stacked text, last line in channel red) for shorts / TikTok / Reels.

**Architecture:** Add a `compose_vertical` alongside the existing 16:9 `compose`, sharing the cinematic grade via an extracted `_grade(base, w, h)` helper. `generate_thumbnail` routes `fmt=="short"` to it. Real human-supplied subject photos only (ADR-0005).

**Tech Stack:** Python 3, Pillow (PIL), Anton/Playfair bundled fonts. `python3 -m pytest tests/ -q`.

**Spec:** `docs/superpowers/specs/2026-06-13-vertical-thumbnail-design.md`
**Branch:** `feat/vertical-thumbnail` (already checked out).

**Conventions:** `python3` only, absolute `engine.*` imports, PostToolUse hook runs pytest (intermediate TDD-red is fine), render/LLM never a test gate (tests use synthetic `Image.new` images).

---

## Task 1: Extract `_grade(base, w, h)` + parametrize `_draw_stamp(draw, w=W)`

Pure refactor — existing `test_thumbnail.py` is the guard (compose output must be unchanged).

**Files:** Modify `engine/pipeline/thumbnail.py`. Test: existing `tests/test_thumbnail.py`.

- [ ] **Step 1: Extract `_grade`**

In `engine/pipeline/thumbnail.py`, add above `compose`:

```python
def _grade(base, w, h):
    """Archival cinematic grade (desaturate + sepia duotone + warm side-light + grain +
    vignette) for a w×h RGB image. Shared by the 16:9 and 9:16 compositors."""
    desat = ImageEnhance.Color(base).enhance(0.35)
    sepia = ImageOps.colorize(ImageOps.grayscale(base), black=(26, 18, 10), white=(236, 222, 196))
    graded = Image.blend(desat, sepia, 0.5)
    graded = ImageEnhance.Contrast(ImageEnhance.Brightness(graded).enhance(0.92)).enhance(1.08)
    blob = ImageOps.invert(Image.radial_gradient("L")).resize((int(w * 1.4), int(h * 1.4)))
    light = Image.new("L", (w, h), 0)
    light.paste(blob, (int(0.28 * w) - blob.width // 2, int(0.62 * h) - blob.height // 2))
    warm = Image.new("RGB", (w, h), (232, 180, 110))
    graded = Image.composite(ImageChops.screen(graded, warm), graded, light.point(lambda v: int(v * 0.30)))
    noise = Image.effect_noise((w, h), 30).convert("RGB")
    graded = Image.blend(graded, noise, 0.07)
    vig = ImageOps.invert(Image.radial_gradient("L")).resize((w, h)).point(lambda v: int(80 + v * 0.69))
    return ImageChops.multiply(graded, Image.merge("RGB", (vig, vig, vig)))
```

- [ ] **Step 2: Use it in `compose`**

Replace the grade block inside `compose` (the lines from `desat = ...` through the `vig`/`ImageChops.multiply` assignment) with:

```python
    base = ImageOps.fit(Image.open(subject_path).convert("RGB"), (W, H), Image.LANCZOS)
    graded = _grade(base, W, H)
    text = (tension_text or "").strip()
    draw = ImageDraw.Draw(graded)
    _draw_stamp(draw)
    if text:
        _draw_tension(draw, text)
    graded.save(out_path, "JPEG", quality=88)
```

- [ ] **Step 3: Parametrize `_draw_stamp`**

Change `def _draw_stamp(draw):` to `def _draw_stamp(draw, w=W):` and replace the two uses of `W` inside it (`x2 = W - 28`) with `w` (`x2 = w - 28`). Existing call `_draw_stamp(draw)` is unaffected (default `w=W`).

- [ ] **Step 4: Run tests (guard the refactor)**

Run: `python3 -m pytest tests/test_thumbnail.py -q`
Expected: PASS unchanged (`test_compose_writes_1280x720_jpeg`, `test_compose_handles_empty_tension_text`, etc.). If any fail, the refactor changed behaviour — fix before continuing.

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/thumbnail.py
git commit -m "refactor(thumbnail): extract _grade(base,w,h) + parametrize _draw_stamp(w)"
```

---

## Task 2: `compose_vertical` + `_layout_vertical`

**Files:** Modify `engine/pipeline/thumbnail.py`. Test: `tests/test_thumbnail.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_thumbnail.py`:

```python
def test_layout_vertical_wraps_and_fits():
    d = ImageDraw.Draw(Image.new("RGB", (tn.VW, tn.VH)))
    font, lines, line_h, widths = tn._layout_vertical("BANNED THEN A DYNASTY", d)
    assert 1 <= len(lines) <= 4
    assert max(widths) <= tn.MAX_TEXT_W_V
    assert tn.V_MIN_FONT <= font.size <= tn.V_MAX_FONT


def test_compose_vertical_writes_1080x1920_jpeg(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1500, 2200), (110, 80, 60)).save(subj)
    out = tmp_path / "cover.jpg"
    tn.compose_vertical(str(subj), "BANNED THEN A DYNASTY", str(out))
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (1080, 1920)
        assert im.format == "JPEG"
    assert out.stat().st_size < 2_000_000


def test_compose_vertical_handles_empty_text(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1080, 1920), (80, 80, 80)).save(subj)
    out = tmp_path / "cover2.jpg"
    tn.compose_vertical(str(subj), "", str(out))   # subject + stamp only, no crash
    with Image.open(out) as im:
        assert im.size == (1080, 1920)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_thumbnail.py::test_compose_vertical_writes_1080x1920_jpeg -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'compose_vertical'` (or `VW`).

- [ ] **Step 3: Add vertical constants**

In `engine/pipeline/thumbnail.py`, near the existing `W, H = 1280, 720` block, add:

```python
VW, VH = 1080, 1920
MAX_TEXT_W_V = int(VW * 0.88)
V_MAX_FONT, V_MIN_FONT = 170, 56
V_MAX_LINES = 4
V_BOTTOM_MARGIN = 150        # px from the frame bottom to the text block's baseline area
```

- [ ] **Step 4: Implement `_layout_vertical` and `compose_vertical`**

Add to `engine/pipeline/thumbnail.py` (after `_layout_tension` / `compose`):

```python
def _layout_vertical(text, draw):
    """Largest Anton font (V_MAX_FONT..V_MIN_FONT) whose wrapped text fits MAX_TEXT_W_V in
    <= V_MAX_LINES lines. Returns (font, lines, line_h, widths)."""
    font = ImageFont.truetype(TENSION_FONT, V_MIN_FONT)
    lines = _wrap(text, font, draw, MAX_TEXT_W_V)
    for size in range(V_MAX_FONT, V_MIN_FONT - 1, -2):
        font = ImageFont.truetype(TENSION_FONT, size)
        lines = _wrap(text, font, draw, MAX_TEXT_W_V)
        if len(lines) > V_MAX_LINES:
            continue
        widths = [draw.textlength(ln, font=font) for ln in lines]
        if max(widths) <= MAX_TEXT_W_V:
            break
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    widths = [draw.textlength(ln, font=font) for ln in lines]
    return font, lines, line_h, widths


def compose_vertical(subject_path: str, tension_text: str, out_path: str) -> None:
    """Render the 1080×1920 vertical cover (shorts / TikTok / Reels) to out_path (JPEG):
    real subject photo, cinematic grade, a dark bottom scrim, and giant bottom-stacked Anton
    text with the LAST line in channel red."""
    base = ImageOps.fit(Image.open(subject_path).convert("RGB"), (VW, VH), Image.LANCZOS)
    graded = _grade(base, VW, VH)
    # bottom-weighted dark scrim so text stays legible on bright photos (top stays clear)
    scrim = Image.linear_gradient("L").resize((VW, VH)).point(lambda v: int(255 - v * 0.78))
    graded = ImageChops.multiply(graded, Image.merge("RGB", (scrim, scrim, scrim)))
    draw = ImageDraw.Draw(graded)
    _draw_stamp(draw, VW)
    text = (tension_text or "").strip()
    if text:
        font, lines, line_h, widths = _layout_vertical(text, draw)
        block_h = line_h * len(lines)
        top = VH - V_BOTTOM_MARGIN - block_h
        for i, ln in enumerate(lines):
            x = (VW - widths[i]) // 2
            y = top + i * line_h
            fill = RED if i == len(lines) - 1 else (255, 255, 255)   # last line = accent
            draw.text((x + 4, y + 4), ln, font=font, fill=(0, 0, 0))   # shadow
            draw.text((x, y), ln, font=font, fill=fill)
    graded.save(out_path, "JPEG", quality=88)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_thumbnail.py -q`
Expected: PASS (new + existing).

- [ ] **Step 6: Commit**

```bash
git add engine/pipeline/thumbnail.py tests/test_thumbnail.py
git commit -m "feat(thumbnail): compose_vertical — 1080x1920 cover, red accent last line"
```

---

## Task 3: Route `generate_thumbnail` by format

**Files:** Modify `engine/pipeline/thumbnail.py` (`generate_thumbnail`). Test: `tests/test_thumbnail.py`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_thumbnail.py`:

```python
def test_generate_thumbnail_short_is_vertical(tmp_path, monkeypatch):
    from engine import paths
    # subject + output paths point into tmp
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1500, 2200), (100, 80, 60)).save(subj)
    out = tmp_path / "thumbnail.jpg"
    monkeypatch.setattr(paths, "subject_path", lambda i, f: str(subj))
    monkeypatch.setattr(paths, "thumbnail_path", lambda i, f: str(out))
    monkeypatch.setattr(tn, "_thumbnail_text", lambda idea, script: "BANNED THEN A DYNASTY")

    tn.generate_thumbnail({"id": "x", "script": ""}, "short")
    with Image.open(out) as im:
        assert im.size == (1080, 1920)   # short → vertical


def test_generate_thumbnail_long_is_landscape(tmp_path, monkeypatch):
    from engine import paths
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1500, 1000), (100, 80, 60)).save(subj)
    out = tmp_path / "thumb_long.jpg"
    monkeypatch.setattr(paths, "subject_path", lambda i, f: str(subj))
    monkeypatch.setattr(paths, "thumbnail_path", lambda i, f: str(out))
    monkeypatch.setattr(tn, "_thumbnail_text", lambda idea, script: "10 DAYS LATER")

    tn.generate_thumbnail({"id": "x", "script": ""}, "long")
    with Image.open(out) as im:
        assert im.size == (1280, 720)    # long → unchanged
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_thumbnail.py::test_generate_thumbnail_short_is_vertical -v`
Expected: FAIL — current `generate_thumbnail` always calls `compose` → output is 1280×720, not 1080×1920.

- [ ] **Step 3: Route by format**

In `generate_thumbnail`, replace the single `compose(subject, text, out)` call with:

```python
    text = _thumbnail_text(idea, idea.get("script", ""))
    out = paths.thumbnail_path(idea_id, fmt)
    if fmt == "short":
        compose_vertical(subject, text, out)
    else:
        compose(subject, text, out)
```

(Keep the surrounding subject-lookup, self-stub, and `return idea` exactly as-is. Verify the
existing variable names `idea_id`, `subject`, `out` match what's already in the function.)

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/thumbnail.py tests/test_thumbnail.py
git commit -m "feat(thumbnail): generate_thumbnail routes short -> vertical cover"
```

---

## Task 4: Proof (manual — needs a real photo)

**Files:** none.

- [ ] **Step 1:** Drop a real, licensed/free subject photo at `produced/25051da8/short/subject.png` (≥2000px long side).
- [ ] **Step 2:** Run `python3 -m engine.run_thumbnail --id 25051da8 --format short`.
- [ ] **Step 3:** `open produced/25051da8/short/thumbnail.jpg` — confirm 1080×1920, bold bottom-stacked text, last line red, over the real photo, stamp visible, ≤2 MB.

---

## Ship

`feat/vertical-thumbnail` → `pytest tests/ -q` green + dual adversarial review (Codex + Claude) → PR with `Adversarial-Reviewed:` trailer → squash-merge (`ship-video-change`; engine change → trailer required).

## Self-Review (done at write time)

- **Spec coverage:** 1080×1920 + bottom-stack + grade reuse → Tasks 1-2; red accent last line → Task 2; fmt routing → Task 3; self-stub/empty-text → Task 2 tests + unchanged guard; proof → Task 4. All mapped.
- **Name consistency:** `_grade(base,w,h)`, `_draw_stamp(draw,w=W)`, `_layout_vertical`, `compose_vertical`, constants `VW/VH/MAX_TEXT_W_V/V_MAX_FONT/V_MIN_FONT/V_MAX_LINES/V_BOTTOM_MARGIN`, `RED` — all defined before use; Task 3 uses Task 2's `compose_vertical`.
- **No placeholders:** every step has concrete code + command + expected result.
- **Refactor safety:** Task 1 is guarded by the existing compose tests (output must stay 1280×720, byte-similar treatment).
