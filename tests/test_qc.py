import json
import os

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


@requires_ffmpeg
def test_brightness_passes_on_grey(gray_video):
    assert qc.brightness_band(str(gray_video))["passed"] is True


@requires_ffmpeg
def test_brightness_fails_on_black(black_video):
    r = qc.brightness_band(str(black_video))
    assert r["passed"] is False
    assert "luma" in r["detail"]


def _props(tmp_path, captions):
    p = tmp_path / "props.json"
    p.write_text(json.dumps({"captions": captions}))
    return p


def test_caption_coverage_passes_full(tmp_path):
    # words span 0..1900ms over a 2.0s audio → 95% coverage, no big gaps
    caps = [{"text": "a", "startMs": i * 100, "endMs": i * 100 + 90} for i in range(20)]
    r = qc.caption_coverage(str(_props(tmp_path, caps)), audio_dur=2.0)
    assert r["passed"] is True


def test_caption_coverage_fails_when_captions_stop_early(tmp_path):
    # words stop at 600ms of a 2.0s audio → 30% coverage
    caps = [{"text": "a", "startMs": i * 100, "endMs": i * 100 + 90} for i in range(6)]
    r = qc.caption_coverage(str(_props(tmp_path, caps)), audio_dur=2.0)
    assert r["passed"] is False


def test_caption_coverage_fails_on_long_gap(tmp_path):
    caps = [{"text": "a", "startMs": 0, "endMs": 100},
            {"text": "b", "startMs": 9000, "endMs": 9100}]  # >8s gap
    r = qc.caption_coverage(str(_props(tmp_path, caps)), audio_dur=9.1)
    assert r["passed"] is False


@requires_ffmpeg
def test_qc_video_writes_report_and_ands_checks(tmp_path, gray_video, silent_audio, monkeypatch):
    # Build a fake produced/<id>/video layout
    idea_id = "testid01"
    vdir = tmp_path / "produced" / idea_id / "video"
    vdir.mkdir(parents=True)
    (vdir / "video.mp4").write_bytes(gray_video.read_bytes())
    (vdir / "narration.wav").write_bytes(silent_audio.read_bytes())
    caps = [{"text": "a", "startMs": i * 100, "endMs": i * 100 + 90} for i in range(20)]
    (vdir / "props.json").write_text(json.dumps({"captions": caps}))
    monkeypatch.setattr(qc, "_ROOT", str(tmp_path))

    report = qc.qc_video(idea_id)
    assert set(c["name"] for c in report["checks"]) == {
        "render_integrity", "brightness_band", "caption_coverage"}
    assert report["passed"] is True
    assert os.path.exists(tmp_path / "produced" / idea_id / "qc.json")
