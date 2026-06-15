"""Pre-flight QC lint for props.json. Pure-stdlib, no ffmpeg/network/API.

Operates ONLY on the props dict (captions + chapters): auto-fixes deterministic
caption/headline/timing defects, then re-runs detectors to decide pass/block.
The linter NEVER touches files — run_video.py regenerates captions.srt from the
returned props. Mirrors the fact-gate pattern: auto-fix once → re-verify → gate.
"""
from __future__ import annotations
import copy
import re

from engine import config

# Closing/joining punctuation: a token STARTING with one of these glues onto its
# predecessor with no space (',000' → '$1,000'; '.' / ',' / '%').
_JOIN_PUNCT = set(',.;:%)]\}\'"!?')
_PUNCT_ONLY = re.compile(r"^[^\w]+$", re.UNICODE)   # token has no letters/digits at all


def _needs_left_merge(tok: str) -> bool:
    """True if this caption token should be swallowed into its predecessor:
    empty, leading join-punctuation, or pure-punctuation."""
    t = (tok or "").strip()
    if not t:
        return True
    if t[0] in _JOIN_PUNCT:
        return True
    return bool(_PUNCT_ONLY.match(t))


def _join_space(prev: str, tok: str) -> str:
    """Glue tok onto prev: NO space for a punct/continuation fragment, one space
    for a normal word (the gap-#1 'space dilemma' fix)."""
    t = (tok or "").strip()
    if not t:
        return prev
    if t[0] in _JOIN_PUNCT or _PUNCT_ONLY.match(t):
        return prev + t
    return prev + " " + t


def _norm_word(s: str) -> str:
    """Letters-only lowercase, for filler matching."""
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _norm_headline(s: str) -> str:
    """Alphanumeric-only lowercase, for duplicate-headline matching."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())
