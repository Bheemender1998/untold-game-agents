"""Wikipedia lookup — mocked, no network. Verifies parsing + the never-raises contract."""
import requests

from engine.ideate import wikipedia


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _fake_get(payload_by_list):
    """Return a requests.get stub that answers search vs extract by the 'list'/'prop' param."""
    def get(url, timeout=None, headers=None, params=None):
        if params.get("list") == "search":
            return _Resp(payload_by_list["search"])
        return _Resp(payload_by_list["extract"])
    return get


def test_lookup_returns_titled_extract(monkeypatch):
    monkeypatch.setattr(wikipedia.requests, "get", _fake_get({
        "search": {"query": {"search": [{"title": "Eden Gardens"}]}},
        "extract": {"query": {"pages": {"123": {
            "extract": "Eden Gardens is a cricket ground in Kolkata. It opened in 1864. "
                       "It is the largest in India."}}}},
    }))
    out = wikipedia.lookup("Eden Gardens 2001 Test")
    assert out.startswith("[Wikipedia: Eden Gardens]")
    assert "Kolkata" in out


def test_lookup_empty_on_no_hits(monkeypatch):
    monkeypatch.setattr(wikipedia.requests, "get", _fake_get({
        "search": {"query": {"search": []}},
        "extract": {},
    }))
    assert wikipedia.lookup("nonexistent gibberish xyzzy") == ""


def test_lookup_never_raises_on_network_error(monkeypatch):
    def boom(*a, **k):
        raise requests.RequestException("network down")
    monkeypatch.setattr(wikipedia.requests, "get", boom)
    assert wikipedia.lookup("anything") == ""  # degrades to empty, no exception


def test_lookup_trims_to_sentence_budget(monkeypatch):
    long_extract = ". ".join(f"Sentence {i}" for i in range(20)) + "."
    monkeypatch.setattr(wikipedia.requests, "get", _fake_get({
        "search": {"query": {"search": [{"title": "T"}]}},
        "extract": {"query": {"pages": {"1": {"extract": long_extract}}}},
    }))
    out = wikipedia.lookup("q", sentences=3)
    assert out.count("Sentence") == 3
