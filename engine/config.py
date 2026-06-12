"""
The Untold Game — Stage 1 Configuration
Central config for all agents and the idea queue.
"""

# Load ANTHROPIC_API_KEY (and anything else) from a local .env if present, so
# you don't have to `export` it every shell. .env is gitignored — never commit it.
import os
try:
    from dotenv import load_dotenv
    # .env lives at the project root, one level up from engine/
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except ImportError:
    pass  # python-dotenv optional; falls back to the real environment

# ── Anthropic model ───────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192   # 5 fully-detailed ideas overflow 2048 and truncate the JSON mid-array

# ── Channel identity (passed to every agent as context) ───────────────────────
CHANNEL_CONTEXT = """
Channel: The Untold Game
Niche: Multi-sport history and storytelling (YouTube)
Brand voice: Cinematic, authoritative, entertaining — like ESPN 30 for 30
Tagline: "The stories they forgot to tell you"
Target audience: Sports fans aged 18-45 who want depth beyond the highlights
Content pillars:
  1. The hidden story — buried moments mainstream media never covered
  2. Moments that changed everything — single decisions that altered sport forever
  3. The forgotten figure — overlooked players/coaches who shaped history
  4. The verdict revisited — reopen settled debates with new evidence
  5. Sport vs the world — when sport collided with politics, war, money
  6. The what-if — counterfactual storytelling at its best
Sports covered: NFL, NBA, Soccer/Football, Cricket, Formula 1, UFC, College Sports
"""

# ── Video length target ───────────────────────────────────────────────────────
# Channel-wide narration-length cap. Overrides each idea's `format_suggestion`
# (the idea agents tend to propose "18-25 min", which renders ~13min+ and tests
# viewer patience). Kokoro narrates ~220 wpm, so ~1,800 words ≈ 8-9 min.
# Tune this single knob to make every future video shorter/longer.
TARGET_SCRIPT_WORDS = 1800        # spoken words; primary driver of runtime
TARGET_SCRIPT_WORDS_MIN = 1600
TARGET_SCRIPT_WORDS_MAX = 2000
TARGET_RUNTIME_LABEL = "8-9 minutes"

SHORT_SCRIPT_WORDS_MIN = 90    # YouTube Shorts: ~30-50s of narration
SHORT_SCRIPT_WORDS_MAX = 130

# ── Viral potential scoring rubric ────────────────────────────────────────────
VIRAL_RUBRIC = """
Score each idea 1-10 on:
- Curiosity gap: Does the title create an itch the viewer MUST scratch?
- Emotional trigger: Does it hit nostalgia, injustice, surprise, or triumph?
- Search volume: Will people actively search for this?
- Shareability: Will fans share it in group chats, Reddit, Twitter?
- Evergreen value: Will it perform for months/years, not just days?
"""

# ── Queue settings ─────────────────────────────────────────────────────────────
# Anchored to the project root so the queue is found regardless of CWD.
_ROOT = os.path.dirname(os.path.dirname(__file__))
QUEUE_FILE = os.path.join(_ROOT, "queue", "idea_queue.json")
MAX_IDEAS_PER_RUN = 5        # Ideas each agent generates per run
MIN_VIRAL_SCORE = 6.0        # Ideas below this are filtered out

# ── Stage B: QC thresholds + render timeout ───────────────────────────────────
# qc.py gate. Mean luma is 0-255 (libx264 limited-range black ≈ 16; mid-grey ≈ 126).
QC_BRIGHTNESS_MIN = 40.0       # below → near-black (the darkness bug)
QC_BRIGHTNESS_MAX = 180.0      # above → blown out
QC_MIN_CAPTION_COVERAGE = 0.85 # captions' last word must reach ≥85% of audio length
QC_MAX_CAPTION_GAP_S = 8.0     # no silent caption gap longer than this
QC_DURATION_TOLERANCE = 0.10   # video vs narration-audio duration may differ by ≤10%
RENDER_TIMEOUT_S = 5400        # 90 min hard cap on one render subprocess
PRODUCE_TIMEOUT_S = 1800       # 30 min cap on one produce (script + sequential fact-gate)

# ── Narration voice (TTS) ─────────────────────────────────────────────────────
# Calmer, content-aware delivery. The voice rotates by story "mood"; long-form has
# no per-script mood, so it derives one from the idea's pillar. Voice names are
# Kokoro voices (see engine/video/tts.py).
NARRATION_SPEED = 0.9            # kokoro speed; <1.0 = slower, calmer
NARRATION_GAP_S = 0.5           # silence between sentences (seconds)
NARRATION_VOICE_DEFAULT = "bm_george"
NARRATION_VOICE_BY_MOOD = {
    "triumphant": "bm_george",  # authoritative for the payoff
    "hype":       "bm_george",  # drives energy
    "tense":      "bm_lewis",   # measured, investigative
    "somber":     "bf_emma",    # warm, gentle for loss
}
# Map the 6 content pillars → a mood, so long-form narration picks a voice too.
PILLAR_MOOD = {
    "hidden_story":                    "tense",
    "moments_that_changed_everything": "triumphant",
    "forgotten_figure":                "somber",
    "verdict_revisited":               "tense",
    "sport_vs_world":                  "tense",
    "what_if":                         "hype",
}
