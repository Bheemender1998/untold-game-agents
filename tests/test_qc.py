from engine.pipeline import qc
from tests.conftest import requires_ffmpeg


@requires_ffmpeg
def test_render_integrity_passes_on_good_video(gray_video, silent_audio):
    r = qc.render_integrity(str(gray_video), str(silent_audio))
    assert r["name"] == "render_integrity"
    assert r["passed"] is True


@requires_ffmpeg
def test_render_integrity_fails_when_audio_missing(gray_video, tmp_path):
    r = qc.render_integrity(str(gray_video), str(tmp_path / "nope.wav"))
    assert r["passed"] is False
