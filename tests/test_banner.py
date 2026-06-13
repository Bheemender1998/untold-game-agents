import os
from PIL import Image, ImageDraw, ImageFont
from engine.pipeline import banner


def test_subtitle_font_loads():
    assert os.path.exists(banner.SUBTITLE_FONT), f"missing: {banner.SUBTITLE_FONT}"
    ImageFont.truetype(banner.SUBTITLE_FONT, 50)


def test_compose_banner_writes_2560x1440_png(tmp_path):
    out = tmp_path / "banner.png"
    banner.compose_banner(str(out))
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (2560, 1440)
        assert im.format == "PNG"


def test_banner_block_within_tv_safe_area():
    d = ImageDraw.Draw(Image.new("RGB", (banner.W, banner.H)))
    L = banner._layout_banner(d)
    bx = L["block_box"]
    assert bx[0] >= banner.SAFE_LEFT and bx[2] <= banner.SAFE_LEFT + banner.SAFE_W
    assert bx[1] >= banner.SAFE_TOP and bx[3] <= banner.SAFE_TOP + banner.SAFE_H
