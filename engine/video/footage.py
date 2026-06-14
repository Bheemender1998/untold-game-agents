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
_PHOTO_SEARCH = "https://api.pexels.com/v1/search"
# Pexels sits behind Cloudflare, which 403s (error 1010) the default python-urllib
# User-Agent. A browser UA is required on BOTH the API call and the CDN download.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# Cross-video dedup ledger of Pexels video ids we've already used.
_USED_PATH = os.path.join(os.path.dirname(__file__), "used_clips.json")

# Keep b-roll on-sport: each sport maps to the keyword Pexels searches best on.
_SPORT_KEYWORD = {
    "F1": "formula 1",
    "Soccer": "soccer",
    "NBA": "basketball",
    "NFL": "american football",
    "Cricket": "cricket",
    "College": "college sports",
    "UFC": "mma",
    "Multi-sport": "",   # too broad to bias on — leave the query as-is
}


def _sport_query(query: str, sport: str | None) -> str:
    """Keep a stock-video query on-sport: prepend the sport keyword unless the query
    already mentions it. Falsy sport → query unchanged (self-stub)."""
    if not sport:
        return query
    keyword = _SPORT_KEYWORD.get(sport, sport.lower())
    low = query.lower()
    if keyword in low or sport.lower() in low:
        return query
    return f"{keyword} {query}"


from engine import config as _config

def mood_beat_queries(mood: str | None, n: int) -> list[str]:
    """n atmospheric search queries for the given mood, cycling the pool so consecutive
    beats differ. Unknown/empty mood falls back to 'tense'. Deterministic (no RNG) — the
    per-clip variety comes from footage.fetch_clips' dedup, not from query randomness."""
    pool = _config.MOOD_BROLL_POOL.get(mood or "", _config.MOOD_BROLL_POOL["tense"])
    return [pool[i % len(pool)] for i in range(n)]


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
    params = urllib.parse.urlencode({"query": query, "per_page": 40,
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
    primary_videos = _search(query, api_key, portrait=portrait)
    videos = primary_videos
    eligible = [v for v in videos if v.get("id") not in exclude_ids
                and _best_file(v, min_width, portrait=portrait)]
    if not eligible:
        # No unused clip for this query. Try a broader query (drop the first word, which is
        # usually the sport keyword or an adjective) to widen the pool before repeating.
        broader = query.split(" ", 1)[1] if " " in query else query
        if broader != query:
            videos = _search(broader, api_key, portrait=portrait)
            eligible = [v for v in videos if v.get("id") not in exclude_ids
                        and _best_file(v, min_width, portrait=portrait)]
    if not eligible:   # genuinely nothing unused → repeat from the widest pool we have, not a blank chapter
        repeat_pool = videos or primary_videos
        eligible = [v for v in repeat_pool if _best_file(v, min_width, portrait=portrait)]
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


def fetch_photo(query: str, out_path: str, api_key: str | None = None,
                min_width: int = 1080) -> str | None:
    """Download one high-res Pexels PHOTO for `query` to out_path. Returns a photographer
    credit on success, else None (missing key / no result / download fail). Never raises."""
    api_key = api_key or os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return None
    params = urllib.parse.urlencode({"query": query, "per_page": 15,
                                     "orientation": "portrait", "size": "large"})
    req = urllib.request.Request(
        f"{_PHOTO_SEARCH}?{params}",
        headers={"Authorization": api_key, "User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            photos = json.load(r).get("photos") or []
    except Exception:
        return None
    for p in photos:
        src = p.get("src") or {}
        link = src.get("large2x") or src.get("original")
        if link and _download(link, out_path):
            return f"Photo by {p.get('photographer', 'Pexels')} on Pexels"
    return None


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
                portrait: bool = False, sport: str | None = None) -> list[str | None]:
    """One clip per query (chapter), in order. Each pick is random and de-duplicated
    against everything used before (across videos) AND within this batch. Each query is
    biased toward `sport` so the b-roll stays on-sport. Missing/failed → None."""
    os.makedirs(out_dir, exist_ok=True)
    api_key = api_key or os.environ.get("PEXELS_API_KEY")
    used = _load_used()
    batch = set(used)   # also avoid repeating a clip within this same video
    out = []
    for i, q in enumerate(queries):
        sq = _sport_query(q, sport)
        res = _fetch_one(sq, os.path.join(out_dir, f"bg_{i:02d}.mp4"), api_key, 1280, batch,
                         portrait=portrait) if api_key else None
        if res:
            out.append(res[0])
            if res[1] is not None:
                batch.add(res[1]); used.add(res[1])
        else:
            out.append(None)
    _save_used(used)
    return out
