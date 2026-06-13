import json

from engine.pipeline import chapters


_DESC = """In 1994, Formula 1 lost its greatest driver.

Chapters:
00:00 – Wrong Estimate One
02:10 – Wrong Estimate Two
05:30 – Wrong Estimate Three

Subscribe for more untold sports history."""

_PROPS = [
    {"headline": "THE LAST LAP", "startMs": 0},
    {"headline": "TWO MEN, TWO WORLDS", "startMs": 31800},
    {"headline": "THE FIRST CLASH", "startMs": 66820},
    {"headline": "TAMBURELLO", "startMs": 122480},
]


def test_rebuild_uses_real_times_and_headlines():
    out = chapters.rebuild_chapters(_DESC, _PROPS)
    lines = [l for l in out.splitlines() if l[:1].isdigit() and ":" in l[:6]]
    assert lines == [
        "00:00 — The Last Lap",
        "00:32 — Two Men, Two Worlds",
        "01:07 — The First Clash",
        "02:02 — Tamburello",
    ]
    # non-chapter content preserved
    assert "In 1994, Formula 1 lost its greatest driver." in out
    assert "Subscribe for more untold sports history." in out
    assert "Chapters:" in out


def test_rebuild_handles_count_mismatch():
    # desc has 3 chapter lines, render produced 4 → result reflects the 4 real chapters
    out = chapters.rebuild_chapters(_DESC, _PROPS)
    assert out.count("\n00:") + (1 if out.startswith("00:") else 0) >= 0  # smoke
    assert "02:02 — Tamburello" in out          # the 4th chapter is present


def test_rebuild_no_chapters_returns_unchanged():
    assert chapters.rebuild_chapters(_DESC, []) == _DESC


def test_rebuild_no_block_returns_unchanged():
    plain = "Just a description with no chapter timestamps at all."
    assert chapters.rebuild_chapters(plain, _PROPS) == plain


def test_rebuild_ignores_stray_prose_timestamp():
    desc = ("The crash happened at 2:10 into the race, a famous moment.\n\n"
            "Chapters:\n00:00 – A\n01:00 – B\n02:00 – C")
    out = chapters.rebuild_chapters(desc, _PROPS)
    # the prose line is NOT treated as the chapter block (block is the longer run)
    assert "The crash happened at 2:10 into the race" in out
    assert "00:00 — The Last Lap" in out and "02:02 — Tamburello" in out


def test_sync_from_render_writes_metadata(tmp_path, monkeypatch):
    from engine import paths
    d = tmp_path / "produced" / "x" / "long"
    (d / "video").mkdir(parents=True)
    (d / "metadata.json").write_text(json.dumps({"title": "T", "description": _DESC}))
    (d / "video" / "props.json").write_text(json.dumps({"chapters": _PROPS}))
    monkeypatch.setattr(paths, "artifact_dir", lambda i, f: str(d))
    assert chapters.sync_from_render("x", "long") is True
    meta = json.loads((d / "metadata.json").read_text())
    assert "02:02 — Tamburello" in meta["description"]
    assert meta["title"] == "T"                  # other fields preserved


def test_sync_from_render_missing_files_is_noop(tmp_path, monkeypatch):
    from engine import paths
    monkeypatch.setattr(paths, "artifact_dir", lambda i, f: str(tmp_path / "nope"))
    assert chapters.sync_from_render("x", "long") is False   # never raises


def test_render_and_qc_syncs_chapters_after_render(monkeypatch):
    from engine import run_auto
    from engine.pipeline import chapters as ch
    monkeypatch.setattr(run_auto, "_render_one", lambda i: True)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, f: {"passed": True})
    monkeypatch.setattr(run_auto.q, "update_idea", lambda *a, **k: None)
    seen = {}
    monkeypatch.setattr(ch, "sync_from_render", lambda i, f: seen.setdefault("args", (i, f)) or True)
    run_auto._render_and_qc("zz")
    assert seen["args"] == ("zz", run_auto._OVERNIGHT_FMT)
