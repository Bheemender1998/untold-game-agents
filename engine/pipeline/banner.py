"""Stage 2 — BANNER: deterministic Pillow generator for the channel's
"Editorial Archive" banner (textural backdrop + wordmark + rule + subtitle)."""
from __future__ import annotations
import os
import random

from engine.pipeline import thumbnail

_FONTS = os.path.dirname(thumbnail.TENSION_FONT)
WORDMARK_FONT = thumbnail.TENSION_FONT                       # Anton (reused)
SUBTITLE_FONT = os.path.join(_FONTS, "PlayfairDisplay-Italic.ttf")
RED = thumbnail.RED

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from engine import config

W, H = 2560, 1440
SAFE_W, SAFE_H = 1546, 423                      # YouTube all-device-safe area
SAFE_LEFT, SAFE_TOP = (W - SAFE_W) // 2, (H - SAFE_H) // 2
WORDMARK_MAX = 220
SUB_SIZE = 52
RULE_H = 8
GAP = 24


def _gradient():
    """Warm archival vertical gradient: warm-lit at the top, dark at the bottom."""
    g = Image.linear_gradient("L").resize((W, H))           # 0 (top) -> 255 (bottom)
    return ImageOps.colorize(g, black=(74, 56, 38), white=(18, 12, 6))


def _grain():
    """Deterministic film grain (fixed seed) — keeps compose_banner bit-reproducible."""
    rnd = random.Random(1979)
    tile = Image.new("L", (256, 256))
    tile.putdata([rnd.randint(0, 255) for _ in range(256 * 256)])
    return tile.resize((W, H)).convert("RGB")


def _layout_banner(draw):
    """Place wordmark + red rule + subtitle, centred in the TV-safe band. The wordmark always
    shrinks to fit the safe width (preferring the height budget when both constraints can be
    met); the configured subtitle fits the safe width fully.
    Returns the fonts, per-element boxes, and the union block_box (all (l,t,r,b) tuples)."""
    target_w = int(SAFE_W * 0.96)
    name = config.CHANNEL_NAME.upper()
    sub = config.CHANNEL_SUBTITLE

    # subtitle: fit to width
    sub_size = SUB_SIZE
    sf = ImageFont.truetype(SUBTITLE_FONT, sub_size)
    while sub_size > 20 and draw.textlength(sub, font=sf) > target_w:
        sub_size -= 2
        sf = ImageFont.truetype(SUBTITLE_FONT, sub_size)
    slh = sum(sf.getmetrics())

    # Largest size that fits BOTH width and the height budget; if none fits both (overlong
    # name / tiny budget), fall back to the largest that fits the safe WIDTH — so the wordmark
    # can never overflow horizontally regardless of name length.
    wm_budget_h = SAFE_H - (slh + GAP + RULE_H + GAP) - 20
    wf = width_fit = None
    for size in range(WORDMARK_MAX, 16, -2):
        f = ImageFont.truetype(WORDMARK_FONT, size)
        if draw.textlength(name, font=f) <= target_w:
            if width_fit is None:
                width_fit = f
            if sum(f.getmetrics()) <= wm_budget_h:
                wf = f
                break
    if wf is None:
        wf = width_fit if width_fit is not None else ImageFont.truetype(WORDMARK_FONT, 18)
    wlh = sum(wf.getmetrics())
    ww = draw.textlength(name, font=wf)
    sw = draw.textlength(sub, font=sf)
    rule_w = int(SAFE_W * 0.42)

    stack_h = wlh + GAP + RULE_H + GAP + slh
    top = SAFE_TOP + (SAFE_H - stack_h) // 2
    cx = W // 2
    wm_box = (cx - ww / 2, top, cx + ww / 2, top + wlh)
    rule_y = top + wlh + GAP
    rule_box = (cx - rule_w / 2, rule_y, cx + rule_w / 2, rule_y + RULE_H)
    sub_y = rule_y + RULE_H + GAP
    sub_box = (cx - sw / 2, sub_y, cx + sw / 2, sub_y + slh)
    block_box = (min(wm_box[0], rule_box[0], sub_box[0]), top,
                 max(wm_box[2], rule_box[2], sub_box[2]), sub_y + slh)
    return {"wf": wf, "sf": sf, "name": name, "sub": sub,
            "wm_box": wm_box, "rule_box": rule_box, "sub_box": sub_box, "block_box": block_box}


def compose_banner(out_path: str) -> None:
    """Render the 2560x1440 'Editorial Archive' channel banner to out_path (PNG)."""
    base = _gradient()
    img = Image.blend(base, _grain(), 0.06)
    vig = ImageOps.invert(Image.radial_gradient("L")).resize((W, H)).point(lambda v: int(70 + v * 0.72))
    img = ImageChops.multiply(img, Image.merge("RGB", (vig, vig, vig)))
    draw = ImageDraw.Draw(img)
    L = _layout_banner(draw)
    wm = L["wm_box"]
    draw.text((wm[0] + 3, wm[1] + 3), L["name"], font=L["wf"], fill=(0, 0, 0))      # shadow
    draw.text((wm[0], wm[1]), L["name"], font=L["wf"], fill=(255, 255, 255))
    draw.rectangle([int(v) for v in L["rule_box"]], fill=RED)
    sb = L["sub_box"]
    draw.text((sb[0], sb[1]), L["sub"], font=L["sf"], fill=(231, 220, 194))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG")
