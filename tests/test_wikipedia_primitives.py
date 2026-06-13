from engine.ideate import wikipedia


class _Resp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


def test_search_title_returns_top_hit(monkeypatch):
    monkeypatch.setattr(wikipedia.requests, "get",
        lambda *a, **k: _Resp({"query": {"search": [{"title": "1998 FIFA World Cup Group F"}]}}))
    assert wikipedia.search_title("Iran USA 1998 Mahdavikia goal") == "1998 FIFA World Cup Group F"


def test_search_title_none_on_no_hits(monkeypatch):
    monkeypatch.setattr(wikipedia.requests, "get", lambda *a, **k: _Resp({"query": {"search": []}}))
    assert wikipedia.search_title("zzz nonexistent") is None


def test_search_title_none_on_error(monkeypatch):
    def boom(*a, **k): raise wikipedia.requests.RequestException("down")
    monkeypatch.setattr(wikipedia.requests, "get", boom)
    assert wikipedia.search_title("anything") is None


def test_extract_returns_full_plaintext(monkeypatch):
    payload = {"query": {"pages": {"123": {"extract": "Full body. Many sentences. Deep facts."}}}}
    monkeypatch.setattr(wikipedia.requests, "get", lambda *a, **k: _Resp(payload))
    out = wikipedia.extract("Some Title")
    assert "Deep facts." in out


def test_extract_empty_on_error(monkeypatch):
    def boom(*a, **k): raise wikipedia.requests.RequestException("down")
    monkeypatch.setattr(wikipedia.requests, "get", boom)
    assert wikipedia.extract("Some Title") == ""
