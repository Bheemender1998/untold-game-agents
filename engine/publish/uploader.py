"""
Upload a finished video + metadata to YouTube via the Data API v3.

This is real (resumable videos.insert), but it needs two things that don't exist
yet in the pipeline: a rendered video file, and the OAuth client (Track A setup).
Until then it's the ready-to-use publishing infra. CLI for manual testing:

    python3 -m engine.publish.uploader --video out.mp4 \
        --title "The Goal That Got Him Killed" --description "..." \
        --tags "Andrés Escobar,1994 World Cup" --privacy private \
        --publish-at 2026-07-01T16:00:00Z
"""
from __future__ import annotations
import http.client
import os
import socket
import ssl
import time

# YouTube videoCategoryId 17 = "Sports".
DEFAULT_CATEGORY_ID = "17"

# Transient connection failures that should resume a resumable upload, not abort it.
# BrokenPipeError/ConnectionReset* are subclasses of ConnectionError (and the OSError
# errno cases EPIPE/ECONNRESET auto-promote to those subclasses), so they're covered
# here; large multi-GB uploads regularly hit one of these mid-stream on a flaky link.
# httplib2.ServerNotFoundError (a transient DNS blip) is added at call time — it isn't
# an OSError subclass, so it would otherwise escape this set and abort the upload.
_RETRYABLE_UPLOAD_ERRORS = (
    ConnectionError, TimeoutError, ssl.SSLError, socket.timeout,
    http.client.IncompleteRead, http.client.RemoteDisconnected,
    http.client.BadStatusLine,
)
# Cap consecutive failures (a genuinely stuck upload) AND total resumes across the whole
# upload (a connection that flaps once per chunk would never trip the consecutive cap,
# since each landed chunk resets the streak — so bound the aggregate too).
_MAX_UPLOAD_RESUMES = 12
_MAX_TOTAL_RESUMES = 40


def _safe_tags(tags: list[str] | None) -> list[str]:
    """YouTube rejects a tag set whose total length exceeds 500 chars (multi-word
    tags are quoted, adding 2 chars each) and tags containing < or >. Strip the
    bad chars and keep adding tags until a safe ~480-char budget is reached."""
    out, total = [], 0
    for t in tags or []:
        t = t.replace("<", "").replace(">", "").strip()
        if not t:
            continue
        cost = len(t) + (2 if " " in t else 0) + 1  # quotes for multi-word + separator
        if total + cost > 480:
            break
        out.append(t)
        total += cost
    return out


def upload(
    video_path: str,
    *,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    category_id: str = DEFAULT_CATEGORY_ID,
    privacy: str = "private",            # private | unlisted | public
    publish_at: str | None = None,       # RFC3339 UTC, e.g. 2026-07-01T16:00:00Z
    thumbnail_path: str | None = None,
) -> str:
    """Upload `video_path` with metadata; return the new YouTube video id.

    If `publish_at` is set, privacy is forced to 'private' and YouTube releases
    the video automatically at that time (scheduled publish).
    """
    import httplib2
    from googleapiclient.http import MediaFileUpload
    from engine.publish.auth import get_service

    # ServerNotFoundError lives in httplib2 (a google-api-python-client dep), imported
    # lazily here so this module stays importable without the google stack installed.
    retryable_errors = _RETRYABLE_UPLOAD_ERRORS + (httplib2.ServerNotFoundError,)

    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": _safe_tags(tags),
            "categoryId": category_id,
        },
        "status": status,
    }

    youtube = get_service()
    # Chunked (not -1/single-shot) so next_chunk() reports progress — a single-shot upload
    # prints nothing for minutes and looks dead, which invites a duplicate re-run. 10 MiB is
    # a multiple of the required 256 KiB and keeps each chunk's exposure to a mid-stream
    # reset small, so a resume re-sends little.
    media = MediaFileUpload(video_path, chunksize=10 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    # Resumable upload: next_chunk(num_retries=...) retries transient HTTP/socket errors
    # per chunk with backoff. The outer loop catches connection resets that escape that
    # (e.g. BrokenPipeError) and resumes the SAME request from the last committed byte —
    # without it, one mid-stream reset aborts a multi-GB upload from zero.
    response = None
    resumes = 0          # consecutive failures since the last landed chunk
    total_resumes = 0    # aggregate failures across the whole upload
    while response is None:
        try:
            progress, response = request.next_chunk(num_retries=5)
            if progress:
                print(f"  upload {int(progress.progress() * 100)}%")
            resumes = 0  # a chunk landed — reset the consecutive streak
        except retryable_errors as e:
            resumes += 1
            total_resumes += 1
            if resumes > _MAX_UPLOAD_RESUMES or total_resumes > _MAX_TOTAL_RESUMES:
                raise
            backoff = min(2 ** resumes, 60)
            print(f"  ⚠ upload interrupted ({type(e).__name__}: {e}) — "
                  f"resume {resumes}/{_MAX_UPLOAD_RESUMES} "
                  f"(total {total_resumes}/{_MAX_TOTAL_RESUMES}) in {backoff}s")
            time.sleep(backoff)

    video_id = response["id"]
    print(f"  ✓ uploaded: https://youtu.be/{video_id}")

    if thumbnail_path and os.path.exists(thumbnail_path):
        youtube.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(thumbnail_path)
        ).execute()
        print("  ✓ thumbnail set")

    return video_id


