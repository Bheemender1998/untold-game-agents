"""
Atmospheric b-roll for the narrated video — Pexels stock video (free API).

INTEGRITY RULE (same as the fact-gate): only atmospheric / symbolic footage —
generic stadiums, crowds, rain, floodlights, textures. NEVER real named people or
event-specific footage (no "Andrés Escobar", no real news clips). Claude writes a
symbolic search query per chapter; we fetch one clip each.

Pexels license: free to use, no attribution required. Get a free key at
https://www.pexels.com/api/ and set PEXELS_API_KEY (env or .env).

Each clip is muted at compose time (the narration is the only audio) and looped if
it is shorter than its chapter. Downloads pick the smallest mp4 >= min_width to stay
light on an M2/8GB.
"""
from __future__ import annotations
import json
import os
import shutil
import urllib.parse
import urllib.request

_SEARCH = "https://api.pexels.com/videos/search"
# Pexels sits behind Cloudflare, which 403s (error 1010) the default python-urllib
# User-Agent. A browser UA is required on BOTH the API call and the CDN download.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def pexels_available() -> bool:
    return bool(os.environ.get("PEXELS_API_KEY"))


def _pick_file(videos: list[dict], min_width: int) -> str | None:
    """Choose the smallest landscape mp4 at >= min_width (light download); fall back to
    any mp4 if none clear the bar."""
    meets, anymp4 = [], []
    for v in videos:
        for f in v.get("video_files", []):
            if f.get("file_type") != "video/mp4" or not f.get("link"):
                continue
            w = f.get("width") or 0
            anymp4.append((w, f["link"]))
            if w >= min_width and (f.get("height") or 0) <= (f.get("width") or 0):  # landscape
                meets.append((w, f["link"]))
    pool = sorted(meets) or sorted(anymp4, reverse=True)   # smallest-that-fits, else biggest available
    return pool[0][1] if pool else None


def fetch_clip(query: str, out_path: str, api_key: str | None = None,
               min_width: int = 1280) -> str | None:
    """Search Pexels for `query` and download one atmospheric clip to out_path.
    Returns out_path, or None on any failure / missing key (caller self-stubs)."""
    api_key = api_key or os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return None
    params = urllib.parse.urlencode({"query": query, "per_page": 8,
                                     "orientation": "landscape", "size": "medium"})
    req = urllib.request.Request(
        f"{_SEARCH}?{params}",
        headers={"Authorization": api_key, "User-Agent": _UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception:
        return None
    link = _pick_file(data.get("videos") or [], min_width)
    if not link:
        return None
    try:
        dl = urllib.request.Request(link, headers={"User-Agent": _UA})
        with urllib.request.urlopen(dl, timeout=60) as r, open(out_path, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception:
        return None
    return out_path


def fetch_clips(queries: list[str], out_dir: str, api_key: str | None = None) -> list[str | None]:
    """One clip per query (chapter), in order. Missing/failed → None (graceful)."""
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for i, q in enumerate(queries):
        path = fetch_clip(q, os.path.join(out_dir, f"bg_{i:02d}.mp4"), api_key=api_key)
        out.append(path)
    return out
