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


def test_fetch_one_repeats_primary_when_broader_query_empty(monkeypatch):
    from engine.video import footage
    def fake_search(query, api_key, portrait=False):
        if query == "basketball game":
            return [{"id": 1, "video_files": [{"file_type": "video/mp4", "link": "a", "width": 1920, "height": 1080}]}]
        return []  # broader "game" query finds nothing
    monkeypatch.setattr(footage, "_search", fake_search)
    monkeypatch.setattr(footage, "_download", lambda link, out: True)
    res = footage._fetch_one("basketball game", "/tmp/x.mp4", "key", 1280, exclude_ids={1})
    assert res is not None and res[1] == 1   # repeats the primary clip rather than returning None


def test_mood_beat_queries_draws_from_the_mood_pool():
    from engine.video import footage
    from engine import config
    qs = footage.mood_beat_queries("somber", 3)
    assert len(qs) == 3
    assert set(qs) <= set(config.MOOD_BROLL_POOL["somber"])


def test_mood_beat_queries_varies_no_immediate_repeat():
    from engine.video import footage
    qs = footage.mood_beat_queries("triumphant", 5)
    assert len(qs) == 5
    assert all(qs[i] != qs[i + 1] for i in range(len(qs) - 1)), f"immediate repeat: {qs}"


def test_mood_beat_queries_cycles_when_n_exceeds_pool():
    from engine.video import footage
    from engine import config
    n = len(config.MOOD_BROLL_POOL["tense"]) + 2
    qs = footage.mood_beat_queries("tense", n)
    assert len(qs) == n  # cycles the pool rather than running out


def test_mood_beat_queries_unknown_mood_falls_back():
    from engine.video import footage
    qs = footage.mood_beat_queries("", 4)         # empty/unknown mood
    assert len(qs) == 4 and all(isinstance(q, str) and q for q in qs)


def test_fetch_photo_returns_credit(monkeypatch, tmp_path):
    import io, json as _json
    from engine.video import footage
    monkeypatch.setenv("PEXELS_API_KEY", "k")

    class _R:
        def __init__(self, payload): self._b = _json.dumps(payload).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._b
    payload = {"photos": [{"photographer": "Ann Lee",
                           "src": {"large2x": "https://img/x.jpg", "original": "https://img/o.jpg"}}]}
    monkeypatch.setattr(footage.urllib.request, "urlopen", lambda req, timeout=30: _R(payload))
    monkeypatch.setattr(footage, "_download", lambda link, out: True)

    out = tmp_path / "subject.png"
    credit = footage.fetch_photo("fifa world cup trophy", str(out))
    assert credit and "Ann Lee" in credit and "Pexels" in credit


def test_fetch_photo_none_without_key(monkeypatch, tmp_path):
    from engine.video import footage
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert footage.fetch_photo("anything", str(tmp_path / "s.png")) is None
