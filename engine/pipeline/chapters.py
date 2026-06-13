"""Post-render chapter-timestamp sync.

The metadata LLM *estimates* description chapter timestamps at produce time — and it
estimates badly (wrong count AND wrong times: a ~11-min video listed chapters running to
39:45). The rendered ``props.json`` holds the AUTHORITATIVE per-chapter start times
(``startMs``) and on-screen headlines. After a render, we rebuild the description's chapter
block from that, so YouTube chapters are exact. Self-stubbing — never crashes a render.
"""
from __future__ import annotations
import json
import os
import re
import string

from engine import paths

_TS = re.compile(r"^\s*\d{1,2}:\d{2}\b")   # a chapter line starts with MM:SS (any separator)


def _mmss(ms: int) -> str:
    s = round((ms or 0) / 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


def _titlecase(headline: str) -> str:
    """On-screen headlines are UPPERCASE; present them as Title Case in the description."""
    return string.capwords((headline or "").strip())


def rebuild_chapters(description: str, chapters: list[dict]) -> str:
    """Return `description` with its chapter block replaced by real times + headlines from
    the rendered `chapters` (each {headline, startMs}). The block is the LONGEST contiguous
    run of timestamp lines (so a stray timestamp in prose is never mistaken for it). Returns
    the description unchanged when there are no render chapters or no block to replace."""
    if not chapters:
        return description
    lines = description.splitlines()
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
        return description
    start, end = max(runs, key=lambda r: r[1] - r[0])
    block = [f"{_mmss(c.get('startMs', 0))} — {_titlecase(c.get('headline', ''))}"
             for c in chapters]
    lines[start:end] = block
    return "\n".join(lines)


def sync_from_render(idea_id: str, fmt: str = "long") -> bool:
    """After a render, rewrite produced/<id>/<fmt>/metadata.json's description chapters from
    the rendered video/props.json (real per-chapter times). Returns True if the description
    changed. Self-stubs (returns False, never raises) on any missing file or error — a
    chapter-sync failure must not break an otherwise-good render."""
    try:
        out_dir = paths.artifact_dir(idea_id, fmt)
        meta_path = os.path.join(out_dir, "metadata.json")
        props_path = os.path.join(out_dir, "video", "props.json")
        if not (os.path.exists(meta_path) and os.path.exists(props_path)):
            return False
        with open(meta_path) as f:
            meta = json.load(f)
        with open(props_path) as f:
            chapters = json.load(f).get("chapters", [])
        new_desc = rebuild_chapters(meta.get("description", ""), chapters)
        if new_desc == meta.get("description"):
            return False
        meta["description"] = new_desc
        tmp = meta_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        os.replace(tmp, meta_path)   # atomic
        return True
    except Exception:
        return False
