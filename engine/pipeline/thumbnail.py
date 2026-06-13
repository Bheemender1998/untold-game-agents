"""Stage 2 — THUMBNAIL: deterministic Pillow compositor for the channel's
"Prestige Feed Killer" thumbnail template (asset layer + tension layer)."""
from __future__ import annotations
import os
from PIL import ImageFont

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
