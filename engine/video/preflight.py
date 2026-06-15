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
    if _PUNCT_ONLY.match(t):
        return True
    # A continuation fragment starts with closing punctuation and carries NO letters
    # (e.g. ',000', '000.', '.50') — so an opening-quote word like '"No"' or a leading-dash
    # word is NOT swallowed (that would corrupt legitimate text).
    return t[0] in _JOIN_PUNCT and not re.search(r"[^\W\d_]", t, re.UNICODE)


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
        if _needs_left_merge(c["text"]):
            if out:
                prev = out[-1]
                merged = _join_space(prev["text"], c["text"])
                muts.append({"type": "merge", "reason": "orphan_punct",
                             "from": [prev["text"], c["text"]], "into": merged})
                prev["text"] = merged
                prev["endMs"] = max(prev["endMs"], c["endMs"])
            else:
                # Leading orphan-punct has no predecessor to merge into → drop it
                # (a caption can't begin with a stray ',000' / '.').
                muts.append({"type": "drop", "token": c["text"], "reason": "orphan_punct",
                             "at_ms": c["startMs"]})
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
        # A token whose START is at/after the audio end is a ghost — DROP it. Clamping
        # would leave a zero/negative-duration token that _fix_min_duration then pushes
        # back past the boundary (gap #2 / review).
        if c["startMs"] >= narration_ms:
            muts.append({"type": "drop", "token": c["text"], "reason": "ghost_after_audio",
                         "at_ms": c["startMs"]})
            continue
        # Starts during the audio but ends well past it (beyond the tolerated overhang)
        # → straddle, clamp the end back to the audio length. A small overhang within
        # `tol` is left alone (matches the re-verify detector's threshold).
        if c["endMs"] > limit:
            muts.append({"type": "clamp", "token": c["text"], "reason": "past_audio",
                         "from": [c["startMs"], c["endMs"]], "to": [c["startMs"], narration_ms]})
            d = dict(c); d["endMs"] = narration_ms; out.append(d)
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
    end; if that clamp would leave the token shorter than one whole frame, extend the end
    to the next frame so it stays visible (and so re-verify can't block on it). Runs last,
    so extending an end only pushes the NEXT token's clamp forward — monotonicity holds."""
    out: list[dict] = []
    muts: list[dict] = []
    for c in caps:
        c = dict(c)
        if out and c["startMs"] < out[-1]["endMs"]:
            new_start = out[-1]["endMs"]
            new_end = c["endMs"]
            if _frame_index(new_end, fps) <= _frame_index(new_start, fps):
                new_end = int(round((_frame_index(new_start, fps) + 1) * 1000.0 / fps))
            muts.append({"type": "clamp", "token": c["text"], "reason": "non_monotonic",
                         "from": [c["startMs"], c["endMs"]], "to": [new_start, new_end]})
            c["startMs"], c["endMs"] = new_start, new_end
        out.append(c)
    return out, muts


def _detect_oversize(caps: list[dict], max_chars: int) -> list[int]:
    """Rule 11 (warn): a single caption token longer than max_chars is a glued defect."""
    return [i for i, c in enumerate(caps) if len(c["text"]) > max_chars]


def _fix_dup_headlines(ch: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rule 10: merge adjacent chapters with identical (normalized) headline text,
    extending the surviving span to cover both."""
    out: list[dict] = []
    muts: list[dict] = []
    for c in ch:
        if out and _norm_headline(c["headline"]) == _norm_headline(out[-1]["headline"]):
            muts.append({"type": "merge", "reason": "dup_headline",
                         "from": [out[-1]["headline"], c["headline"]], "into": out[-1]["headline"]})
            out[-1]["endMs"] = max(out[-1]["endMs"], c["endMs"])
        else:
            out.append(dict(c))
    return out, muts


def _fix_headline_overlap(ch: list[dict]) -> tuple[list[dict], list[dict]]:
    """Rule 8: enforce non-overlapping chapter cards — clamp start to the previous end."""
    out: list[dict] = []
    muts: list[dict] = []
    for c in ch:
        c = dict(c)
        if out and c["startMs"] < out[-1]["endMs"]:
            new_start = out[-1]["endMs"]
            new_end = max(c["endMs"], new_start)
            muts.append({"type": "clamp", "token": c["headline"], "reason": "headline_overlap",
                         "from": [c["startMs"], c["endMs"]], "to": [new_start, new_end]})
            c["startMs"], c["endMs"] = new_start, new_end
        out.append(c)
    return out, muts


def _detect_stuck_headlines(ch: list[dict], max_s: float) -> list[int]:
    """Rule 9 (warn): a chapter card on screen longer than max_s seconds (dead-air ghost)."""
    return [i for i, c in enumerate(ch) if (c["endMs"] - c["startMs"]) > max_s * 1000]


def _count(muts: list[dict], reason: str) -> int:
    return sum(1 for m in muts if m.get("reason") == reason)


def lint_props(props: dict, fps: int, narration_ms: int) -> tuple[dict, dict]:
    """Auto-fix deterministic caption/headline defects, then re-run detectors to decide
    pass/block. Returns (fixed_props, report). Never raises — malformed input fails the
    structural check and blocks. The single fix pass runs in dependency order; the
    post-fix detectors are the re-verify backstop."""
    props = copy.deepcopy(props)
    muts: list[dict] = []

    # ── caption fixers, in order (gap #2: drop ghosts BEFORE any clamp) ──
    caps = list(props.get("captions") or [])
    caps, m = _fix_past_audio(caps, narration_ms, config.QC_CAPTION_END_TOL_MS); muts += m
    caps, m = _fix_punct_captions(caps); muts += m
    caps, m = _fix_fillers(caps, config.QC_FILLER_WORDS); muts += m
    caps, m = _fix_min_duration(caps, fps); muts += m
    caps, m = _fix_overlap(caps, fps); muts += m
    props["captions"] = caps

    # ── headline fixers ──
    ch = list(props.get("chapters") or [])
    ch, m = _fix_dup_headlines(ch); muts += m
    ch, m = _fix_headline_overlap(ch); muts += m
    props["chapters"] = ch

    # ── re-verify: run detectors on the FIXED props ──
    structural_ok = bool(props.get("captions")) and bool(props.get("chapters")) \
        and bool(props.get("audioSrc")) and bool(props.get("narrationMs"))
    overlaps = [i for i in range(1, len(caps)) if caps[i]["startMs"] < caps[i - 1]["endMs"]]
    bad_dur = [i for i, c in enumerate(caps)
               if _frame_index(c["endMs"], fps) <= _frame_index(c["startMs"], fps)]
    past = [i for i, c in enumerate(caps) if c["endMs"] > narration_ms + config.QC_CAPTION_END_TOL_MS]
    punct = [i for i, c in enumerate(caps) if _needs_left_merge(c["text"])]
    oversize = _detect_oversize(caps, config.QC_MAX_CAPTION_TOKEN_CHARS)
    h_overlap = [i for i in range(1, len(ch)) if ch[i]["startMs"] < ch[i - 1]["endMs"]]
    h_dup = [i for i in range(1, len(ch))
             if _norm_headline(ch[i]["headline"]) == _norm_headline(ch[i - 1]["headline"])]
    stuck = _detect_stuck_headlines(ch, config.QC_MAX_HEADLINE_S)

    checks = [
        {"name": "structural", "severity": "critical", "passed": structural_ok,
         "detail": "captions/chapters/audioSrc/narrationMs present" if structural_ok
         else "missing captions/chapters/audioSrc/narrationMs", "fixed": 0},
        {"name": "split_number_caption", "severity": "critical", "passed": not punct,
         "detail": f"{len(punct)} orphan-punct caption(s) remain", "fixed": _count(muts, "orphan_punct")},
        {"name": "ghost_after_audio", "severity": "critical", "passed": not past,
         "detail": f"{len(past)} caption(s) past audio end", "fixed": _count(muts, "ghost_after_audio") + _count(muts, "past_audio")},
        {"name": "caption_duration", "severity": "critical", "passed": not bad_dur,
         "detail": f"{len(bad_dur)} zero/sub-frame caption(s)", "fixed": _count(muts, "min_frame_duration")},
        {"name": "caption_monotonic", "severity": "critical", "passed": not overlaps,
         "detail": f"{len(overlaps)} overlapping caption(s)", "fixed": _count(muts, "non_monotonic")},
        {"name": "headline_overlap", "severity": "critical", "passed": not h_overlap,
         "detail": f"{len(h_overlap)} overlapping headline(s)", "fixed": _count(muts, "headline_overlap")},
        {"name": "duplicate_headline", "severity": "critical", "passed": not h_dup,
         "detail": f"{len(h_dup)} duplicate headline(s)", "fixed": _count(muts, "dup_headline")},
        {"name": "filler_caption", "severity": "warn", "passed": True,
         "detail": f"{_count(muts, 'filler')} filler(s) dropped", "fixed": _count(muts, "filler")},
        {"name": "oversize_caption_token", "severity": "warn", "passed": not oversize,
         "detail": f"{len(oversize)} oversize token(s) (>{config.QC_MAX_CAPTION_TOKEN_CHARS} chars)", "fixed": 0},
        {"name": "stuck_headline", "severity": "warn", "passed": not stuck,
         "detail": f"{len(stuck)} headline(s) > {config.QC_MAX_HEADLINE_S:.0f}s", "fixed": 0},
    ]
    blocked = any((not c["passed"]) and c["severity"] == "critical" for c in checks)
    report = {"passed": all(c["passed"] for c in checks), "blocked": blocked,
              "checks": checks, "mutations": muts}
    return props, report
