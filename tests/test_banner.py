import os
from PIL import Image, ImageDraw, ImageFont
from engine.pipeline import banner as bn
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


def test_banner_wordmark_fits_width_for_long_name(monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "CHANNEL_NAME",
                        "THE EXTRAORDINARILY LONG UNTOLD GAME DOCUMENTARY CHANNEL")
    d = ImageDraw.Draw(Image.new("RGB", (bn.W, bn.H)))
    L = bn._layout_banner(d)
    bx = L["block_box"]
    assert bx[0] >= bn.SAFE_LEFT and bx[2] <= bn.SAFE_LEFT + bn.SAFE_W   # width contained, no overflow


def test_compose_banner_is_deterministic(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    bn.compose_banner(str(a))
    bn.compose_banner(str(b))
    assert a.read_bytes() == b.read_bytes()   # bit-identical across runs


def test_run_banner_writes_banner_and_description(tmp_path, monkeypatch):
    from engine import paths, config
    from engine import run_banner
    monkeypatch.setattr(paths, "CHANNEL_DIR", str(tmp_path / "channel"))
    run_banner.main()
    with Image.open(paths.channel_banner_path()) as im:
        assert im.size == (2560, 1440)
    assert open(paths.channel_description_path()).read().strip() == config.CHANNEL_DESCRIPTION.strip()
