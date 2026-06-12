"""
Atmospheric b-roll for the narrated video — Pexels stock video (free API).

INTEGRITY RULE (same as the fact-gate): only atmospheric / symbolic footage —
generic stadiums, crowds, rain, floodlights, textures. NEVER real named people or
event-specific footage (no "Andrés Escobar", no real news clips). Claude writes a
symbolic search query per chapter; we fetch one clip each.

Pexels license: free to use, no attribution required. Get a free key at
https://www.pexels.com/api/ and set PEXELS_API_KEY (env or .env).

Variety: a clip is chosen at RANDOM among the eligible search results, and every
Pexels video id we use is remembered (used_clips.json) so footage never repeats
across videos. Each clip is muted at compose time and looped if shorter than its
chapter.
"""
from __future__ import annotations
import json
import os
import random
import shutil
import urllib.parse
import urllib.request

_SEARCH = "https://api.pexels.com/videos/search"
# Pexels sits behind Cloudflare, which 403s (error 1010) the default python-urllib
# User-Agent. A browser UA is required on BOTH the API call and the CDN download.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# Cross-video dedup ledger of Pexels video ids we've already used.
_USED_PATH = os.path.join(os.path.dirname(__file__), "used_clips.json")


def pexels_available() -> bool:
    return bool(os.environ.get("PEXELS_API_KEY"))


def _best_file(video: dict, min_width: int, portrait: bool = False) -> str | None:
    """Smallest eligible mp4 >= min_width for one video (light download); else any mp4.

    landscape (portrait=False): files where height <= width and width >= min_width,
      ranked by width ascending (smallest wide-enough).
    portrait  (portrait=True):  files where height >= width and height >= min_width,
      ranked by height ascending (smallest tall-enough).
    Fallback in both cases: any mp4, sorted largest-dimension first.
    """
    files, meets = [], []
    for f in video.get("video_files", []):
        if f.get("file_type") != "video/mp4" or not f.get("link"):
            continue
        w = f.get("width") or 0
        h = f.get("height") or 0
        if portrait:
            files.append((h, f["link"]))
            if h >= w and h >= min_width:  # tall and tall-enough
                meets.append((h, f["link"]))
        else:
            files.append((w, f["link"]))
            if w >= min_width and h <= w:  # landscape
                meets.append((w, f["link"]))
    pool = sorted(meets) or sorted(files, reverse=True)
    return pool[0][1] if pool else None


def _search(query: str, api_key: str, portrait: bool = False) -> list[dict]:
    orientation = "portrait" if portrait else "landscape"
    params = urllib.parse.urlencode({"query": query, "per_page": 12,
                                     "orientation": orientation, "size": "medium"})
    req = urllib.request.Request(
        f"{_SEARCH}?{params}",
        headers={"Authorization": api_key, "User-Agent": _UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("videos") or []
    except Exception:
        return []


def _download(link: str, out_path: str) -> bool:
    try:
        dl = urllib.request.Request(link, headers={"User-Agent": _UA})
        with urllib.request.urlopen(dl, timeout=60) as r, open(out_path, "wb") as f:
            shutil.copyfileobj(r, f)
        return True
    except Exception:
        return False


def _fetch_one(query: str, out_path: str, api_key: str, min_width: int,
               exclude_ids: set, portrait: bool = False) -> tuple[str, int] | None:
    """Pick a RANDOM eligible (unused) clip for the query and download it.
    Returns (out_path, video_id) or None."""
    videos = _search(query, api_key, portrait=portrait)
    eligible = [v for v in videos if v.get("id") not in exclude_ids
                and _best_file(v, min_width, portrait=portrait)]
    if not eligible:   # everything seen already → allow a repeat rather than a blank chapter
        eligible = [v for v in videos if _best_file(v, min_width, portrait=portrait)]
    if not eligible:
        return None
    v = random.choice(eligible)
    link = _best_file(v, min_width, portrait=portrait)
    if not link or not _download(link, out_path):
        return None
    return out_path, v.get("id")


def fetch_clip(query: str, out_path: str, api_key: str | None = None,
               min_width: int = 1280, portrait: bool = False) -> str | None:
    """Search Pexels and download one atmospheric clip to out_path. Returns out_path,
    or None on any failure / missing key (caller self-stubs)."""
    api_key = api_key or os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return None
    res = _fetch_one(query, out_path, api_key, min_width, set(), portrait=portrait)
    return res[0] if res else None


def _load_used() -> set:
    try:
        return set(json.load(open(_USED_PATH)))
    except Exception:
        return set()


def _save_used(used: set) -> None:
    try:
        with open(_USED_PATH, "w") as f:
            json.dump(sorted(i for i in used if i is not None), f)
    except Exception:
        pass


def fetch_clips(queries: list[str], out_dir: str, api_key: str | None = None,
                portrait: bool = False) -> list[str | None]:
    """One clip per query (chapter), in order. Each pick is random and de-duplicated
    against everything used before (across videos) AND within this batch. Missing/failed → None."""
    os.makedirs(out_dir, exist_ok=True)
    api_key = api_key or os.environ.get("PEXELS_API_KEY")
    used = _load_used()
    batch = set(used)   # also avoid repeating a clip within this same video
    out = []
    for i, q in enumerate(queries):
        res = _fetch_one(q, os.path.join(out_dir, f"bg_{i:02d}.mp4"), api_key, 1280, batch,
                         portrait=portrait) if api_key else None
        if res:
            out.append(res[0])
            if res[1] is not None:
                batch.add(res[1]); used.add(res[1])
        else:
            out.append(None)
    _save_used(used)
    return out
