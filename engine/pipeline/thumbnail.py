"""Stage 2 — THUMBNAIL: deterministic Pillow compositor for the channel's
"Prestige Feed Killer" thumbnail template (asset layer + tension layer)."""
from __future__ import annotations
import json
import os
import anthropic
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageOps
from engine.config import MODEL
from engine.pipeline.script import title_numbers_within

_FONTS = os.path.join(os.path.dirname(__file__), "assets", "fonts")
TENSION_FONT = os.path.join(_FONTS, "Anton-Regular.ttf")
STAMP_FONT = os.path.join(_FONTS, "PlayfairDisplay.ttf")

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
