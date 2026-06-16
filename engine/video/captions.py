"""
Word-level timestamps + caption lines from the narration audio.

Two jobs: (1) the timing track compose.py uses to sync on-screen captions to the
spoken words, and (2) optional .srt export. Uses faster-whisper (`small`) when it's
installed; when it isn't, the pipeline degrades gracefully — estimate_caption_timings()
spreads caption lines over the measured audio duration (no word-perfect sync, but it
still renders). See run_video / compose for the auto-fallback.

A "caption chunk" anywhere below is {'text': str, 'start': float, 'end': float}.
"""
from __future__ import annotations
import difflib
import json
import re
import subprocess


# ── Whisper transcription (optional dependency) ──────────────────────────────

def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def proper_nouns(text: str, limit: int = 60) -> str:
    """Pull likely proper nouns (capitalised words/names) out of the script, to bias
    whisper toward correct spellings (e.g. Medellín, Andrés Escobar) — passed as
    initial_prompt. Returns a comma-joined glossary string."""
    cands = re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*\b", text or "")
    seen, out = set(), []
    for c in cands:
        if len(c) < 3 or c.lower() in {"the", "this", "that", "then", "they"}:
            continue
        if c not in seen:
            seen.add(c); out.append(c)
        if len(out) >= limit:
            break
    return ", ".join(out)


def transcribe(audio_path: str, model: str = "small",
               initial_prompt: str | None = None) -> dict | None:
    """Word-level transcript of the narration, or None if faster-whisper isn't
    installed (the caller then falls back to estimate_caption_timings()).

    initial_prompt biases recognition toward the script's proper nouns (see proper_nouns()).
    Returns {'words': [{word,start,end}], 'segments': [{start,end,text}]}.
    """
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return None
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segments, _info = m.transcribe(audio_path, word_timestamps=True,
                                   initial_prompt=initial_prompt or None)
    words, segs = [], []
    for seg in segments:
        segs.append({"start": float(seg.start), "end": float(seg.end),
                     "text": seg.text.strip()})
        for w in (seg.words or []):
            words.append({"word": w.word.strip(),
                          "start": float(w.start), "end": float(w.end)})
    return {"words": words, "segments": segs}


# ── Pure helpers (deterministically testable, no deps) ───────────────────────

def chunk_words_to_captions(words: list[dict], max_words: int = 8,
                            max_chars: int = 42) -> list[dict]:
    """Group whisper words into short caption lines, each timed to when it's spoken.
    Breaks on sentence-ending punctuation or when a line hits max_words / max_chars.
    Returns caption chunks (start = first word's start, end = last word's end)."""
    chunks, cur = [], []

    def flush():
        if not cur:
            return
        text = " ".join(w["word"].strip() for w in cur).strip()
        chunks.append({"text": text, "start": cur[0]["start"], "end": cur[-1]["end"]})
        cur.clear()

    for w in words:
        cur.append(w)
        line = " ".join(x["word"].strip() for x in cur)
        ends_sentence = bool(re.search(r"[.!?]$", w["word"].strip()))
        if ends_sentence or len(cur) >= max_words or len(line) >= max_chars:
            flush()
    flush()
    return chunks


