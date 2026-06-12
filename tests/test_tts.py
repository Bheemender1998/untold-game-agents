from engine import config
from engine.taxonomy.pillars import PILLARS
from engine.video import tts


def test_voice_map_covers_the_four_moods():
    for mood in ("triumphant", "hype", "tense", "somber"):
        assert config.NARRATION_VOICE_BY_MOOD[mood]


def test_every_pillar_maps_to_a_known_mood():
    for pillar in PILLARS:
        mood = config.PILLAR_MOOD[pillar]
        assert mood in config.NARRATION_VOICE_BY_MOOD


def test_narration_speed_is_calmer_than_default():
    assert 0.7 <= config.NARRATION_SPEED < 1.0
    assert config.NARRATION_GAP_S >= 0.4


def test_resolve_voice_maps_mood():
    assert tts.resolve_voice("tense") == "bm_george"
    assert tts.resolve_voice("somber") == "af_sarah"


def test_only_sarah_and_george_in_rotation():
    """Narration uses exactly two Kokoro voices: af_sarah and bm_george."""
    allowed = {"af_sarah", "bm_george"}
    assert set(config.NARRATION_VOICE_BY_MOOD.values()) | {config.NARRATION_VOICE_DEFAULT} == allowed


def test_resolve_voice_defaults_on_unknown_or_empty():
    assert tts.resolve_voice("") == config.NARRATION_VOICE_DEFAULT
    assert tts.resolve_voice(None) == config.NARRATION_VOICE_DEFAULT
    assert tts.resolve_voice("nonsense") == config.NARRATION_VOICE_DEFAULT


def test_mood_for_pillar():
    assert tts.mood_for_pillar("verdict_revisited") == "tense"
    assert tts.mood_for_pillar("what_if") == "hype"
    assert tts.mood_for_pillar(None) == ""


def test_narration_voice_prefers_explicit_mood_then_pillar():
    assert tts.narration_voice({"mood": "somber"}) == "af_sarah"
    assert tts.narration_voice({"pillar": "what_if"}) == "bm_george"
    assert tts.narration_voice({"mood": "tense", "pillar": "what_if"}) == "bm_george"


def test_narration_voice_override_wins():
    assert tts.narration_voice({"mood": "somber"}, override="af_sky") == "af_sky"


def test_narration_voice_none_for_non_kokoro_provider():
    # `say` has its own voice (Daniel) — don't hand it a Kokoro voice name.
    assert tts.narration_voice({"mood": "somber"}, provider="say") is None


def test_narration_voice_default_when_no_signal():
    assert tts.narration_voice({}) == config.NARRATION_VOICE_DEFAULT


def test_script_to_narration_text_strips_mood_header_line():
    # Defense in depth: a leaked 'MOOD: <mood>' header must never be spoken by TTS.
    md = "# Title\n\nMOOD: somber\n\nHe made white America forget he was Black."
    out = tts.script_to_narration_text(md)
    assert out.startswith("He made white America")
    assert "MOOD" not in out
    assert "somber" not in out
