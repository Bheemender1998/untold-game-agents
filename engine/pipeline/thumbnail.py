"""Stage 2 — THUMBNAIL: deterministic Pillow compositor for the channel's
"Prestige Feed Killer" thumbnail template (asset layer + tension layer)."""
from __future__ import annotations
import os

_FONTS = os.path.join(os.path.dirname(__file__), "assets", "fonts")
TENSION_FONT = os.path.join(_FONTS, "Anton-Regular.ttf")
STAMP_FONT = os.path.join(_FONTS, "PlayfairDisplay.ttf")