def _service(service=None):
    if service is not None:
        return service
    from engine.publish.auth import get_service
    return get_service()


def update_description(video_id: str, new_description: str, *, service=None) -> str:
    """Replace a live video's description. videos.update needs the FULL snippet, so
    we list the current snippet, swap only the description, and send it all back —
    sending description alone would wipe title/categoryId. Returns the new description."""
    youtube = _service(service)
    items = youtube.videos().list(part="snippet", id=video_id).execute().get("items", [])
    if not items:
        raise ValueError(f"video {video_id!r} not found or inaccessible")
    snippet = items[0]["snippet"]
    snippet["description"] = new_description[:5000]
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    return snippet["description"]


def append_to_description(video_id: str, suffix: str, *, skip_if_contains=None, service=None) -> str:
    """Append `suffix` (e.g. a companion-long link) to a live video's existing
    description, preserving the rest of the snippet. The suffix is ALWAYS kept intact —
    if base+suffix would exceed 5000 chars, the existing description is truncated to make
    room (the backlink is the point of the call). If `skip_if_contains` is already present
    in the live description, this is a no-op (returns the current description) so re-running
    a backlink can't duplicate it even if a prior run crashed before its flag was written."""
    youtube = _service(service)
    items = youtube.videos().list(part="snippet", id=video_id).execute().get("items", [])
    if not items:
        raise ValueError(f"video {video_id!r} not found or inaccessible")
    snippet = items[0]["snippet"]
    base = (snippet.get("description") or "").rstrip()
    if skip_if_contains is not None and skip_if_contains in base:
        return base  # already present — idempotent no-op against live state
    if not base:
        new_desc = suffix[:5000]
    else:
        sep = "\n\n"
        room = 5000 - len(sep) - len(suffix)
        if room < 0:
            raise ValueError(
                f"suffix ({len(suffix)} chars) too long to append within the 5000-char limit")
        new_desc = f"{base[:room].rstrip()}{sep}{suffix}"
    snippet["description"] = new_desc
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    return new_desc


def _cli() -> None:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Upload a video to YouTube (Data API v3)")
    ap.add_argument("--video", required=True)
    ap.add_argument("--metadata", help="produced/<id>/metadata.json — fills title/description/tags")
    ap.add_argument("--title", default=None, help="overrides metadata title")
    ap.add_argument("--description", default=None, help="overrides metadata description")
    ap.add_argument("--tags", default=None, help="comma-separated; overrides metadata tags")
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--publish-at", default=None, help="RFC3339 UTC, e.g. 2026-07-01T16:00:00Z")
    ap.add_argument("--thumbnail", default=None)
    a = ap.parse_args()

    meta = {}
    if a.metadata:
        with open(a.metadata) as f:
            meta = json.load(f)

    title = a.title or meta.get("title")
    if not title:
        ap.error("provide --title or --metadata pointing at a metadata.json with a title")
    description = a.description if a.description is not None else meta.get("description", "")
    tags = ([t.strip() for t in a.tags.split(",") if t.strip()]
            if a.tags is not None else meta.get("tags", []))

    upload(
        a.video, title=title, description=description, tags=tags,
        privacy=a.privacy, publish_at=a.publish_at, thumbnail_path=a.thumbnail,
    )


if __name__ == "__main__":
    _cli()