def _norm_tok(s: str) -> str:
    """Lowercase, strip non-alphanumerics — for MATCHING only (not display)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def align_to_script(whisper_words: list[dict], narration_text: str) -> list[dict]:
    """Project the SCRIPT's words onto whisper's timings so caption/headline TEXT is the
    script (correct names, hyphens, abbreviations) while TIMING comes from whisper.

    whisper_words: [{word,start,end}] (seconds). Returns the same shape with script text.
    - equal / same-count replace: each script word takes its matched whisper word's OWN
      start/end (real per-word timing — preserves pacing and inter-word silences);
    - multi↔one replace (counts differ): the matched whisper span is split proportionally
      by char length;
    - delete (script word whisper dropped): timing interpolated between known neighbours;
    - insert (whisper word not in script): dropped.
    Falls back to whisper_words unchanged if either side is empty (never crashes a render)."""
    swords = [w for w in re.split(r"\s+", (narration_text or "").strip()) if w]
    if not whisper_words or not swords:
        return whisper_words
    wnorm = [_norm_tok(w["word"]) for w in whisper_words]
    snorm = [_norm_tok(w) for w in swords]
    out: list[dict] = []
    sm = difflib.SequenceMatcher(a=snorm, b=wnorm, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            continue
        sseg = swords[i1:i2]
        if tag == "delete":
            for w in sseg:
                out.append({"word": w, "start": None, "end": None})
            continue
        wseg = whisper_words[j1:j2]
        if len(sseg) == len(wseg):
            # 1:1 correspondence — always true for "equal" blocks, and the common case
            # for "replace" (a single misheard word). Take each whisper word's OWN
            # start/end so real per-word pacing AND the inter-word silences (dramatic
            # pauses) survive. Re-spreading by char length here flattens the timing into
            # a contiguous char-weighted estimate and desyncs every caption.
            for w, ww in zip(sseg, wseg):
                out.append({"word": w, "start": ww["start"], "end": ww["end"]})
            continue
        # counts differ (a multi↔one "replace") — split the matched whisper span
        # proportionally by char length, the best we can do without a 1:1 mapping.
        t0, t1 = wseg[0]["start"], wseg[-1]["end"]
        span = max(0.0, t1 - t0)
        lengths = [max(1, len(w)) for w in sseg]
        total = sum(lengths)
        cursor = t0
        for w, ln in zip(sseg, lengths):
            dur = span * (ln / total) if total else 0.0
            out.append({"word": w, "start": cursor, "end": cursor + dur})
            cursor += dur
    n = len(out)
    for k in range(n):
        if out[k]["start"] is not None:
            continue
        prev = next((out[p]["end"] for p in range(k - 1, -1, -1) if out[p]["end"] is not None), None)
        nxt = next((out[q]["start"] for q in range(k + 1, n) if out[q]["start"] is not None), None)
        lo = prev if prev is not None else (nxt if nxt is not None else 0.0)
        hi = nxt if nxt is not None else lo
        run = []
        q = k
        while q < n and out[q]["start"] is None:
            run.append(q)
            q += 1
        step = (hi - lo) / (len(run) + 1)
        for m, q in enumerate(run, start=1):
            out[q]["start"] = lo + step * m
            out[q]["end"] = lo + step * (m + 0.5)
    return out


# Spoken-number word → value, for collapsing whisper tokens back to digits in captions.
_NUM_UNIT = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_NUM_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
             "seventy": 70, "eighty": 80, "ninety": 90}


def _number_token_value(tok: str):
    """Value of a single lowercased number token, or None. Handles hyphenated tens
    like 'eighty-four' (84) and bare units/tens. 'hundred'/'thousand'/'oh' handled by
    the run parser, not here."""
    tok = tok.strip().lower()
    if tok in _NUM_UNIT:
        return _NUM_UNIT[tok]
    if tok in _NUM_TENS:
        return _NUM_TENS[tok]
    if "-" in tok:
        a, _, b = tok.partition("-")
        if a in _NUM_TENS and b in _NUM_UNIT and 1 <= _NUM_UNIT.get(b, 0) <= 9:
            return _NUM_TENS[a] + _NUM_UNIT[b]
    return None


def _parse_number_run(toks: list[str]):
    """Parse a run of number tokens into an int, conservatively. Recognizes:
    year pairs ('nineteen eighty-four'→1984, 'nineteen hundred'→1900,
    'nineteen oh five'→1905), 'twenty NN' (→20NN), and 'two thousand [n]' (→200n).
    Returns the int or None if the run isn't a confident match."""
    low = [t.strip().lower() for t in toks]
    # two thousand [unit]
    if len(low) >= 2 and low[0] == "two" and low[1] == "thousand":
        if len(low) == 2:
            return 2000
        if len(low) == 3 and (u := _number_token_value(low[2])) is not None and u < 10:
            return 2000 + u
        return None
    # century pair: <unit/teen> ['hundred' | 'oh' <unit> | <tens-or-tens-unit>]
    head = _number_token_value(low[0])
    if head is not None and 10 <= head <= 20:
        if len(low) == 2 and low[1] == "hundred":
            return head * 100
        if len(low) == 3 and low[1] == "oh" and (u := _number_token_value(low[2])) is not None and u < 10:
            return head * 100 + u
        if (len(low) == 3 and low[1] in _NUM_TENS
                and (u := _number_token_value(low[2])) is not None and 1 <= u <= 9):
            return head * 100 + _NUM_TENS[low[1]] + u
        if len(low) == 2 and (lo := _number_token_value(low[1])) is not None and 10 <= lo <= 99:
            return head * 100 + lo
    return None


