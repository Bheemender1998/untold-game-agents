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


def test_layout_vertical_wraps_and_fits():
    d = ImageDraw.Draw(Image.new("RGB", (tn.VW, tn.VH)))
    font, lines, line_h, widths = tn._layout_vertical("BANNED THEN A DYNASTY", d)
    assert 1 <= len(lines) <= 4
    assert max(widths) <= tn.MAX_TEXT_W_V
    assert tn.V_MIN_FONT <= font.size <= tn.V_MAX_FONT


def test_compose_vertical_writes_1080x1920_jpeg(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1500, 2200), (110, 80, 60)).save(subj)
    out = tmp_path / "cover.jpg"
    tn.compose_vertical(str(subj), "BANNED THEN A DYNASTY", str(out))
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (1080, 1920)
        assert im.format == "JPEG"
    assert out.stat().st_size < 2_000_000


def test_compose_vertical_handles_empty_text(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1080, 1920), (80, 80, 80)).save(subj)
    out = tmp_path / "cover2.jpg"
    tn.compose_vertical(str(subj), "", str(out))   # subject + stamp only, no crash
    with Image.open(out) as im:
        assert im.size == (1080, 1920)


def test_compose_vertical_omits_text_when_it_cannot_fit(tmp_path):
    # Pathological text (over-wide single word; very long string) must not draw off-frame —
    # the band is omitted, the graded photo + stamp stand. Mirrors the 16:9 _draw_tension guard.
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1500, 2200), (100, 80, 60)).save(subj)
    for bad in ["PNEUMONOULTRAMICROSCOPICSILICOVOLCANOCONIOSIS", "WORD " * 220]:
        out = tmp_path / "covbad.jpg"
        tn.compose_vertical(str(subj), bad, str(out))   # must not raise / draw off-frame
        with Image.open(out) as im:
            assert im.size == (1080, 1920)


def test_thumbnail_text_uses_human_override(monkeypatch):
    # override present -> used verbatim, no LLM call
    monkeypatch.setattr(tn, "_thumbnail_text_llm", lambda i, s: (_ for _ in ()).throw(AssertionError("LLM should not be called")))
    assert tn._thumbnail_text({"thumbnail_text": "10 DAYS LATER"}, "script") == "10 DAYS LATER"


def test_thumbnail_text_uses_llm_when_clean(monkeypatch):
    monkeypatch.setattr(tn, "_thumbnail_text_llm", lambda i, s: "THEN HE VANISHED")
    assert tn._thumbnail_text({}, "He retired one season short of the record.") == "THEN HE VANISHED"


def test_thumbnail_text_rejects_fabricated_number(monkeypatch):
    # '1500' is not in the script -> digit backstop rejects -> empty (no override)
    monkeypatch.setattr(tn, "_thumbnail_text_llm", lambda i, s: "1500 YARDS SHORT")
    assert tn._thumbnail_text({}, "He retired 1457 yards short.") == ""


def test_thumbnail_text_falls_back_to_empty_on_llm_error(monkeypatch):
    def boom(i, s):
        raise RuntimeError("down")
    monkeypatch.setattr(tn, "_thumbnail_text_llm", boom)
    assert tn._thumbnail_text({}, "script") == ""


import os as _os


def test_generate_thumbnail_self_stubs_without_subject(tmp_path, monkeypatch):
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    _os.makedirs(paths.artifact_dir("id9", "short"), exist_ok=True)
    idea = {"id": "id9"}
    out = tn.generate_thumbnail(idea, "short")   # no subject photo present
    assert out is idea                            # returned unchanged
    assert not _os.path.exists(paths.thumbnail_path("id9", "short"))   # no file, no crash


def test_generate_thumbnail_composites_when_subject_present(tmp_path, monkeypatch):
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    d = paths.artifact_dir("id8", "long")
    _os.makedirs(d, exist_ok=True)
    Image.new("RGB", (1000, 1000), (100, 80, 60)).save(_os.path.join(d, "subject.png"))
    monkeypatch.setattr(tn, "_thumbnail_text", lambda idea, script: "THEN HE VANISHED")
    idea = {"id": "id8", "script": "He retired one season short."}
    tn.generate_thumbnail(idea, "long")
    assert _os.path.exists(paths.thumbnail_path("id8", "long"))
    with Image.open(paths.thumbnail_path("id8", "long")) as im:
        assert im.size == (1280, 720)


def test_generate_thumbnail_short_is_vertical(tmp_path, monkeypatch):
    from engine import paths
    # subject + output paths point into tmp
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1500, 2200), (100, 80, 60)).save(subj)
    out = tmp_path / "thumbnail.jpg"
    monkeypatch.setattr(paths, "subject_path", lambda i, f: str(subj))
    monkeypatch.setattr(paths, "thumbnail_path", lambda i, f: str(out))
    monkeypatch.setattr(tn, "_thumbnail_text", lambda idea, script: "BANNED THEN A DYNASTY")

    tn.generate_thumbnail({"id": "x", "script": ""}, "short")
    with Image.open(out) as im:
        assert im.size == (1080, 1920)   # short → vertical


