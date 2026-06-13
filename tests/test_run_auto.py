import json
import time

from engine import run_auto


def test_select_returns_top_n_pending(monkeypatch):
    pending = [{"id": "a"}, {"id": "b"}, {"id": "c"}]  # get_pending() already sorts by score
    monkeypatch.setattr(run_auto.q, "get_pending", lambda: pending)
    assert [i["id"] for i in run_auto._select(2)] == ["a", "b"]


def test_produce_one_returns_resulting_status(monkeypatch):
    monkeypatch.setattr(run_auto, "_run", lambda *a, **k: 0)  # produce subprocess "succeeds"
    monkeypatch.setattr(run_auto.q, "get_by_id",
                        lambda i: {"id": i, "status": "in_production", "human_reviewed": False})
    assert run_auto._produce_one("x") == "in_production"


def test_run_kills_on_timeout():
    start = time.monotonic()
    rc = run_auto._run(["sleep", "10"], timeout=1)
    assert rc == 124
    assert time.monotonic() - start < 5  # killed promptly, not after 10s


def test_render_one_marks_render_failed_on_nonzero(monkeypatch):
    monkeypatch.setattr(run_auto, "_run", lambda *a, **k: 1)
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    assert run_auto._render_one("x") is False
    assert seen["status"] == "render_failed"


def _stub_pipeline(monkeypatch, idea, render_ok=True, qc_pass=True):
    monkeypatch.setattr(run_auto, "_select", lambda n: [idea])
    monkeypatch.setattr(run_auto, "_produce_one", lambda i: idea["status"])
    monkeypatch.setattr(run_auto, "_render_one", lambda i: render_ok)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="long": {"passed": qc_pass, "checks": []})
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: (seen.update(f), idea.update(f)))
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    return seen


