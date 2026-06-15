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
_JOIN_PUNCT = set(",.;:%)]}" "'" '’"”!?')   # straight + curly closing punctuation
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


def _fix_punct_captions(caps: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rules 1+2: swallow orphan-punct / continuation tokens into the previous word.
    Glue with no space; extend the predecessor's endMs to cover the swallowed token."""
    out: list[dict] = []
    muts: list[dict] = []
    for c in caps:
        if out and _needs_left_merge(c["text"]):
            prev = out[-1]
            merged = _join_space(prev["text"], c["text"])
            muts.append({"type": "merge", "reason": "orphan_punct",
                         "from": [prev["text"], c["text"]], "into": merged})
            prev["text"] = merged
            prev["endMs"] = max(prev["endMs"], c["endMs"])
        else:
            out.append(dict(c))
    return out, muts


def _fix_fillers(caps: list[dict], fillers: tuple[str, ...]) -> tuple[list[dict], list[dict]]:
    """Rule 3: drop filler tokens (um/uh/...). Each word keeps absolute timing, so a
    dropped filler leaves a brief un-captioned gap — nothing freezes."""
    fset = {f.lower() for f in fillers}
    out: list[dict] = []
    muts: list[dict] = []
    for c in caps:
        if _norm_word(c["text"]) in fset:
            muts.append({"type": "drop", "token": c["text"], "reason": "filler",
                         "at_ms": c["startMs"]})
            continue
        out.append(dict(c))
    return out, muts


def _fix_past_audio(caps: list[dict], narration_ms: int, tol: int) -> tuple[list[dict], list[dict]]:
    """Rule 7: a Whisper ghost token wholly after the audio is DROPPED (clamping it
    would invert it — gap #2); a token straddling the audio end is clamped to narration_ms."""
    out: list[dict] = []
    muts: list[dict] = []
    limit = narration_ms + tol
    for c in caps:
        if c["startMs"] > limit:
            muts.append({"type": "drop", "token": c["text"], "reason": "ghost_after_audio",
                         "at_ms": c["startMs"]})
            continue
        if c["endMs"] > narration_ms:
            new_end = max(narration_ms, c["startMs"])   # never invert
            muts.append({"type": "clamp", "token": c["text"], "reason": "past_audio",
                         "from": [c["startMs"], c["endMs"]], "to": [c["startMs"], new_end]})
            d = dict(c); d["endMs"] = new_end; out.append(d)
        else:
            out.append(dict(c))
    return out, muts


def _frame_index(ms: int, fps: int) -> int:
    """Which video frame a millisecond timestamp lands on (Remotion rounds ms→frame)."""
    return int(round(ms * fps / 1000.0))


def _fix_min_duration(caps: list[dict], fps: int) -> tuple[list[dict], list[dict]]:
    """Rules 5+6: every caption must span at least one whole frame. Catches zero/negative
    duration (Rule 5, critical) and positive-but-sub-frame captions (Rule 6, warn) with the
    same bump: push endMs to the start of the next frame."""
    out: list[dict] = []
    muts: list[dict] = []
    for c in caps:
        c = dict(c)
        if _frame_index(c["endMs"], fps) <= _frame_index(c["startMs"], fps):
            new_end = int(round((_frame_index(c["startMs"], fps) + 1) * 1000.0 / fps))
            muts.append({"type": "retime", "token": c["text"], "reason": "min_frame_duration",
                         "from": [c["startMs"], c["endMs"]], "to": [c["startMs"], new_end]})
            c["endMs"] = new_end
        out.append(c)
    return out, muts


def _fix_overlap(caps: list[dict], fps: int) -> tuple[list[dict], list[dict]]:
    """Rule 4: enforce monotonic non-overlapping captions. Clamp start to the previous
    end; if that would invert the token, give it one frame so it stays valid."""
    frame_ms = int(round(1000.0 / fps))
    out: list[dict] = []
    muts: list[dict] = []
    for c in caps:
        c = dict(c)
        if out and c["startMs"] < out[-1]["endMs"]:
            new_start = out[-1]["endMs"]
            new_end = c["endMs"] if c["endMs"] >= new_start else new_start + frame_ms
            muts.append({"type": "clamp", "token": c["text"], "reason": "non_monotonic",
                         "from": [c["startMs"], c["endMs"]], "to": [new_start, new_end]})
            c["startMs"], c["endMs"] = new_start, new_end
        out.append(c)
    return out, muts


def _detect_oversize(caps: list[dict], max_chars: int) -> list[int]:
    """Rule 11 (warn): a single caption token longer than max_chars is a glued defect."""
    return [i for i, c in enumerate(caps) if len(c["text"]) > max_chars]