def test_generate_thumbnail_long_is_landscape(tmp_path, monkeypatch):
    from engine import paths
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1500, 1000), (100, 80, 60)).save(subj)
    out = tmp_path / "thumb_long.jpg"
    monkeypatch.setattr(paths, "subject_path", lambda i, f: str(subj))
    monkeypatch.setattr(paths, "thumbnail_path", lambda i, f: str(out))
    monkeypatch.setattr(tn, "_thumbnail_text", lambda idea, script: "10 DAYS LATER")

    tn.generate_thumbnail({"id": "x", "script": ""}, "long")
    with Image.open(out) as im:
        assert im.size == (1280, 720)    # long → unchanged


def test_compose_omits_tension_when_text_cannot_fit(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1280, 720), (90, 90, 90)).save(subj)
    out = tmp_path / "pathological.jpg"
    tn.compose(str(subj), "WORD " * 120, str(out))   # impossible to fit — must not crash or go off-canvas
    with Image.open(out) as im:
        assert im.size == (1280, 720)


def test_compose_handles_whitespace_only_tension(tmp_path):
    subj = tmp_path / "subject.png"
    Image.new("RGB", (1280, 720), (90, 90, 90)).save(subj)
    out = tmp_path / "ws.jpg"
    tn.compose(str(subj), "   ", str(out))            # whitespace -> treated as empty, no crash
    with Image.open(out) as im:
        assert im.size == (1280, 720)


def test_generate_thumbnail_removes_stale_thumbnail_when_subject_missing(tmp_path, monkeypatch):
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    d = paths.artifact_dir("stale1", "long")
    _os.makedirs(d, exist_ok=True)
    # a leftover thumbnail exists but the subject photo does NOT
    Image.new("RGB", (1280, 720), (0, 0, 0)).save(paths.thumbnail_path("stale1", "long"))
    assert _os.path.exists(paths.thumbnail_path("stale1", "long"))
    tn.generate_thumbnail({"id": "stale1"}, "long")
    assert not _os.path.exists(paths.thumbnail_path("stale1", "long"))   # stale removed


def test_generate_thumbnail_self_stub_survives_remove_error(tmp_path, monkeypatch):
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    d = paths.artifact_dir("s2", "long")
    _os.makedirs(d, exist_ok=True)
    Image.new("RGB", (1280, 720), (0, 0, 0)).save(paths.thumbnail_path("s2", "long"))
    def boom(_p):
        raise OSError("permission denied")
    monkeypatch.setattr(tn.os, "remove", boom)   # removal fails
    # the self-stub path must NEVER propagate — it returns the idea unchanged
    idea = {"id": "s2"}
    out = tn.generate_thumbnail(idea, "long")
    assert out is idea


def test_run_thumbnail_main_errors_without_subject(tmp_path, monkeypatch, capsys):
    import sys
    from engine import paths, queue_manager
    from engine import run_thumbnail
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    _os.makedirs(paths.artifact_dir("idz", "short"), exist_ok=True)
    monkeypatch.setattr(queue_manager, "get_by_id", lambda _id: {"id": "idz", "script": "s"})
    monkeypatch.setattr(sys, "argv", ["run_thumbnail", "--id", "idz", "--format", "short"])
    import pytest
    with pytest.raises(SystemExit) as e:
        run_thumbnail.main()
    assert e.value.code != 0
    out, err = capsys.readouterr()
    assert "no subject photo" in (out + err).lower()


def test_wrap_honors_explicit_newline():
    # An explicit '\n' forces a hard line break (so a cover can be hand-split:
    # "RED FLAG" on line 1, "NO EXPLANATION" on line 2 → last line is the red accent).
    f = ImageFont.truetype(tn.TENSION_FONT, 120)
    d = ImageDraw.Draw(Image.new("RGB", (tn.VW, tn.VH)))
    lines = tn._wrap("RED FLAG\nNO EXPLANATION", f, d, tn.MAX_TEXT_W_V)
    assert lines == ["RED FLAG", "NO EXPLANATION"]


def test_wrap_no_newline_unchanged():
    f = ImageFont.truetype(tn.TENSION_FONT, 60)
    d = ImageDraw.Draw(Image.new("RGB", (tn.W, tn.H)))
    # plain text still greedy-wraps within width (no spurious breaks)
    assert tn._wrap("GONE", f, d, tn.MAX_TEXT_W) == ["GONE"]


def test_generate_thumbnail_feeds_real_script_to_headline(tmp_path, monkeypatch):
    # Bug: generate_thumbnail derived the headline from idea.get("script") — but the queue
    # idea carries only script_path, so the headline LLM always saw an empty string and
    # produced generic copy. It must read the produced script.md from disk.
    from engine import paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path))
    idea_id, fmt = "headlinebug", "long"
    d = paths.artifact_dir(idea_id, fmt)
    os.makedirs(d)
    with open(paths.script_path(idea_id, fmt), "w") as f:
        f.write("A nation's football dream, stolen by war at Euro 1992.")
    Image.new("RGB", (900, 1200), (80, 60, 50)).save(paths.subject_path(idea_id, fmt))

    captured = {}
    monkeypatch.setattr(tn, "_thumbnail_text",
                        lambda idea, script: captured.setdefault("script", script) or "X")
    monkeypatch.setattr(tn, "compose", lambda *a, **k: None)
    monkeypatch.setattr(tn, "compose_vertical", lambda *a, **k: None)

    # Exact queue regression shape: idea carries an empty "script" plus a script_path.
    tn.generate_thumbnail(
        {"id": idea_id, "script": "", "script_path": paths.script_path(idea_id, fmt)}, fmt)
    assert "football dream" in captured.get("script", ""), \
        "headline must be derived from the real script.md, not an empty string"
