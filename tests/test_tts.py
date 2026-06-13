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


def test_split_sentences_keeps_initialisms_intact():
    # Initials must not be split into their own chunk (each chunk gets a 0.5s gap, so
    # "O.J. Simpson" was being spoken as "O.J. <pause> Simpson").
    out = tts._split_sentences("In 1973, O.J. Simpson rushed for glory. The U.S. team won.")
    assert out == ["In 1973, O.J. Simpson rushed for glory.", "The U.S. team won."]


def test_narration_spells_out_comma_grouped_numbers():
    # kokoro reads '2,003' as 'two zero zero three' — spell thousands-grouped numbers out.
    out = tts.script_to_narration_text("He rushed for 2,003 yards, 1,457 short of the mark.")
    assert "two thousand three" in out
    assert "one thousand four hundred fifty-seven" in out
    assert "2,003" not in out and "1,457" not in out


def test_narration_leaves_plain_numbers_alone():
    # Years are now spelled naturally; small counts (300, 134) are left untouched.
    out = tts.script_to_narration_text("In 1973 he gained 300 yards, 134 votes short.")
    assert "nineteen seventy-three" in out
    assert "300" in out and "134" in out
    assert "1973" not in out


def test_spell_numbers_handles_millions_and_skips_decimals_currency():
    assert "one million" in tts._spell_grouped_numbers("1,234,567 fans")
    # decimals + currency left intact (no partial mangling)
    assert tts._spell_grouped_numbers("hit 1,234.56 today") == "hit 1,234.56 today"
    assert tts._spell_grouped_numbers("a $1,234 deal") == "a $1,234 deal"
    # plain comma integer still spelled
    assert "two thousand three" in tts._spell_grouped_numbers("2,003 yards")


def test_split_sentences_protects_abbreviations():
    assert tts._split_sentences("Dr. Smith arrived. He left.") == ["Dr. Smith arrived.", "He left."]
    assert tts._split_sentences("He moved to D.C. with U.S. backing.") == ["He moved to D.C. with U.S. backing."]


def test_split_sentences_breaks_after_sentence_end_initialism():
    # A sentence ending in an initialism + a clear sentence-starter is a real break...
    assert tts._split_sentences("She lives in D.C. She moved.") == ["She lives in D.C.", "She moved."]
    # ...but a name following initials must NOT split (the original O.J. bug).
    assert tts._split_sentences("O.J. Simpson rushed. He scored.") == ["O.J. Simpson rushed.", "He scored."]


def test_year_to_words_paired_decades():
    from engine.video import tts
    assert tts._year_to_words(1984) == "nineteen eighty-four"
    assert tts._year_to_words(1973) == "nineteen seventy-three"
    assert tts._year_to_words(1900) == "nineteen hundred"
    assert tts._year_to_words(1905) == "nineteen oh five"
    assert tts._year_to_words(2003) == "two thousand three"
    assert tts._year_to_words(2000) == "two thousand"
    assert tts._year_to_words(2026) == "twenty twenty-six"
    assert tts._year_to_words(2010) == "twenty ten"


def test_script_to_narration_spells_years():
    from engine.video import tts
    out = tts.script_to_narration_text("In 1984 at Monaco, then 2003 and 2026.")
    assert "nineteen eighty-four" in out
    assert "two thousand three" in out
    assert "twenty twenty-six" in out
    assert "1984" not in out


def test_script_to_narration_leaves_non_years_alone():
    from engine.video import tts
    out = tts.script_to_narration_text("He ran 400 meters; the crowd was 2,003 strong.")
    assert "400" in out
    assert "two thousand three" in out


def test_apply_pronunciation_respells_known_names():
    from engine.video import tts
    out = tts.apply_pronunciation("Jacky Ickx and Jean-Marie Balestre argued.")
    assert "Ickx" not in out
    assert tts._PRONUNCIATION["Ickx"] in out


def test_apply_pronunciation_leaves_unmapped_text_untouched():
    from engine.video import tts
    assert tts.apply_pronunciation("Senna led the race.") == "Senna led the race."


def test_apply_pronunciation_is_word_boundary_safe(monkeypatch):
    from engine.video import tts
    monkeypatch.setitem(tts._PRONUNCIATION, "Lauda", "Lowda")
    tts._pronunciation_re.cache_clear()       # map changed → rebuild the regex
    try:
        out = tts.apply_pronunciation("Laudable Lauda")
        assert "Laudable" in out
    finally:
        tts._PRONUNCIATION.pop("Lauda", None)
        tts._pronunciation_re.cache_clear()   # restore: remove the injected entry


def test_spell_years_handles_ranges():
    from engine.video import tts
    out = tts.script_to_narration_text("From 1984-1988 he raced.")
    assert "nineteen eighty-four to nineteen eighty-eight" in out


def test_spell_years_leaves_decades_alone():
    from engine.video import tts
    out = tts.script_to_narration_text("The 1990s were wild.")
    assert "1990s" in out          # not half-converted to 'nineteen ninety s'


def test_narration_pace_short_is_brisk_and_tight():
    from engine.video import tts
    from engine import config
    speed, gap = tts.narration_pace("short")
    assert speed == config.SHORT_NARRATION_SPEED
    assert gap == config.SHORT_NARRATION_GAP_S
    assert speed > config.NARRATION_SPEED      # brisker than long-form
    assert gap < config.NARRATION_GAP_S        # tighter pauses than long-form


def test_narration_pace_long_uses_calm_defaults():
    from engine.video import tts
    from engine import config
    assert tts.narration_pace("long") == (config.NARRATION_SPEED, config.NARRATION_GAP_S)
    # unknown/None format defaults to long-form (calm)
    assert tts.narration_pace(None) == (config.NARRATION_SPEED, config.NARRATION_GAP_S)
