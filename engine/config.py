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

# ── API cost tracking ─────────────────────────────────────────────────────────
COST_LEDGER_PATH = "logs/api-cost.jsonl"  # one priced JSON row per Anthropic call
COST_ALERT_USD = 10.0                     # per-run budget alert (warn-only, never blocks)

# ── Channel identity (passed to every agent as context) ───────────────────────
CHANNEL_CONTEXT = """
Channel: The Untold Game
Niche: Multi-sport history and storytelling (YouTube)
Brand voice: Cinematic, authoritative, entertaining — like ESPN 30 for 30
Tagline: "The Archive of Lost Sports History"
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

# Channel handle (watermark, end card, description CTA) + default music credit.
CHANNEL_HANDLE = "@untoldgamemedia"
# Channel positioning (banner + public "About"; source of truth for engine.pipeline.banner).
CHANNEL_NAME = "The Untold Game"
CHANNEL_SUBTITLE = "The Archive of Lost Sports History"
CHANNEL_DESCRIPTION = """The Untold Game — The Archive of Lost Sports History.
Premium, heavily researched documentaries on the forgotten, buried, and deliberately overlooked stories behind the world's biggest games — F1, football, cricket, the NFL, and beyond. Cinematic, told in a 30-for-30 voice. Every claim verified; nothing sensationalized.
▶ New untold stories regularly. Subscribe → @untoldgamemedia"""
# Neutral default — the curated library is mixed-source (Pixabay, Tunetank, etc.), so we
# don't claim a single source. Per-track credits in music/attribution.json override this.
MUSIC_CREDIT_DEFAULT = "Royalty-free background music"

# ── Video length target ───────────────────────────────────────────────────────
# Channel-wide narration-length cap. Overrides each idea's `format_suggestion`
# (the idea agents tend to propose "18-25 min", which renders ~13min+ and tests
# viewer patience). Kokoro narrates ~220 wpm, so ~1,800 words ≈ 8-9 min.
# Tune this single knob to make every future video shorter/longer.
TARGET_SCRIPT_WORDS = 1800        # spoken words; primary driver of runtime
TARGET_SCRIPT_WORDS_MIN = 1600
TARGET_SCRIPT_WORDS_MAX = 2000
TARGET_RUNTIME_LABEL = "8-9 minutes"

SHORT_SCRIPT_WORDS_MIN = 110   # YouTube Shorts: ~50-55s at the brisk short pace (~2.3 words/s)
SHORT_SCRIPT_WORDS_MAX = 135

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
# Short-form is brisker and tighter than the cinematic long-form pace above — TikTok/Reels
# give you ~2s before a swipe, so we cut the calm. Long-form keeps the values above.
SHORT_NARRATION_SPEED = 1.12     # noticeably brisk, still clear (vs 0.9 long-form)
SHORT_NARRATION_GAP_S = 0.12     # near-eliminate the dramatic pauses (vs 0.5)
# Only two voices in rotation: af_sarah (warm, well-proportioned) carries the
# emotional/somber stories; bm_george (authoritative British male) anchors the rest.
NARRATION_VOICE_DEFAULT = "bm_george"
NARRATION_VOICE_BY_MOOD = {
    "triumphant": "bm_george",  # authoritative for the payoff
    "hype":       "bm_george",  # drives energy
    "tense":      "bm_george",  # measured, investigative
    "somber":     "af_sarah",   # warm, gentle for loss
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

# Atmospheric b-roll search terms per mood. Purely symbolic/abstract (nature, sky, weather,
# space, texture) — zero integrity risk (never implies real event footage). Each pool has
# enough terms that beat-level selection + the global used_clips.json dedup yields a fresh
# clip per beat. Keys match the four canonical MOODS (tense/triumphant/somber/hype).
MOOD_BROLL_POOL = {
    "somber": ["rain on window", "grey ocean waves", "dusk fog forest", "empty road night",
               "falling snow slow", "still misty lake", "dark clouds drifting", "candle flame dark"],
    "triumphant": ["sunrise over clouds", "light rays forest", "open blue sky", "mountain summit",
                   "golden hour ocean", "soaring birds sky", "sun flare horizon", "aurora night sky"],
    "tense": ["storm clouds timelapse", "lightning strike", "crashing waves rocks", "dark smoke",
              "fast moving clouds", "flickering light dark", "rough sea storm", "wind grass field"],
    "hype": ["city lights night", "neon lights motion", "fireworks night", "highway traffic timelapse",
             "fast city motion", "abstract energy light", "crowd lights blur", "spinning star trails"],
}

SHORT_BROLL_BEAT_S = 4.0    # short: a new atmospheric clip every ~4s (energetic but breathing)
LONG_BROLL_BEAT_S = 7.0     # long: every ~7s — varied but cinematic, no single-clip loop

# ── Fact-gate (fact_gate.py) ──────────────────────────────────────────────────
import os as _os  # local alias; config.py is module-level constants
_FACT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # repo root
# Persistent MediaWiki entity cache (gitignored). Keyed by resolved article title;
# compounds across videos. See docs/superpowers/specs/2026-06-13-fact-gate-design.md.
FACTCACHE_PATH = _os.path.join(_FACT_ROOT, ".factcache.json")
FACTCACHE_TTL_DAYS = 30          # bounds living-entity staleness (see spec Risks)
FACT_GATE_SHADOW = True          # ship in shadow: compute verdicts, still route all to human
