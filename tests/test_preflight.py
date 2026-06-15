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


def test_ghost_token_fully_after_audio_is_dropped():
    caps = [{"text": "end.", "startMs": 59000, "endMs": 59500},
            {"text": "the", "startMs": 62000, "endMs": 63000}]   # entirely after audio
    fixed, muts = preflight._fix_past_audio(caps, narration_ms=60000, tol=500)
    assert [c["text"] for c in fixed] == ["end."]
    assert muts == [{"type": "drop", "token": "the", "reason": "ghost_after_audio",
                     "at_ms": 62000}]


def test_straddling_token_is_clamped_not_dropped():
    caps = [{"text": "finish.", "startMs": 59800, "endMs": 61000}]  # straddles 60000
    fixed, muts = preflight._fix_past_audio(caps, narration_ms=60000, tol=500)
    assert fixed[0]["endMs"] == 60000
    assert fixed[0]["startMs"] == 59800
    assert muts[0]["type"] == "clamp" and muts[0]["to"] == [59800, 60000]


def test_clamp_never_creates_negative_duration():
    caps = [{"text": "x", "startMs": 59999, "endMs": 70000}]
    fixed, muts = preflight._fix_past_audio(caps, narration_ms=60000, tol=500)
    assert fixed[0]["endMs"] >= fixed[0]["startMs"]


def test_zero_duration_caption_gets_min_one_frame():
    caps = [{"text": "x", "startMs": 1000, "endMs": 1000}]   # zero duration
    fixed, muts = preflight._fix_min_duration(caps, fps=30)
    assert fixed[0]["endMs"] > fixed[0]["startMs"]
    assert muts[0]["type"] == "retime" and muts[0]["reason"] == "min_frame_duration"


def test_subframe_caption_is_extended():
    caps = [{"text": "x", "startMs": 0, "endMs": 10}]   # <1 frame (33ms) → invisible
    fixed, _ = preflight._fix_min_duration(caps, fps=30)
    assert preflight._frame_index(fixed[0]["endMs"], 30) > preflight._frame_index(0, 30)


def test_healthy_caption_unchanged_by_min_duration():
    caps = [{"text": "x", "startMs": 0, "endMs": 500}]
    fixed, muts = preflight._fix_min_duration(caps, fps=30)
    assert fixed[0]["endMs"] == 500
    assert muts == []


def test_overlap_clamped_to_previous_end():
    caps = [{"text": "a", "startMs": 0, "endMs": 500},
            {"text": "b", "startMs": 300, "endMs": 800}]   # starts before a ends
    fixed, muts = preflight._fix_overlap(caps, fps=30)
    assert fixed[1]["startMs"] == 500
    assert fixed[1]["endMs"] == 800
    assert muts[0]["type"] == "clamp" and muts[0]["reason"] == "non_monotonic"


def test_overlap_clamp_keeps_min_frame_when_inverted():
    caps = [{"text": "a", "startMs": 0, "endMs": 500},
            {"text": "b", "startMs": 300, "endMs": 400}]   # clamp start→500 would invert
    fixed, _ = preflight._fix_overlap(caps, fps=30)
    assert fixed[1]["endMs"] >= fixed[1]["startMs"]


def test_detect_oversize_tokens():
    caps = [{"text": "ok", "startMs": 0, "endMs": 100},
            {"text": "x" * 40, "startMs": 100, "endMs": 200}]
    assert preflight._detect_oversize(caps, max_chars=25) == [1]
