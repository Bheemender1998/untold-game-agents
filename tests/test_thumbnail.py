import os
from PIL import Image, ImageDraw, ImageFont
from engine.pipeline import thumbnail
from engine.pipeline import thumbnail as tn


def test_bundled_fonts_load():
    for path in (thumbnail.TENSION_FONT, thumbnail.STAMP_FONT):
        assert os.path.exists(path), f"missing bundled font: {path}"
        ImageFont.truetype(path, 40)  # raises if the file isn't a valid font


def _draw():
    return ImageDraw.Draw(Image.new("RGB", (tn.W, tn.H)))


def test_marker_anchored_to_text_block_one_and_three_lines():
    d = _draw()
    f1, lines1, box1, marker1, _, _ = tn._layout_tension("GONE", d)
    f3, lines3, box3, marker3, _, _ = tn._layout_tension("THE NIGHT HE NEVER MADE IT HOME", d)
    assert len(lines1) == 1 and len(lines3) >= 2
    # marker top is exactly MARKER_GAP below the text block's bottom in BOTH cases
    assert marker1[1] - box1[3] == tn.MARKER_GAP
    assert marker3[1] - box3[3] == tn.MARKER_GAP
    # three-line block sits lower-bottom than one-line, and its marker follows it down
    assert marker3[1] > marker1[1]


def test_layout_wraps_to_at_most_three_lines_and_fits_width():
    d = _draw()
    _, lines, box, _, _, _ = tn._layout_tension("THE NIGHT HE NEVER MADE IT HOME", d)
    assert len(lines) <= 3
    assert (box[2] - box[0]) <= tn.MAX_TEXT_W


def test_compose_writes_1280x720_jpeg(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (900, 1200), (120, 90, 70)).save(subj)   # synthetic portrait
    out = tmp_path / "thumbnail.jpg"
    tn.compose(str(subj), "10 DAYS LATER", str(out))
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (1280, 720)
        assert im.format == "JPEG"
    assert out.stat().st_size < 2_000_000   # YouTube's 2 MB limit


def test_compose_handles_empty_tension_text(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1280, 720), (90, 90, 90)).save(subj)
    out = tmp_path / "thumb2.jpg"
    tn.compose(str(subj), "", str(out))   # asset layer only, no crash
    with Image.open(out) as im:
        assert im.size == (1280, 720)
