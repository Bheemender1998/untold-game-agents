"""
Narration audio from script.md (TEXT-TO-SPEECH).

Two providers, auto-detected (no config needed):

  kokoro  — kokoro-onnx (82M, ONNX, CPU). The quality voice; runs on M2/8GB.
            Needs `pip install kokoro-onnx` AND the two model files (see _synth_kokoro).
  say     — macOS built-in `say` → ffmpeg to wav. Zero install, robotic-but-clear.
            The "prove the pipeline today" provider.

`synthesize()` picks kokoro if importable, else falls back to `say`. Whisper
(captions.py) gives the word timings later — TTS only has to produce clean audio.
"""
from __future__ import annotations
import functools
import os
import re
import shutil
import subprocess
import tempfile

from engine import config


_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

# Seedable phonetic respellings applied to the NARRATION TEXT ONLY (not the caption
# glossary), so espeak says tricky names right. Approximate — tune by ear over time.
# Captions keep the canonical spelling (proper_nouns feeds whisper the real names).
_PRONUNCIATION = {
    "Ickx": "Eex",
    "Balestre": "Balestra",
    "Bellof": "Bell-off",
    "Tendulkar": "Ten-dull-car",
    "Sachin": "Suh-chin",
    "Médellín": "Meda-yeen",
    "Medellín": "Meda-yeen",
}