def digitize_number_words(words: list[dict]) -> list[dict]:
    """Collapse runs of spoken-number tokens in a whisper word list back into a single
    digit token, merging the run's start/end timing. Conservative — only collapses
    confident year-ish patterns (see _parse_number_run); leaves everything else as-is.
    Input/return shape: [{'word','start','end'}]. Trailing punctuation on the run's last
    token is preserved on the digit token."""
    out: list[dict] = []
    i, n = 0, len(words)
    while i < n:
        matched = False
        for run_len in (3, 2):
            if i + run_len > n:
                continue
            chunk = words[i:i + run_len]
            core = [w["word"].rstrip(".,!?;:") for w in chunk]
            val = _parse_number_run(core)
            if val is not None:
                w_last = chunk[-1]["word"]
                punct = w_last[len(w_last.rstrip(".,!?;:")):]
                out.append({"word": f"{val}{punct}",
                            "start": chunk[0]["start"], "end": chunk[-1]["end"]})
                i += run_len
                matched = True
                break
        if not matched:
            out.append(words[i])
            i += 1
    return out


def estimate_caption_timings(narration_text: str, total_duration: float,
                             max_words: int = 8) -> list[dict]:
    """No-whisper fallback: split narration into short lines and spread them across
    total_duration in proportion to word count. Same shape as chunk_words_to_captions."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narration_text.replace("\n", " "))
                 if s.strip()]
    # break long sentences into <=max_words lines
    lines: list[str] = []
    for s in sentences:
        toks = s.split()
        for i in range(0, len(toks), max_words):
            lines.append(" ".join(toks[i:i + max_words]))
    if not lines:
        return []
    weights = [max(1, len(ln.split())) for ln in lines]
    total_w = sum(weights)
    chunks, t = [], 0.0
    for ln, wt in zip(lines, weights):
        dur = total_duration * wt / total_w
        chunks.append({"text": ln, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur
    return chunks


def estimate_word_timings(narration_text: str, total_duration: float) -> list[dict]:
    """No-whisper fallback for Remotion captions: split narration into WORDS and spread
    them across total_duration (weighted by word length). Returns
    [{text, startMs, endMs}] — the word shape the Remotion composition expects."""
    words = [w for w in re.split(r"\s+", narration_text) if w]
    if not words:
        return []
    weights = [len(w) + 1 for w in words]
    total_w = sum(weights)
    out, t = [], 0.0
    for w, wt in zip(words, weights):
        dur = total_duration * wt / total_w
        out.append({"text": re.sub(r"[*_`]", "", w),
                    "startMs": int(round(t * 1000)), "endMs": int(round((t + dur) * 1000))})
        t += dur
    return out


def to_srt(chunks: list[dict], out_path: str) -> str:
    """Write caption chunks ({text,start,end}) as an .srt file. Returns out_path."""
    def ts(sec: float) -> str:
        ms = int(round(sec * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    out = []
    for i, c in enumerate(chunks, 1):
        out.append(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{c['text']}\n")
    with open(out_path, "w") as f:
        f.write("\n".join(out))
    return out_path


# ── Audio duration (ffprobe) ─────────────────────────────────────────────────

def audio_duration(audio_path: str) -> float:
    """Seconds of audio, via ffprobe (ships with ffmpeg)."""
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])
