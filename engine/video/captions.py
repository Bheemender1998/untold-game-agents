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
