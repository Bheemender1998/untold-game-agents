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


def test_lookup_never_raises_on_malformed_pages(monkeypatch):
    # a structurally-wrong-but-parseable payload (null page entry) must not raise
    monkeypatch.setattr(wikipedia.requests, "get", _fake_get({
        "search": {"query": {"search": [{"title": "X"}]}},
        "extract": {"query": {"pages": {"123": None}}},
    }))
    assert wikipedia.lookup("anything") == ""


def test_lookup_trims_to_sentence_budget(monkeypatch):
    long_extract = ". ".join(f"Sentence {i}" for i in range(20)) + "."
    monkeypatch.setattr(wikipedia.requests, "get", _fake_get({
        "search": {"query": {"search": [{"title": "T"}]}},
        "extract": {"query": {"pages": {"1": {"extract": long_extract}}}},
    }))
    out = wikipedia.lookup("q", sentences=3)
    assert out.count("Sentence") == 3


def test_lead_image_returns_url_and_credit(monkeypatch):
    from engine.ideate import wikipedia

    class _Resp:
        def __init__(self, data): self._d = data
        def json(self): return self._d

    calls = {"n": 0}
    def fake_get(url, **kw):
        params = kw.get("params", {})
        if params.get("list") == "search":   # search_title
            return _Resp({"query": {"search": [{"title": "Felipe Massa"}]}})
        if params.get("prop") == "pageimages":
            return _Resp({"query": {"pages": {"1": {
                "original": {"source": "https://up.wikimedia.org/massa.jpg", "width": 2000},
                "pageimage": "Felipe_Massa.jpg"}}}})
        if params.get("prop") == "imageinfo":
            return _Resp({"query": {"pages": {"1": {"imageinfo": [{"extmetadata": {
                "Artist": {"value": "<a href='x'>Jane Doe</a>"},
                "LicenseShortName": {"value": "CC BY 2.0"}}}]}}}})
        return _Resp({})
    monkeypatch.setattr(wikipedia.requests, "get", fake_get)

    out = wikipedia.lead_image("Felipe Massa")
    assert out is not None
    url, credit = out
    assert url == "https://up.wikimedia.org/massa.jpg"
    assert "Jane Doe" in credit and "CC BY 2.0" in credit and "Wikimedia Commons" in credit
    assert "<a" not in credit  # HTML stripped


def test_lead_image_none_when_no_image(monkeypatch):
    from engine.ideate import wikipedia
    class _Resp:
        def __init__(self, d): self._d = d
        def json(self): return self._d
    def fake_get(url, **kw):
        if kw.get("params", {}).get("list") == "search":
            return _Resp({"query": {"search": [{"title": "Obscure Thing"}]}})
        return _Resp({"query": {"pages": {"1": {}}}})  # no 'original'
    monkeypatch.setattr(wikipedia.requests, "get", fake_get)
    assert wikipedia.lead_image("Obscure Thing") is None


def test_lead_image_rejects_svg(monkeypatch):
    from engine.ideate import wikipedia
    class _Resp:
        def __init__(self, d): self._d = d
        def json(self): return self._d
    def fake_get(url, **kw):
        if kw.get("params", {}).get("list") == "search":
            return _Resp({"query": {"search": [{"title": "Logo Page"}]}})
        return _Resp({"query": {"pages": {"1": {"original": {"source": "https://x/logo.svg", "width": 3000}}}}})
    monkeypatch.setattr(wikipedia.requests, "get", fake_get)
    assert wikipedia.lead_image("Logo Page") is None  # SVG → Pillow can't open → reject


def test_lead_image_accepts_tall_narrow_portrait(monkeypatch):
    # Regression: lead portraits are tall+narrow (e.g. Senna 438×584). Gating on width alone
    # wrongly rejected them; gate on the larger side instead.
    from engine.ideate import wikipedia
    class _Resp:
        def __init__(self, d): self._d = d
        def json(self): return self._d
    def fake_get(url, **kw):
        p = kw.get("params", {})
        if p.get("list") == "search":
            return _Resp({"query": {"search": [{"title": "Ayrton Senna"}]}})
        if p.get("prop") == "pageimages":
            return _Resp({"query": {"pages": {"1": {
                "original": {"source": "https://up/senna.jpg", "width": 438, "height": 584},
                "pageimage": "Senna.jpg"}}}})
        return _Resp({"query": {"pages": {"1": {"imageinfo": [{"extmetadata": {}}]}}}})
    monkeypatch.setattr(wikipedia.requests, "get", fake_get)
    out = wikipedia.lead_image("Ayrton Senna")
    assert out is not None and out[0] == "https://up/senna.jpg"  # 584 tall ≥ min_dim → accepted