def _int_to_words(n: int) -> str:
    """Cardinal number → English words (e.g. 2003 → 'two thousand three'). Up to billions."""
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else "")
    if n < 1000:
        return _ONES[n // 100] + " hundred" + (f" {_int_to_words(n % 100)}" if n % 100 else "")
    for div, name in ((1_000_000_000, "billion"), (1_000_000, "million"), (1000, "thousand")):
        if n >= div:
            return _int_to_words(n // div) + f" {name}" + (f" {_int_to_words(n % div)}" if n % div else "")
    return str(n)


def _spell_grouped_numbers(text: str) -> str:
    """Spell out thousands-separated integers (e.g. '2,003' → 'two thousand three') so TTS
    reads them naturally instead of digit-by-digit ('two zero zero three'). Skips currency
    ('$1,234') and decimals ('1,234.56') — espeak reads those acceptably and partial spelling
    would mangle them. Plain numbers (years, small counts) are left untouched."""
    return re.sub(r"(?<![\d.$])\d{1,3}(?:,\d{3})+\b(?!\.\d)",
                  lambda m: _int_to_words(int(m.group().replace(",", ""))), text)


def _year_to_words(n: int) -> str:
    """Spoken form of a 4-digit year. 1100-1999 → paired decades ('nineteen eighty-four',
    'nineteen hundred', 'nineteen oh five'); 2000-2009 → 'two thousand [n]'; 2010-2099 →
    'twenty [nn]'. Anything else falls back to the cardinal form."""
    if not (1100 <= n <= 2099):
        return _int_to_words(n)
    hi, lo = n // 100, n % 100
    if 2000 <= n <= 2009:
        return "two thousand" + (f" {_ONES[lo]}" if lo else "")
    if lo == 0:
        return _int_to_words(hi) + " hundred"
    if lo < 10:
        return _int_to_words(hi) + f" oh {_ONES[lo]}"
    return _int_to_words(hi) + f" {_int_to_words(lo)}"


def _spell_years(text: str) -> str:
    """Spell standalone 4-digit years (1100-2099) the way people say them, so espeak
    doesn't read '1984' as 'nineteen hundred eighty four'. Skips currency/decimals and
    digits glued to other digits (e.g. '$1,984', '19840'). Year ranges like '1984-1988'
    are converted to 'nineteen eighty-four to nineteen eighty-eight' before the
    standalone pass. Decades like '1990s' are left unchanged."""
    text = re.sub(
        r"\b(1[1-9]\d{2}|20\d{2})\s*-\s*(1[1-9]\d{2}|20\d{2})\b",
        lambda m: f"{_year_to_words(int(m.group(1)))} to {_year_to_words(int(m.group(2)))}",
        text,
    )
    return re.sub(r"(?<![\d.$,])(1[1-9]\d{2}|20\d{2})(?![\ds])",
                  lambda m: _year_to_words(int(m.group())), text)


@functools.lru_cache(maxsize=1)
def _pronunciation_re():
    if not _PRONUNCIATION:
        return None
    alt = "|".join(re.escape(k) for k in sorted(_PRONUNCIATION, key=len, reverse=True))
    return re.compile(rf"\b(?:{alt})\b")


def apply_pronunciation(text: str) -> str:
    """Respell mapped names phonetically for TTS (word-boundary, longest-match-first).
    Applied to the narration text only — the caption glossary keeps canonical names."""
    pat = _pronunciation_re()
    if pat is None:
        return text
    return pat.sub(lambda m: _PRONUNCIATION[m.group(0)], text)


# Lines a chatty model leaks around the real narration — reasoning preamble, word-count
# tallies, draft markers. Conservative + line-start anchored so real narration never matches.
_SCAFFOLD_RE = [
    re.compile(r"^word count\b", re.I),
    re.compile(r"^let me\b", re.I),
    re.compile(r"^now let me\b", re.I),
    re.compile(r"^here'?s\b", re.I),
    re.compile(r"^here is\b", re.I),
    re.compile(r"^good[\s,—-]", re.I),
    re.compile(r"^i'?ll write\b", re.I),
    re.compile(r"^i (now )?have\b", re.I),
    re.compile(r"^\d+\s+words\b", re.I),
    re.compile(r"\bwords\b\s*[—-].*(within range|slightly under|over)", re.I),
]
_TOKEN_TALLY_RE = re.compile(r"\(\d+\)")


def is_scaffold_line(line: str) -> bool:
    """True when a line is leaked model scaffolding (reasoning preamble, word-count tally,
    draft marker) rather than spoken narration. Strips markdown emphasis first."""
    s = re.sub(r"[*_`]", "", line).strip()
    if not s:
        return False
    if "✅" in s and len(s.split()) <= 6:
        return True
    if len(_TOKEN_TALLY_RE.findall(s)) >= 3:   # "A(1) kung-fu(2) kick(3)…"
        return True
    return any(p.search(s) for p in _SCAFFOLD_RE)


def script_to_narration_text(script_md: str) -> str:
    """Strip production cues ([VISUAL]/[ARCHIVAL]/[MUSIC]) and headers so only the
    spoken narration is sent to TTS."""
    lines = []
    for ln in script_md.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if re.match(r"^\[[A-Z].*\]$", s):   # bracketed cue lines
            continue
        if re.match(r"(?i)^MOOD:\s*\w+\s*$", s):  # leaked short-script MOOD header
            continue
        if is_scaffold_line(s):                    # leaked reasoning / word-count / drafts
            continue
        s = re.sub(r"[*_`]", "", s)          # drop markdown emphasis (spoken, not read)
        s = _spell_grouped_numbers(s)        # '2,003' → 'two thousand three' for clean TTS
        s = _spell_years(s)                  # '1984' → 'nineteen eighty-four' (year form)
        lines.append(s)
    return "\n".join(lines)


# ── Voice selection (content-aware) ──────────────────────────────────────────

def resolve_voice(mood: str | None) -> str:
    """Kokoro voice for a story mood; falls back to the default voice."""
    return config.NARRATION_VOICE_BY_MOOD.get(mood or "", config.NARRATION_VOICE_DEFAULT)


def mood_for_pillar(pillar: str | None) -> str:
    """Mood for a content pillar (long-form has no per-script mood). '' if unknown."""
    return config.PILLAR_MOOD.get(pillar or "", "")


def narration_pace(fmt: str | None) -> tuple[float, float]:
    """(speed, gap_s) for kokoro narration by output format. 'short' is brisk + tight;
    anything else (long/None) keeps the calm cinematic defaults."""
    if fmt == "short":
        return config.SHORT_NARRATION_SPEED, config.SHORT_NARRATION_GAP_S
    return config.NARRATION_SPEED, config.NARRATION_GAP_S


def narration_voice(idea: dict, override: str | None = None,
                    provider: str = "kokoro") -> str | None:
    """Pick the narration voice for an idea. An explicit `override` always wins.
    Non-kokoro providers keep their own default voice (return None). Otherwise the
    voice comes from the idea's explicit `mood`, else its pillar-derived mood."""
    if override:
        return override
    if provider != "kokoro":
        return None
    mood = idea.get("mood") or mood_for_pillar(idea.get("pillar"))
    return resolve_voice(mood)


# ── Provider selection ───────────────────────────────────────────────────────

def available_provider() -> str:
    """Which provider synthesize() would use right now: 'kokoro' if installed, else
    'say' on macOS, else '' (none)."""
    try:
        import kokoro_onnx  # noqa: F401
        return "kokoro"
    except Exception:
        pass
    if shutil.which("say") and shutil.which("ffmpeg"):
        return "say"
    return ""


def synthesize(text: str, out_path: str, provider: str | None = None,
               voice: str | None = None, speed: float | None = None,
               gap_s: float | None = None) -> str:
    """Render narration `text` to a wav at out_path. Returns out_path.

    provider: 'kokoro' | 'say' | None (auto). Raises if the chosen provider can't run.
    speed/gap_s: kokoro only (None → config defaults).
    """
    provider = provider or available_provider()
    if provider == "kokoro":
        return _synth_kokoro(text, out_path, voice, speed, gap_s)
    if provider == "say":
        return _synth_say(text, out_path, voice)
    raise RuntimeError(
        "No TTS provider available. Install kokoro-onnx (`pip install kokoro-onnx`) "
        "or run on macOS (built-in `say` + ffmpeg)."
    )


# ── macOS `say` (zero install) ───────────────────────────────────────────────

def _synth_say(text: str, out_path: str, voice: str | None) -> str:
    """macOS `say`: text → AIFF → wav (24kHz mono) via ffmpeg. Long text is passed
    by file so we don't hit argv limits."""
    voice = voice or "Daniel"   # en_GB, the most documentary-ish built-in voice
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        tf.write(text)
        txt_path = tf.name
    aiff_path = out_path + ".aiff"
    try:
        subprocess.run(["say", "-v", voice, "-o", aiff_path, "-f", txt_path], check=True)
        subprocess.run(
            ["ffmpeg", "-y", "-i", aiff_path, "-ar", "24000", "-ac", "1", out_path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    finally:
        for p in (txt_path, aiff_path):
            if os.path.exists(p):
                os.remove(p)
    return out_path


# ── Kokoro (quality, local) ──────────────────────────────────────────────────

# Model files aren't shipped with the pip package — download once and point these
# env vars (or drop the files in engine/video/models/) at them:
#   kokoro-v0_19.onnx  + voices.bin
#   https://github.com/thewh1teagle/kokoro-onnx (Releases) — see that README.
_MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
_KOKORO_MODEL = os.environ.get("KOKORO_MODEL", os.path.join(_MODELS_DIR, "kokoro-v0_19.onnx"))
_KOKORO_VOICES = os.environ.get("KOKORO_VOICES", os.path.join(_MODELS_DIR, "voices.bin"))


def _synth_kokoro(text: str, out_path: str, voice: str | None,
                  speed: float | None = None, gap_s: float | None = None) -> str:
    """kokoro-onnx narration. Splits long text into sentences and concatenates so we
    don't blow the per-call length limit; writes a 24kHz wav."""
    import numpy as np
    import soundfile as sf
    from kokoro_onnx import Kokoro

    if not (os.path.exists(_KOKORO_MODEL) and os.path.exists(_KOKORO_VOICES)):
        raise RuntimeError(
            "Kokoro model files missing. Download kokoro-v0_19.onnx + voices.bin "
            f"into {_MODELS_DIR}/ (or set KOKORO_MODEL / KOKORO_VOICES). "
            "See https://github.com/thewh1teagle/kokoro-onnx."
        )
    voice = voice or config.NARRATION_VOICE_DEFAULT
    speed = config.NARRATION_SPEED if speed is None else speed
    gap_s = config.NARRATION_GAP_S if gap_s is None else gap_s
    kokoro = Kokoro(_KOKORO_MODEL, _KOKORO_VOICES)

    sample_rate = 24000
    gap = np.zeros(int(gap_s * sample_rate), dtype=np.float32)   # pause between sentences
    chunks: list = []
    for sent in _split_sentences(text):
        samples, sr = kokoro.create(sent, voice=voice, speed=speed, lang="en-us")
        sample_rate = sr
        chunks.append(np.asarray(samples, dtype=np.float32))
        chunks.append(gap)
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    sf.write(out_path, audio, sample_rate)
    return out_path


_ABBR = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|vs|No|etc|Inc|Ltd)\.")
# Words that almost always begin a NEW sentence — used to recover a real sentence break
# after an initialism (e.g. "…in D.C. She moved.") without re-splitting a name ("O.J. Simpson").
_SENT_START = (r"The|This|That|These|Those|It|He|She|They|We|You|I|But|And|Or|Yet|So|"
               r"When|While|After|Before|Then|Now|Today|Yesterday|Tomorrow|Meanwhile|"
               r"By|In|On|At|For|From|With|Despite|During|Within|His|Her|Their|Its|A|An")
_INITIALISM_BREAK = re.compile(rf"(?<=[A-Z]\.)\s+(?=(?:{_SENT_START})\b)")


def _split_sentences(text: str) -> list[str]:
    """Sentence split for chunked synthesis (keeps terminal punctuation). Dotted initialisms
    (O.J., U.S., D.C., I.R.S.) and common abbreviations (Dr., Mr., No.) are protected so they
    aren't split into their own chunk — which would speak them with a spurious 0.5s gap. A real
    sentence break that lands right after an initialism (e.g. 'in D.C. She moved.') is recovered
    only when the next word is a clear sentence-starter, so names ('O.J. Simpson') stay intact."""
    sep = "․"  # one-dot leader stands in for a protected period during the split
    hide = lambda m: m.group(0).replace(".", sep)
    t = text.replace("\n", " ")
    t = re.sub(r"\b(?:[A-Za-z]\.){2,}", hide, t)        # O.J., U.S., D.C., I.R.S.
    t = re.sub(r"\b[A-Z]\.(?=\s*[A-Z][a-z])", hide, t)  # single initial before a name: "J. Smith"
    t = _ABBR.sub(hide, t)                               # Dr., Mr., No., etc.
    out: list[str] = []
    for p in re.split(r"(?<=[.!?])\s+", t):
        p = p.replace(sep, ".")
        out.extend(s.strip() for s in _INITIALISM_BREAK.split(p) if s.strip())
    return out
