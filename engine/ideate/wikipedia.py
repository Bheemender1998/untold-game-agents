"""Authoritative-source lookup for the fact-gate. Queries the MediaWiki API (no key) for the
most relevant article's intro extract — encyclopedic ground truth to complement the noisy
DuckDuckGo results that flag false-positives on well-documented topics (e.g. Kolkata 2001).
Pattern borrowed from anthropics/claude-cookbooks (Wikipedia-RAG). See docs/external-references.md.
"""
from __future__ import annotations

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
        return f"[Wikipedia: {title}] {trimmed}"
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return ""
