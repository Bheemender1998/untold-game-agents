"""Stage 2 — BANNER: deterministic Pillow generator for the channel's
"Editorial Archive" banner (textural backdrop + wordmark + rule + subtitle)."""
from __future__ import annotations
import os

from engine.pipeline import thumbnail

_FONTS = os.path.dirname(thumbnail.TENSION_FONT)
WORDMARK_FONT = thumbnail.TENSION_FONT                       # Anton (reused)
SUBTITLE_FONT = os.path.join(_FONTS, "PlayfairDisplay-Italic.ttf")
RED = thumbnail.RED
