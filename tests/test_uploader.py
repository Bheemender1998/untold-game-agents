import pytest

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


# ---- resumable-upload retry loop ----------------------------------------------------------

class _FakeProgress:
    def __init__(self, frac): self._frac = frac
    def progress(self): return self._frac


class _FakeUploadRequest:
    """Yields a scripted sequence of next_chunk() outcomes: an Exception instance is
    raised, a (progress, response) tuple is returned."""
    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    def next_chunk(self, num_retries=0):
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _FakeInsertYouTube:
    def __init__(self, request): self._request = request
    def videos(self):
        request = self._request
        class _V:
            def insert(self, *, part, body, media_body): return request
        return _V()


def _patch_upload_env(monkeypatch, request, tmp_path):
    """Stub the lazy googleapiclient + auth imports so upload() drives our fake request,
    and neutralise real backoff sleeps."""
    import googleapiclient.http as gh
    import engine.publish.auth as auth
    monkeypatch.setattr(gh, "MediaFileUpload", lambda *a, **k: object())
    monkeypatch.setattr(auth, "get_service", lambda: _FakeInsertYouTube(request))
    monkeypatch.setattr(uploader.time, "sleep", lambda *_: None)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    return str(video)


def test_upload_resumes_after_broken_pipe(monkeypatch, tmp_path):
    # A mid-stream BrokenPipeError must resume the same request, not abort the upload.
    req = _FakeUploadRequest([
        BrokenPipeError("reset"),
        (_FakeProgress(0.5), None),
        (None, {"id": "VID123"}),
    ])
    video = _patch_upload_env(monkeypatch, req, tmp_path)
    assert uploader.upload(video, title="T") == "VID123"
    assert req.calls == 3


def test_upload_retries_server_not_found(monkeypatch, tmp_path):
    # ServerNotFoundError isn't an OSError subclass; the lazy-added entry must catch it.
    import httplib2
    req = _FakeUploadRequest([
        httplib2.ServerNotFoundError("dns blip"),
        (None, {"id": "VID9"}),
    ])
    video = _patch_upload_env(monkeypatch, req, tmp_path)
    assert uploader.upload(video, title="T") == "VID9"


def test_upload_reraises_after_consecutive_cap(monkeypatch, tmp_path):
    # No landed chunk ever resets the streak → the consecutive cap must re-raise.
    req = _FakeUploadRequest([BrokenPipeError("x")] * (uploader._MAX_UPLOAD_RESUMES + 1))
    video = _patch_upload_env(monkeypatch, req, tmp_path)
    with pytest.raises(BrokenPipeError):
        uploader.upload(video, title="T")


def test_upload_reraises_after_total_cap(monkeypatch, tmp_path):
    # A connection that lands one chunk between every failure never trips the consecutive
    # cap, so the aggregate cap must stop it. Interleave failure/success past the total cap.
    script = []
    for _ in range(uploader._MAX_TOTAL_RESUMES + 1):
        script.append(BrokenPipeError("flap"))
        script.append((_FakeProgress(0.1), None))
    req = _FakeUploadRequest(script)
    video = _patch_upload_env(monkeypatch, req, tmp_path)
    with pytest.raises(BrokenPipeError):
        uploader.upload(video, title="T")