def test_pipeline_marks_awaiting_approval_on_qc_pass(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    seen = _stub_pipeline(monkeypatch, idea, qc_pass=True)
    run_auto.pipeline(count=1, no_render=False)
    assert seen["status"] == "awaiting_approval"


def test_pipeline_human_reviewed_clears_to_render(monkeypatch):
    idea = {"id": "x", "status": "needs_review", "human_reviewed": True}
    seen = _stub_pipeline(monkeypatch, idea, qc_pass=True)
    run_auto.pipeline(count=1, no_render=False)
    assert seen["status"] == "awaiting_approval"


def test_pipeline_skips_unreviewed_needs_review(monkeypatch):
    idea = {"id": "x", "status": "needs_review", "human_reviewed": False}
    called = {"render": False}
    monkeypatch.setattr(run_auto, "_select", lambda n: [idea])
    monkeypatch.setattr(run_auto, "_produce_one", lambda i: "needs_review")
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    monkeypatch.setattr(run_auto, "_render_one",
                        lambda i: called.__setitem__("render", True) or True)
    run_auto.pipeline(count=1, no_render=False)
    assert called["render"] is False  # never rendered an unreviewed needs_review idea


def test_pipeline_marks_qc_failed(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    seen = _stub_pipeline(monkeypatch, idea, qc_pass=False)
    run_auto.pipeline(count=1, no_render=False)
    assert seen["status"] == "qc_failed"


def test_cmd_review_sets_two_fields(monkeypatch):
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto.cmd_review("x", note="checked scorecard")
    assert seen["human_reviewed"] is True
    assert seen["human_review_note"].endswith("checked scorecard")


def test_cmd_approve_uploads_and_marks_published(monkeypatch):
    idea = {"id": "x", "status": "awaiting_approval",
            "metadata_path": "produced/x/metadata.json",
            "video_path": "produced/x/video/video.mp4"}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    monkeypatch.setattr(run_auto, "_load_metadata",
                        lambda p: {"title": "T", "description": "D", "tags": ["a"]})
    calls = {}
    monkeypatch.setattr(run_auto.uploader, "upload",
                        lambda **k: calls.update(k) or "yt123")
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto.cmd_approve("x", public=False, dry_run=False)
    assert calls["privacy"] == "unlisted"
    assert seen["status"] == "published"
    assert "yt123" in seen["long_youtube_url"]


def test_cmd_approve_dry_run_skips_upload(monkeypatch):
    idea = {"id": "x", "status": "awaiting_approval",
            "metadata_path": "produced/x/metadata.json",
            "video_path": "produced/x/video/video.mp4"}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    monkeypatch.setattr(run_auto, "_load_metadata",
                        lambda p: {"title": "T", "description": "D", "tags": ["a"]})
    monkeypatch.setattr(run_auto.auth, "get_credentials", lambda: object())  # auth exercised
    monkeypatch.setattr(run_auto, "_ROOT", "/")  # so os.path.exists(video) is checkable
    import os
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    called = {"upload": False}
    monkeypatch.setattr(run_auto.uploader, "upload",
                        lambda **k: called.__setitem__("upload", True))
    run_auto.cmd_approve("x", public=False, dry_run=True)
    assert called["upload"] is False


def test_pipeline_render_failed_skips_qc(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    monkeypatch.setattr(run_auto, "_select", lambda n: [idea])
    monkeypatch.setattr(run_auto, "_produce_one", lambda i: idea["status"])
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    monkeypatch.setattr(run_auto, "_render_one", lambda i: False)
    called = {"qc": False}
    monkeypatch.setattr(run_auto.qc, "qc_video",
                        lambda i, fmt="long": called.__setitem__("qc", True) or {"passed": True, "checks": []})
    run_auto.pipeline(count=1, no_render=False)
    assert called["qc"] is False  # render_failed → never QC'd


def test_pipeline_no_render_stops_before_render(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    monkeypatch.setattr(run_auto, "_select", lambda n: [idea])
    monkeypatch.setattr(run_auto, "_produce_one", lambda i: idea["status"])
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    called = {"render": False}
    monkeypatch.setattr(run_auto, "_render_one",
                        lambda i: called.__setitem__("render", True) or True)
    run_auto.pipeline(count=1, no_render=True)
    assert called["render"] is False


def test_pipeline_batch_isolation_one_failure_continues(monkeypatch):
    ideas = [{"id": "bad", "status": "in_production", "human_reviewed": False},
             {"id": "good", "status": "in_production", "human_reviewed": False}]
    monkeypatch.setattr(run_auto, "_select", lambda n: ideas)
    monkeypatch.setattr(run_auto.q, "get_by_id",
                        lambda i: {"id": i, "status": "in_production", "human_reviewed": False})

    def boom(idea_id):
        if idea_id == "bad":
            raise RuntimeError("produce blew up")
        return "in_production"

    monkeypatch.setattr(run_auto, "_produce_one", boom)
    monkeypatch.setattr(run_auto, "_render_one", lambda i: True)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="long": {"passed": True, "checks": []})
    seen = []
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.append((i, f.get("status"))))
    run_auto.pipeline(count=2, no_render=False)
    assert ("good", "awaiting_approval") in seen  # 2nd idea ran despite the 1st throwing


def test_cmd_list_empty(monkeypatch, capsys):
    monkeypatch.setattr(run_auto.q, "get_by_status", lambda s: [])
    run_auto.cmd_list()
    assert "No videos awaiting approval" in capsys.readouterr().out


def test_cmd_reject_marks_rejected(monkeypatch):
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto.cmd_reject("x")
    assert seen["status"] == "rejected"


def test_cmd_render_renders_cleared_human_reviewed_idea(monkeypatch):
    # the previously-unreachable override path: needs_review + human_reviewed → renders
    idea = {"id": "x", "status": "needs_review", "human_reviewed": True}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    monkeypatch.setattr(run_auto, "_render_one", lambda i: True)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="long": {"passed": True, "checks": []})
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    produce_called = {"v": False}
    monkeypatch.setattr(run_auto, "_produce_one",
                        lambda i: produce_called.__setitem__("v", True) or "x")
    run_auto.cmd_render("x")
    assert seen["status"] == "awaiting_approval"
    assert produce_called["v"] is False  # crucially: did NOT regenerate the script


def test_cmd_render_refuses_uncleared_idea(monkeypatch):
    idea = {"id": "x", "status": "needs_review", "human_reviewed": False}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    import pytest
    with pytest.raises(SystemExit):
        run_auto.cmd_render("x")


def test_cmd_approve_refuses_non_awaiting(monkeypatch):
    idea = {"id": "x", "status": "in_production",
            "metadata_path": "produced/x/metadata.json",
            "video_path": "produced/x/video/video.mp4"}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    import pytest
    with pytest.raises(SystemExit):
        run_auto.cmd_approve("x", public=False, dry_run=False)


def test_cmd_list_shows_qc_summary(monkeypatch, tmp_path, capsys):
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    qc_dir = tmp_path / "produced" / "x" / "long"
    qc_dir.mkdir(parents=True)
    (qc_dir / "qc.json").write_text(json.dumps(
        {"passed": False, "checks": [{"name": "brightness_band", "passed": False}]}))
    monkeypatch.setattr(run_auto.q, "get_by_status",
                        lambda s: [{"id": "x", "title_variants": ["T"]}])
    run_auto.cmd_list()
    out = capsys.readouterr().out
    assert "QC FAIL" in out and "brightness_band" in out


from collections import Counter


def test_pipeline_returns_status_counter(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    _stub_pipeline(monkeypatch, idea, qc_pass=True)
    result = run_auto.pipeline(count=1, no_render=False)
    assert isinstance(result, Counter)
    assert result["awaiting_approval"] == 1


def test_summary_message_lists_counts():
    msg = run_auto._summary_message(Counter({"awaiting_approval": 2, "qc_failed": 1}))
    assert "2 awaiting_approval" in msg
    assert "1 qc_failed" in msg


def test_summary_message_handles_empty():
    assert run_auto._summary_message(Counter()) == "No ideas produced."


def test_pipeline_counts_not_cleared_idea(monkeypatch):
    idea = {"id": "x", "status": "needs_review", "human_reviewed": False}
    _stub_pipeline(monkeypatch, idea, qc_pass=True)
    result = run_auto.pipeline(count=1, no_render=False)
    assert result["needs_review"] == 1


def test_notify_invokes_osascript(monkeypatch):
    calls = {}
    monkeypatch.setattr(run_auto.subprocess, "run",
                        lambda cmd, **k: calls.setdefault("cmd", cmd))
    run_auto._notify("3 produced: 2 awaiting_approval")
    assert calls["cmd"][0] == "osascript"
    assert any("3 produced" in str(part) for part in calls["cmd"])


def test_notify_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("no osascript")
    monkeypatch.setattr(run_auto.subprocess, "run", boom)
    run_auto._notify("anything")  # must not raise


def test_cmd_backlink_appends_long_url_to_short(monkeypatch):
    idea = {"id": "x",
            "long_youtube_url": "https://youtu.be/LONGvideoAB",
            "short_youtube_url": "https://youtu.be/SHORTvid123"}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    calls = {}
    monkeypatch.setattr(run_auto.uploader, "append_to_description",
                        lambda vid, suffix, **k: calls.update(vid=vid, suffix=suffix) or "newdesc")
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: True)
    run_auto.cmd_backlink("x")
    assert calls["vid"] == "SHORTvid123"            # extracted the short's video id
    assert "https://youtu.be/LONGvideoAB" in calls["suffix"]


def test_cmd_backlink_refuses_without_both_urls(monkeypatch):
    monkeypatch.setattr(run_auto.q, "get_by_id",
                        lambda i: {"id": "x", "short_youtube_url": "https://youtu.be/SHORTvid123"})
    import pytest
    with pytest.raises(SystemExit):
        run_auto.cmd_backlink("x")


def test_cmd_backlink_refuses_if_already_backlinked(monkeypatch):
    idea = {"id": "x", "long_youtube_url": "https://youtu.be/LONGvideoAB",
            "short_youtube_url": "https://youtu.be/SHORTvid123", "short_backlinked": True}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    called = {"append": False}
    monkeypatch.setattr(run_auto.uploader, "append_to_description",
                        lambda *a, **k: called.__setitem__("append", True))
    import pytest
    with pytest.raises(SystemExit):
        run_auto.cmd_backlink("x")
    assert called["append"] is False   # never touched the live description


def test_video_id_parses_misordered_query_and_rejects_garbage():
    import pytest
    assert run_auto._video_id("https://www.youtube.com/watch?si=x&v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert run_auto._video_id("https://youtu.be/dQw4w9WgXcQ?si=abc") == "dQw4w9WgXcQ"
    assert run_auto._video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    with pytest.raises(ValueError):
        run_auto._video_id("https://example.com/definitely-not-a-yt-url")


def test_render_companion_short_renders_and_qcs(monkeypatch):
    monkeypatch.setattr(run_auto, "_produce_companion", lambda i: {"within_long": True})
    calls = {}

    def _fake_run(cmd, timeout=None):
        calls["cmd"] = cmd
        return 0

    monkeypatch.setattr(run_auto, "_run", _fake_run)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="long": {"passed": True, "checks": []})
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto._companion_short("x")
    assert "--format" in calls["cmd"] and "short" in calls["cmd"]
    assert seen.get("short_status") == "short_awaiting_approval"
    assert "short_video_path" in seen


def test_companion_short_failure_does_not_raise(monkeypatch):
    monkeypatch.setattr(run_auto, "_produce_companion",
                        lambda i: (_ for _ in ()).throw(RuntimeError("derive blew up")))
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto._companion_short("x")   # must not raise
    assert seen.get("short_status") == "short_failed"


def test_companion_short_guard_fail_flags_needs_review(monkeypatch):
    monkeypatch.setattr(run_auto, "_produce_companion", lambda i: {"within_long": False})
    called = {"render": False}
    monkeypatch.setattr(run_auto, "_run", lambda cmd, timeout=None: called.__setitem__("render", True) or 0)
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto._companion_short("x")
    assert seen.get("short_status") == "short_needs_review"
    assert called["render"] is False    # guard failed → never rendered


def test_cmd_approve_uploads_long_then_linked_short(monkeypatch):
    idea = {"id": "x", "status": "awaiting_approval",
            "metadata_path": "produced/x/long/metadata.json",
            "video_path": "produced/x/long/video/video.mp4",
            "short_status": "short_awaiting_approval",
            "short_metadata_path": "produced/x/short/metadata.json",
            "short_video_path": "produced/x/short/video/video.mp4"}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    metas = {"produced/x/long/metadata.json": {"title": "Long", "description": "L", "tags": []},
             "produced/x/short/metadata.json": {"title": "Short", "description": "S", "tags": []}}
    monkeypatch.setattr(run_auto, "_load_metadata", lambda p: metas[p])
    import os
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    ups = []
    monkeypatch.setattr(run_auto.uploader, "upload",
                        lambda **k: ups.append(k) or ("ytLONG" if "Long" in k["title"] else "ytSHORT"))
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto.cmd_approve("x", public=False, dry_run=False)
    assert ups[0]["title"] == "Long" and ups[1]["title"] == "Short"
    assert "youtu.be/ytLONG" in ups[1]["description"]   # short desc links the long
    assert "ytLONG" in seen["long_youtube_url"] and "ytSHORT" in seen["short_youtube_url"]
