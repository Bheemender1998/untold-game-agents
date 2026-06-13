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
    # Build a fake produced/<id>/long/video layout
    from engine import paths
    idea_id = "testid01"
    vdir = tmp_path / "produced" / idea_id / "long" / "video"
    vdir.mkdir(parents=True)
    (vdir / "video.mp4").write_bytes(gray_video.read_bytes())
    (vdir / "narration.wav").write_bytes(silent_audio.read_bytes())
    caps = [{"text": "a", "startMs": i * 100, "endMs": i * 100 + 90} for i in range(20)]
    (vdir / "props.json").write_text(json.dumps({"captions": caps}))
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))

    report = qc.qc_video(idea_id, "long")
    assert set(c["name"] for c in report["checks"]) == {
        "render_integrity", "brightness_band", "caption_coverage"}
    assert report["passed"] is True
    assert os.path.exists(tmp_path / "produced" / idea_id / "long" / "qc.json")


def test_caption_coverage_survives_malformed_captions(tmp_path):
    # a caption entry missing "endMs" must NOT raise — it degrades to a failed check
    p = tmp_path / "props.json"
    p.write_text(json.dumps({"captions": [{"text": "a", "startMs": 0}]}))
    r = qc.caption_coverage(str(p), audio_dur=2.0)
    assert r["passed"] is False  # and crucially: no exception was raised


def test_qc_video_survives_missing_idea_dir(tmp_path, monkeypatch):
    # produced/<id>/long/ does not exist — qc_video must still return a report, not raise
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    report = qc.qc_video("ghost_idea", "long")
    assert report["passed"] is False
    assert isinstance(report["checks"], list)
    import os
    assert os.path.exists(tmp_path / "produced" / "ghost_idea" / "long" / "qc.json")


def test_qc_video_routes_to_format_subdir(monkeypatch, tmp_path):
    from engine.pipeline import qc
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    (tmp_path / "produced" / "x" / "short" / "video").mkdir(parents=True)
    report = qc.qc_video("x", "short")           # never raises on missing inputs
    assert "passed" in report
    assert (tmp_path / "produced" / "x" / "short" / "qc.json").exists()   # routed to <fmt>
    assert not (tmp_path / "produced" / "x" / "long" / "qc.json").exists()
