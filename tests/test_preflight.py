from engine.video import preflight


def test_needs_left_merge_detects_continuation_and_punct():
    assert preflight._needs_left_merge(",000") is True
    assert preflight._needs_left_merge(",000.") is True
    assert preflight._needs_left_merge(".") is True
    assert preflight._needs_left_merge("%") is True
    assert preflight._needs_left_merge("") is True
    assert preflight._needs_left_merge("million.") is False
    assert preflight._needs_left_merge("$1") is False


def test_join_space_glues_punct_without_space_and_words_with_space():
    assert preflight._join_space("$1", ",000") == "$1,000"
    assert preflight._join_space("$1,000", ",000.") == "$1,000,000."
    assert preflight._join_space("the", "race") == "the race"
