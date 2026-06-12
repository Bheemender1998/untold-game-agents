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
