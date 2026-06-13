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
import os
import re
import shutil
import subprocess
import tempfile

from engine import config


_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


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
        s = re.sub(r"[*_`]", "", s)          # drop markdown emphasis (spoken, not read)
        s = _spell_grouped_numbers(s)        # '2,003' → 'two thousand three' for clean TTS
        lines.append(s)
    return "\n".join(lines)


# ── Voice selection (content-aware) ──────────────────────────────────────────

def resolve_voice(mood: str | None) -> str:
    """Kokoro voice for a story mood; falls back to the default voice."""
    return config.NARRATION_VOICE_BY_MOOD.get(mood or "", config.NARRATION_VOICE_DEFAULT)


def mood_for_pillar(pillar: str | None) -> str:
    """Mood for a content pillar (long-form has no per-script mood). '' if unknown."""
    return config.PILLAR_MOOD.get(pillar or "", "")


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


def _split_sentences(text: str) -> list[str]:
    """Sentence split for chunked synthesis (keeps terminal punctuation). Dotted initialisms
    (O.J., U.S., D.C., I.R.S.) and common abbreviations (Dr., Mr., No.) are protected so they
    aren't split into their own chunk — which would speak them with a spurious 0.5s gap.
    (Heuristic: a rare initialism that genuinely ends a sentence may merge with the next — a
    minor pacing nit, far better than the frequent mid-name gaps.)"""
    sep = "․"  # one-dot leader stands in for a protected period during the split
    hide = lambda m: m.group(0).replace(".", sep)
    t = text.replace("\n", " ")
    t = re.sub(r"\b(?:[A-Za-z]\.){2,}", hide, t)        # O.J., U.S., D.C., I.R.S.
    t = re.sub(r"\b[A-Z]\.(?=\s*[A-Z][a-z])", hide, t)  # single initial before a name: "J. Smith"
    t = _ABBR.sub(hide, t)                               # Dr., Mr., No., etc.
    parts = re.split(r"(?<=[.!?])\s+", t)
    return [p.replace(sep, ".").strip() for p in parts if p.strip()]
