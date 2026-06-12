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
    assert tts.resolve_voice("tense") == "bm_lewis"
    assert tts.resolve_voice("somber") == "bf_emma"


def test_resolve_voice_defaults_on_unknown_or_empty():
    assert tts.resolve_voice("") == config.NARRATION_VOICE_DEFAULT
    assert tts.resolve_voice(None) == config.NARRATION_VOICE_DEFAULT
    assert tts.resolve_voice("nonsense") == config.NARRATION_VOICE_DEFAULT


def test_mood_for_pillar():
    assert tts.mood_for_pillar("verdict_revisited") == "tense"
    assert tts.mood_for_pillar("what_if") == "hype"
    assert tts.mood_for_pillar(None) == ""


def test_narration_voice_prefers_explicit_mood_then_pillar():
    assert tts.narration_voice({"mood": "somber"}) == "bf_emma"
    assert tts.narration_voice({"pillar": "what_if"}) == "bm_george"
    assert tts.narration_voice({"mood": "tense", "pillar": "what_if"}) == "bm_lewis"


def test_narration_voice_override_wins():
    assert tts.narration_voice({"mood": "somber"}, override="af_sky") == "af_sky"


def test_narration_voice_none_for_non_kokoro_provider():
    # `say` has its own voice (Daniel) — don't hand it a Kokoro voice name.
    assert tts.narration_voice({"mood": "somber"}, provider="say") is None


def test_narration_voice_default_when_no_signal():
    assert tts.narration_voice({}) == config.NARRATION_VOICE_DEFAULT
