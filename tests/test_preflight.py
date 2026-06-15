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


def test_merge_punct_captions_fixes_split_number():
    caps = [
        {"text": "worth", "startMs": 120220, "endMs": 120540},
        {"text": "$1", "startMs": 120540, "endMs": 121020},
        {"text": ",000", "startMs": 121020, "endMs": 121880},
        {"text": ",000.", "startMs": 121880, "endMs": 121880},
        {"text": "Six", "startMs": 121880, "endMs": 122120},
    ]
    fixed, muts = preflight._fix_punct_captions(caps)
    texts = [c["text"] for c in fixed]
    assert texts == ["worth", "$1,000,000.", "Six"]
    assert fixed[1]["endMs"] == 121880          # endMs extended to the swallowed token
    assert any(m["type"] == "merge" and m["into"] == "$1,000,000." for m in muts)


def test_merge_punct_leaves_clean_captions_untouched():
    caps = [{"text": "the", "startMs": 0, "endMs": 100},
            {"text": "race", "startMs": 100, "endMs": 300}]
    fixed, muts = preflight._fix_punct_captions(caps)
    assert [c["text"] for c in fixed] == ["the", "race"]
    assert muts == []


def test_drop_fillers_removes_um_and_logs_mutation():
    caps = [{"text": "and", "startMs": 0, "endMs": 100},
            {"text": "um", "startMs": 100, "endMs": 260},
            {"text": "then", "startMs": 300, "endMs": 500}]
    fixed, muts = preflight._fix_fillers(caps, ("um", "uh"))
    assert [c["text"] for c in fixed] == ["and", "then"]
    assert muts == [{"type": "drop", "token": "um", "reason": "filler", "at_ms": 100}]
