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
