import os
from PIL import ImageFont
from engine.pipeline import thumbnail


def test_bundled_fonts_load():
    for path in (thumbnail.TENSION_FONT, thumbnail.STAMP_FONT):
        assert os.path.exists(path), f"missing bundled font: {path}"
        ImageFont.truetype(path, 40)  # raises if the file isn't a valid font
