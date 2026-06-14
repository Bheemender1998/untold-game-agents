import math

from engine.video import remotion_build, music


def test_beat_track_covers_narration_contiguously():
    beats = remotion_build.beat_track(10_000, 2.5)   # 10s narration, 2.5s beats
    assert len(beats) == 4
    assert beats[0]["startMs"] == 0
    # contiguous, non-overlapping
    for a, b in zip(beats, beats[1:]):
        assert a["endMs"] == b["startMs"]
    # last beat reaches the end of the narration
    assert beats[-1]["endMs"] == 10_000


def test_beat_track_rounds_up_partial_final_beat():
    beats = remotion_build.beat_track(9_000, 2.5)     # 9 / 2.5 = 3.6 → 4 beats
    assert len(beats) == math.ceil(9_000 / 2_500)
    assert beats[-1]["endMs"] == 9_000                # clamped to narration end


def test_beat_track_long_cadence_is_coarser():
    short_beats = remotion_build.beat_track(60_000, 2.5)
    long_beats = remotion_build.beat_track(60_000, 7.0)
    assert len(short_beats) > len(long_beats)         # short cuts more often


def _patch_heavy(monkeypatch):
    """Neutralize the network/heavy helpers so we test only the music wiring."""
    monkeypatch.setattr(remotion_build._tts, "script_to_narration_text", lambda md: "word word word")
    monkeypatch.setattr(remotion_build._captions, "estimate_word_timings",
                        lambda text, dur: [{"text": "word", "startMs": 0, "endMs": 500}])
    monkeypatch.setattr(remotion_build._compose, "build_section_headlines", lambda idea, md: [])
    monkeypatch.setattr(remotion_build._compose, "assign_headline_times", lambda s, w, d, n: [])
    monkeypatch.setattr(remotion_build._footage, "fetch_clips",
                        lambda queries, vd, portrait=False, sport=None: [])


def test_build_props_digitizes_captions_but_keeps_raw_words_for_anchors(monkeypatch, tmp_path):
    """Captions must show digitized text ("1984"), but assign_headline_times must receive
    the original raw whisper tokens so year-anchored chapter titles can still match."""
    captured = {}

    def _capture_assign(sections, words, total_dur, narration):
        captured["words"] = list(words) if words else words
        return []

    monkeypatch.setattr(remotion_build._tts, "script_to_narration_text", lambda md: "narration text")
    monkeypatch.setattr(remotion_build._compose, "build_section_headlines", lambda idea, md: [])
    monkeypatch.setattr(remotion_build._compose, "assign_headline_times", _capture_assign)
    monkeypatch.setattr(remotion_build._footage, "fetch_clips",
                        lambda queries, vd, portrait=False, sport=None: [])
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))

    words = [
        {"word": "In",          "start": 0.0, "end": 0.2},
        {"word": "nineteen",    "start": 0.2, "end": 0.6},
        {"word": "eighty-four", "start": 0.6, "end": 1.1},
        {"word": "at",          "start": 1.1, "end": 1.3},
    ]
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, assets, credit = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", words, 1.3)

    # (a) Captions must have the digitized token "1984", not the spelled form.
    caption_texts = [t["text"] for t in props["captions"]]
    assert "1984" in caption_texts, (
        f"Expected '1984' in caption tokens (digitized for display), got: {caption_texts}")

    # (b) assign_headline_times must have received the raw (un-digitized) tokens.
    assert "words" in captured, "assign_headline_times was never called with a words argument"
    raw_words = [w["word"] for w in captured["words"]]
    assert "nineteen" in raw_words, (
        f"Expected raw token 'nineteen' in words passed to assign_headline_times, got: {raw_words}")
    assert "eighty-four" in raw_words, (
        f"Expected raw token 'eighty-four' in words passed to assign_headline_times, got: {raw_words}")


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


def test_build_props_no_music_when_track_missing(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, assets, credit = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0, portrait=False)
    assert "musicSrc" not in props and credit == ""


