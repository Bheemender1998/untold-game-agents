from engine.video import footage


def test_best_file_portrait_prefers_tall_clip():
    video = {"video_files": [
        {"file_type": "video/mp4", "link": "land", "width": 1920, "height": 1080},
        {"file_type": "video/mp4", "link": "port", "width": 1080, "height": 1920},
    ]}
    assert footage._best_file(video, 1280, portrait=True) == "port"
    assert footage._best_file(video, 1280, portrait=False) == "land"


def test_best_file_portrait_falls_back_when_none_tall_enough():
    video = {"video_files": [
        {"file_type": "video/mp4", "link": "small", "width": 240, "height": 320},
    ]}
    # below min height → falls back to "any file" pool (never returns None when a file exists)
    assert footage._best_file(video, 1280, portrait=True) == "small"


def test_sport_query_prepends_missing_keyword():
    assert footage._sport_query("race track aerial", "F1") == "formula 1 race track aerial"
    assert footage._sport_query("ball net", "Soccer") == "soccer ball net"


def test_sport_query_noop_when_keyword_present():
    assert footage._sport_query("formula 1 pit lane", "F1") == "formula 1 pit lane"
    assert footage._sport_query("Formula 1 grid", "F1") == "Formula 1 grid"  # case-insensitive


def test_sport_query_unknown_sport_uses_raw_lowercased():
    assert footage._sport_query("court", "Pickleball") == "pickleball court"


def test_sport_query_falsy_sport_unchanged():
    assert footage._sport_query("race track", None) == "race track"
    assert footage._sport_query("race track", "") == "race track"


def test_fetch_one_prefers_unused_within_video(monkeypatch):
    from engine.video import footage
    fake = [{"id": 1, "video_files": [{"file_type": "video/mp4", "link": "a", "width": 1920, "height": 1080}]},
            {"id": 2, "video_files": [{"file_type": "video/mp4", "link": "b", "width": 1920, "height": 1080}]},
            {"id": 3, "video_files": [{"file_type": "video/mp4", "link": "c", "width": 1920, "height": 1080}]}]
    monkeypatch.setattr(footage, "_search", lambda *a, **k: fake)
    monkeypatch.setattr(footage, "_download", lambda link, out: True)
    res = footage._fetch_one("q", "/tmp/x.mp4", "key", 1280, exclude_ids={1, 2})
    assert res is not None and res[1] == 3


def test_fetch_one_repeats_only_when_no_unused_left(monkeypatch):
    from engine.video import footage
    fake = [{"id": 1, "video_files": [{"file_type": "video/mp4", "link": "a", "width": 1920, "height": 1080}]}]
    monkeypatch.setattr(footage, "_search", lambda *a, **k: fake)
    monkeypatch.setattr(footage, "_download", lambda link, out: True)
    res = footage._fetch_one("q", "/tmp/x.mp4", "key", 1280, exclude_ids={1})
    assert res is not None and res[1] == 1


def test_fetch_one_broadens_query_before_repeating(monkeypatch):
    from engine.video import footage
    calls = []
    def fake_search(query, api_key, portrait=False):
        calls.append(query)
        if query == "basketball game":
            # primary query: only id 1, which is already used
            return [{"id": 1, "video_files": [{"file_type": "video/mp4", "link": "a", "width": 1920, "height": 1080}]}]
        # broader "game" query surfaces a fresh, unused clip
        return [{"id": 9, "video_files": [{"file_type": "video/mp4", "link": "z", "width": 1920, "height": 1080}]}]
    monkeypatch.setattr(footage, "_search", fake_search)
    monkeypatch.setattr(footage, "_download", lambda link, out: True)
    res = footage._fetch_one("basketball game", "/tmp/x.mp4", "key", 1280, exclude_ids={1})
    assert calls == ["basketball game", "game"]   # broadened to the second word before repeating
    assert res is not None and res[1] == 9         # picked the fresh broader clip, not a repeat of 1
