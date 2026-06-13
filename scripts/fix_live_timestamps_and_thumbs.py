"""One-off retro-fix for already-published videos:
  (1) rebuild each LONG's description chapter timestamps from the rendered props.json
      (real per-chapter startMs) — the LLM-estimated times were wildly wrong; and
  (2) set the custom thumbnail on every published long/short that has one.

Idempotent + re-runnable (only touches videos that are already published). Run from
repo root: PYTHONPATH=. python3 scripts/fix_live_timestamps_and_thumbs.py
"""
import json
import os
import re
import string

from engine import paths, queue_manager as q
from engine.publish import uploader
from engine.publish.auth import get_service

IDS = ["f058733a", "4ef3fc89", "648d57e6"]
_TS = re.compile(r"^\s*\d{1,2}:\d{2}\b")     # a chapter line starts with MM:SS (any separator)


def _mmss(ms: int) -> str:
    s = round(ms / 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


_SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or",
          "the", "to", "vs", "with", "from", "into", "over"}


def _titlecase(h: str) -> str:
    """On-screen headlines are UPPERCASE; present as proper Title Case — small words
    (and/of/the/in…) stay lowercase unless first, so it reads clean not SHOUTY."""
    words = (h or "").strip().split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        out.append(lw if (i and lw in _SMALL) else (w[:1].upper() + w[1:].lower()))
    return " ".join(out)


def _rebuilt_description(idea_id: str) -> str | None:
    """Replace the description's chapter block with one built from the rendered props.json
    (real per-chapter startMs + on-screen headline). The LLM's produce-time chapters are
    disconnected from the actual render (wrong count AND wrong times), so we rebuild from
    the authoritative render output. Returns None if inputs are missing."""
    meta_path = os.path.join(paths.artifact_dir(idea_id, "long"), "metadata.json")
    props_path = os.path.join(paths.artifact_dir(idea_id, "long"), "video", "props.json")
    if not (os.path.exists(meta_path) and os.path.exists(props_path)):
        print(f"  · [{idea_id}] missing metadata/props — skip description"); return None
    desc = json.load(open(meta_path)).get("description", "")
    chapters = json.load(open(props_path)).get("chapters", [])
    if not chapters:
        print(f"  · [{idea_id}] no props chapters — skip description"); return None
    lines = desc.splitlines()
    # Find the longest contiguous run of timestamp lines = the chapters block (a stray
    # timestamp in prose can't be longer than the real block).
    runs, i = [], 0
    while i < len(lines):
        if _TS.match(lines[i]):
            j = i
            while j < len(lines) and _TS.match(lines[j]):
                j += 1
            runs.append((i, j)); i = j
        else:
            i += 1
    if not runs:
        print(f"  · [{idea_id}] no chapter block found in description — skip"); return None
    start, end = max(runs, key=lambda r: r[1] - r[0])
    block = [f"{_mmss(c['startMs'])} — {_titlecase(c['headline'])}" for c in chapters]
    lines[start:end] = block
    return "\n".join(lines)


def main() -> int:
    svc = get_service()
    for idea_id in IDS:
        d = q.get_by_id(idea_id) or {}
        print(f"\n▶ [{idea_id}]")
        # (1) LONG description timestamp fix (only if the long is published)
        long_url = d.get("long_youtube_url")
        if long_url:
            vid = long_url.rsplit("/", 1)[-1]
            new_desc = _rebuilt_description(idea_id)
            if new_desc is not None:
                uploader.update_description(vid, new_desc, service=svc)
                # keep metadata.json consistent for future reference
                mp = os.path.join(paths.artifact_dir(idea_id, "long"), "metadata.json")
                m = json.load(open(mp)); m["description"] = new_desc
                json.dump(m, open(mp, "w"), indent=2, ensure_ascii=False)
                print(f"  ✓ long description timestamps fixed → {vid}")
        else:
            print("  · long not published yet — skip")
        # (2) thumbnails for published long + short
        for fmt, url_key in (("long", "long_youtube_url"), ("short", "short_youtube_url")):
            url = d.get(url_key)
            thumb = paths.thumbnail_path(idea_id, fmt)
            if not url:
                continue
            if not os.path.exists(thumb):
                print(f"  · [{fmt}] no thumbnail.jpg — skip"); continue
            from googleapiclient.http import MediaFileUpload
            try:
                svc.thumbnails().set(videoId=url.rsplit("/", 1)[-1],
                                     media_body=MediaFileUpload(thumb)).execute()
                print(f"  ✓ [{fmt}] thumbnail set → {url.rsplit('/', 1)[-1]}")
            except Exception as e:
                print(f"  ! [{fmt}] thumbnail set failed: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
