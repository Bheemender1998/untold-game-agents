"""One-off: auto-source a subject photo (Wikipedia lead image) per story and
generate the 6 thumbnails (3 ids x long/short). Wikipedia/Commons is the most
license-defensible source. Run from repo root: python3 scripts/source_thumbnails.py
"""
import io
import os
import sys
import time

import requests
from PIL import Image

from engine import paths, queue_manager as q
from engine.pipeline import thumbnail

_API = "https://en.wikipedia.org/w/api.php"
_UA = "TheUntoldGame-thumbnail/1.0 (YouTube: The Untold Game; contact via project repo)"

# id -> candidate Wikipedia articles (first that yields a valid raster photo wins).
# Wikipedia lead images for people are usually photos; team/event articles are often
# SVG logos (unusable), so people are listed first.
SUBJECTS = {
    "f058733a": ["Ayrton Senna"],                                   # Senna vs Schumacher
    "4ef3fc89": ["Ali Daei", "Mehdi Mahdavikia", "Carlos Queiroz",  # Iran-USA 1998 figures
                 "Iran national football team"],
    "648d57e6": ["Felipe Massa", "Fernando Alonso"],                # Massa / Crashgate
}


def lead_image_url(title: str) -> str | None:
    r = requests.get(_API, timeout=20, headers={"User-Agent": _UA}, params={
        "action": "query", "prop": "pageimages", "piprop": "original",
        "titles": title, "format": "json"})
    pages = r.json().get("query", {}).get("pages", {})
    p = next(iter(pages.values()), {})
    return (p.get("original") or {}).get("source")


def _valid_raster(url: str, content: bytes) -> Image.Image | None:
    if url.lower().endswith(".svg") or content[:5] == b"<?xml" or content[:4] == b"<svg":
        return None
    try:
        im = Image.open(io.BytesIO(content)); im.load()
        return im.convert("RGB")
    except Exception:
        return None


def fetch_subject(titles: list[str], dest: str) -> str | None:
    """Try each candidate; save the first that yields a valid raster photo. Returns the
    title used, or None."""
    for title in titles:
        url = lead_image_url(title)
        if not url:
            continue
        content = None
        for attempt in range(4):                       # upload.wikimedia rate-limits (429)
            try:
                r = requests.get(url, timeout=30, headers={"User-Agent": _UA})
            except Exception:
                break
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1))          # back off and retry
                continue
            content = r.content
            break
        if content is None:
            continue
        im = _valid_raster(url, content)
        if im is None or min(im.size) < 200:          # skip svg/garbage/tiny logos
            print(f"  · '{title}' → not a usable photo ({url.rsplit('/', 1)[-1]}), trying next")
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        im.save(dest, "PNG")
        print(f"  ✓ subject ← '{title}' ({url.rsplit('/', 1)[-1]}) → {os.path.relpath(dest)}")
        return title
    print(f"  ! no usable lead image among {titles}")
    return None


def main() -> int:
    made = 0
    for idea_id, titles in SUBJECTS.items():
        idea = q.get_by_id(idea_id) or {"id": idea_id}
        print(f"\n▶ [{idea_id}] candidates: {titles}")
        # Download the subject ONCE per story (politer to the image server), reuse for both.
        long_subj = paths.subject_path(idea_id, "long")
        if not fetch_subject(titles, long_subj):
            continue
        for fmt in ("long", "short"):
            try:
                dest = paths.subject_path(idea_id, fmt)
                if fmt == "short":
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    Image.open(long_subj).convert("RGB").save(dest, "PNG")  # reuse
                script_file = os.path.join(os.path.dirname(dest), "script.md")
                script = open(script_file).read() if os.path.exists(script_file) else ""
                thumbnail.generate_thumbnail({**idea, "script": script}, fmt)
                if os.path.exists(paths.thumbnail_path(idea_id, fmt)):
                    made += 1
            except Exception as e:                     # one story must not crash the rest
                print(f"  ! [{idea_id}/{fmt}] failed: {e}")
    print(f"\n=== {made}/6 thumbnails generated ===")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
