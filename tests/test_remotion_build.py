from engine.video import remotion_build, music


def _patch_heavy(monkeypatch):
    """Neutralize the network/heavy helpers so we test only the music wiring."""
    monkeypatch.setattr(remotion_build._tts, "script_to_narration_text", lambda md: "word word word")
    monkeypatch.setattr(remotion_build._captions, "estimate_word_timings",
                        lambda text, dur: [{"text": "word", "startMs": 0, "endMs": 500}])
    monkeypatch.setattr(remotion_build._compose, "build_section_headlines", lambda idea, md: [])
    monkeypatch.setattr(remotion_build._compose, "assign_headline_times", lambda s, w, d, n: [])
    monkeypatch.setattr(remotion_build._footage, "fetch_clips",
                        lambda queries, vd, portrait=False, sport=None: [])


def test_build_props_adds_music_for_short(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props",
                        lambda idea, *a, **k: ({"musicSrc": "x.mp3", "musicVolume": 0.12},
                                               "/lib/x.mp3", "Music by X"))
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, assets, credit = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0, portrait=True)
    assert props["musicSrc"] == "x.mp3" and props["musicVolume"] == 0.12
    assert "/lib/x.mp3" in assets
    assert credit == "Music by X"


def test_build_props_no_music_for_longform(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    called = []
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: called.append(1) or ({}, None, ""))
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, assets, credit = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0, portrait=False)
    assert "musicSrc" not in props and credit == ""
    assert called == []   # long-form never asks for music
