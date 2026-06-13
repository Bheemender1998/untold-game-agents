import os
from PIL import ImageFont
from engine.pipeline import banner


def test_subtitle_font_loads():
    assert os.path.exists(banner.SUBTITLE_FONT), f"missing: {banner.SUBTITLE_FONT}"
    ImageFont.truetype(banner.SUBTITLE_FONT, 50)