def test_build_props_adds_music_for_longform(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props",
                        lambda i, *a, **k: ({"musicSrc": "m.mp3", "musicVolume": 0.12}, "/lib/m.mp3", "Music"))
    idea = {"id": "i", "pillar": "verdict_revisited", "title_variants": ["T"]}
    props, assets, credit = remotion_build.build_props(
        idea, "# s\nb", str(tmp_path), "n.wav", None, 10.0, portrait=False)
    assert props["musicSrc"] == "m.mp3" and "/lib/m.mp3" in assets and credit == "Music"


def test_build_props_emits_bbeats_from_mood_pool(tmp_path, monkeypatch):
    from engine.video import remotion_build, footage, music
    from engine import config

    # Neutralize heavy/network helpers; capture the queries footage receives.
    captured = {}
    def _fake_fetch(queries, vd, portrait=False, sport=None):
        captured["queries"] = list(queries)
        captured["sport"] = sport
        return [f"bg_{i:02d}.mp4" for i in range(len(queries))]   # every beat gets a clip

    monkeypatch.setattr(remotion_build._tts, "script_to_narration_text", lambda md: "w w w")
    monkeypatch.setattr(remotion_build._captions, "estimate_word_timings",
                        lambda text, dur: [{"text": "w", "startMs": 0, "endMs": 500}])
    monkeypatch.setattr(remotion_build._compose, "build_section_headlines", lambda idea, md: [])
    monkeypatch.setattr(remotion_build._compose, "assign_headline_times", lambda s, w, d, n: [])
    monkeypatch.setattr(remotion_build._footage, "fetch_clips", _fake_fetch)
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))

    idea = {"id": "i1", "mood": "somber", "pillar": "hidden_story", "title_variants": ["T"],
            "sport": "Soccer"}
    props, assets, credit = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0, broll_beat_s=2.5)

    # 10s / 2.5s = 4 beats → 4 bBeats, each with a src + contiguous timing + alternating zoom.
    beats = props["bBeats"]
    assert len(beats) == 4
    assert [b["zoomDir"] for b in beats] == ["in", "out", "in", "out"]
    assert all(b["src"] for b in beats)
    assert beats[0]["startMs"] == 0 and beats[-1]["endMs"] == 10_000
    # queries came from the somber mood pool, generic (sport not biased in)
    assert set(captured["queries"]) <= set(config.MOOD_BROLL_POOL["somber"])
    assert captured["sport"] is None


def test_build_props_bbeats_mood_falls_back_to_pillar(tmp_path, monkeypatch):
    from engine.video import remotion_build, footage, music
    from engine import config

    monkeypatch.setattr(remotion_build._tts, "script_to_narration_text", lambda md: "w")
    monkeypatch.setattr(remotion_build._captions, "estimate_word_timings",
                        lambda text, dur: [{"text": "w", "startMs": 0, "endMs": 500}])
    monkeypatch.setattr(remotion_build._compose, "build_section_headlines", lambda idea, md: [])
    monkeypatch.setattr(remotion_build._compose, "assign_headline_times", lambda s, w, d, n: [])
    grabbed = {}
    def _fake_fetch(queries, vd, portrait=False, sport=None):
        grabbed["queries"] = list(queries)
        return [None for _ in queries]      # no clips available → graceful
    monkeypatch.setattr(remotion_build._footage, "fetch_clips", _fake_fetch)
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))

    # No idea["mood"] → derive from pillar via tts.mood_for_pillar.
    pillar = next(iter(config.PILLAR_MOOD))
    expected_mood = config.PILLAR_MOOD[pillar]
    idea = {"id": "i2", "pillar": pillar, "title_variants": ["T"]}
    props, _, _ = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 5.0, broll_beat_s=7.0)

    assert set(grabbed["queries"]) <= set(config.MOOD_BROLL_POOL[expected_mood])
    # beats with no clip omit src but keep timing (gradient shows through, never crashes)
    assert props["bBeats"][0]["src"] is None


def test_build_props_sets_end_hold_for_short(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, _, _ = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0,
        portrait=True, end_hold_ms=1000)
    assert props["endHoldMs"] == 1000


def test_build_props_end_hold_defaults_to_zero(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props", lambda *a, **k: ({}, None, ""))
    idea = {"id": "i1", "mood": "tense", "title_variants": ["T"]}
    props, _, _ = remotion_build.build_props(
        idea, "# s\nbody", str(tmp_path), "narration.wav", None, 10.0)
    assert props["endHoldMs"] == 0
