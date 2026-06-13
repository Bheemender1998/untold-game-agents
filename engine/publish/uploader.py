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
import os

# YouTube videoCategoryId 17 = "Sports".
DEFAULT_CATEGORY_ID = "17"


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
    from googleapiclient.http import MediaFileUpload
    from engine.publish.auth import get_service

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
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        progress, response = request.next_chunk()
        if progress:
            print(f"  upload {int(progress.progress() * 100)}%")

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


def append_to_description(video_id: str, suffix: str, *, service=None) -> str:
    """Append `suffix` (e.g. a companion-long link) to a live video's existing
    description, preserving the rest of the snippet. Returns the new description."""
    youtube = _service(service)
    items = youtube.videos().list(part="snippet", id=video_id).execute().get("items", [])
    if not items:
        raise ValueError(f"video {video_id!r} not found or inaccessible")
    snippet = items[0]["snippet"]
    base = (snippet.get("description") or "").rstrip()
    new_desc = (f"{base}\n\n{suffix}" if base else suffix)[:5000]
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
