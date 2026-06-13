from engine.publish import uploader


class _FakeReq:
    def __init__(self, result): self._result = result
    def execute(self): return self._result


class _FakeVideos:
    def __init__(self, snippet):
        self._snippet = snippet
        self.update_body = None
    def list(self, *, part, id):
        return _FakeReq({"items": [{"snippet": dict(self._snippet)}]})
    def update(self, part, body):
        self.update_body = body
        return _FakeReq(body)


class _FakeYouTube:
    def __init__(self, snippet): self._videos = _FakeVideos(snippet)
    def videos(self): return self._videos


def test_update_description_preserves_title_and_category():
    yt = _FakeYouTube({"title": "T", "categoryId": "17", "description": "old"})
    uploader.update_description("vid1", "brand new", service=yt)
    body = yt._videos.update_body
    assert body["id"] == "vid1"
    assert body["snippet"]["description"] == "brand new"
    assert body["snippet"]["title"] == "T"          # not clobbered
    assert body["snippet"]["categoryId"] == "17"    # not clobbered


def test_append_to_description_appends_suffix():
    yt = _FakeYouTube({"title": "T", "categoryId": "17", "description": "watch this"})
    new_desc = uploader.append_to_description("vid1", "Full story: https://youtu.be/LLL",
                                              service=yt)
    assert new_desc.startswith("watch this")
    assert "Full story: https://youtu.be/LLL" in new_desc
    assert yt._videos.update_body["snippet"]["description"] == new_desc


def test_append_to_description_truncates_base_keeping_suffix():
    yt = _FakeYouTube({"title": "T", "categoryId": "17", "description": "x" * 4999})
    new_desc = uploader.append_to_description("vid1", "SUFFIX", service=yt)
    assert len(new_desc) <= 5000
    assert new_desc.endswith("SUFFIX")          # suffix kept intact
    assert new_desc.startswith("x")             # base preserved (truncated to make room)


def test_append_to_description_skips_when_already_present():
    yt = _FakeYouTube({"title": "T", "categoryId": "17",
                       "description": "watch this\n\nFull story: https://youtu.be/LONGvideoID"})
    result = uploader.append_to_description("vid1", "Full story: https://youtu.be/LONGvideoID",
                                            skip_if_contains="https://youtu.be/LONGvideoID", service=yt)
    assert yt._videos.update_body is None       # no update call — already present
    assert "https://youtu.be/LONGvideoID" in result
