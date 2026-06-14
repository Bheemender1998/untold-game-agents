"""Authoritative-source lookup for the fact-gate. Queries the MediaWiki API (no key) for the
most relevant article's intro extract — encyclopedic ground truth to complement the noisy
DuckDuckGo results that flag false-positives on well-documented topics (e.g. Kolkata 2001).
Pattern borrowed from anthropics/claude-cookbooks (Wikipedia-RAG). See docs/external-references.md.
"""
from __future__ import annotations

import re

import requests

_API = "https://en.wikipedia.org/w/api.php"
# Wikipedia's API policy requires a descriptive User-Agent.
_UA = "TheUntoldGame-factcheck/1.0 (YouTube: The Untold Game; contact via project repo)"
_TIMEOUT = 10


def lookup(query: str, sentences: int = 6) -> str:
    """Return the intro extract of the top Wikipedia article for `query` (prefixed with the
    article title), or "" if there's no hit or anything fails. NEVER raises — the fact-gate
    must not crash on a lookup failure (same contract as the rest of the gate)."""
    try:
        headers = {"User-Agent": _UA}
        s = requests.get(_API, timeout=_TIMEOUT, headers=headers, params={
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": 1, "format": "json"})
        hits = s.json().get("query", {}).get("search", [])
        if not hits:
            return ""
        title = hits[0]["title"]
        e = requests.get(_API, timeout=_TIMEOUT, headers=headers, params={
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
            "titles": title, "format": "json"})
        pages = e.json().get("query", {}).get("pages", {})
        extract = next(iter(pages.values()), {}).get("extract", "") if pages else ""
        if not extract:
            return ""
        # Trim to the first `sentences` sentences to keep the judge prompt tight.
        flat = " ".join(extract.split())
        trimmed = ". ".join(flat.split(". ")[:sentences]).strip()
        if not trimmed:
            return ""
        return f"[Wikipedia: {title}] {trimmed}"
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return ""


def search_title(query: str) -> str | None:
    """Return the title of the top MediaWiki search hit for `query`, or None.
    NEVER raises (same contract as lookup)."""
    try:
        s = requests.get(_API, timeout=_TIMEOUT, headers={"User-Agent": _UA}, params={
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": 1, "format": "json"})
        hits = s.json().get("query", {}).get("search", [])
        return hits[0]["title"] if hits else None
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return None


def extract(title: str) -> str:
    """Return the FULL plaintext extract of `title` (not intro-only), or "" on any
    failure. NEVER raises."""
    try:
        e = requests.get(_API, timeout=_TIMEOUT, headers={"User-Agent": _UA}, params={
            "action": "query", "prop": "extracts", "explaintext": 1,
            "titles": title, "format": "json"})
        pages = e.json().get("query", {}).get("pages", {})
        return (next(iter(pages.values()), {}) or {}).get("extract", "") or ""
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return ""


def lead_image(query: str, min_width: int = 600) -> tuple[str, str] | None:
    """The lead/infobox image URL + attribution for the best-matching Wikipedia page, or None.
    Rejects SVGs (Pillow can't open them) and images narrower than `min_width`. Never raises."""
    try:
        title = search_title(query)
        if not title:
            return None
        headers = {"User-Agent": _UA}
        r = requests.get(_API, timeout=_TIMEOUT, headers=headers, params={
            "action": "query", "titles": title, "prop": "pageimages",
            "piprop": "original|name", "format": "json"})
        page = next(iter(r.json().get("query", {}).get("pages", {}).values()), {}) or {}
        original = page.get("original") or {}
        url = original.get("source")
        if not url or url.lower().endswith(".svg") or (original.get("width") or 0) < min_width:
            return None
        return url, _image_credit(page.get("pageimage"), headers)
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return None


def _image_credit(file_name: str | None, headers: dict) -> str:
    """'<artist> / <license> via Wikimedia Commons' for a File: name; best-effort, never raises."""
    base = "via Wikimedia Commons"
    if not file_name:
        return base
    try:
        r = requests.get(_API, timeout=_TIMEOUT, headers=headers, params={
            "action": "query", "titles": f"File:{file_name}", "prop": "imageinfo",
            "iiprop": "extmetadata", "format": "json"})
        page = next(iter(r.json().get("query", {}).get("pages", {}).values()), {}) or {}
        meta = (page.get("imageinfo") or [{}])[0].get("extmetadata", {}) or {}
        artist = re.sub(r"<[^>]+>", "", (meta.get("Artist", {}) or {}).get("value", "")).strip()
        lic = ((meta.get("LicenseShortName", {}) or {}).get("value", "")).strip()
        parts = [p for p in (artist, lic) if p]
        return (" / ".join(parts) + " " + base) if parts else base
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return base
