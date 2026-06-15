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


def test_dedup_adjacent_headlines_merges_spans():
    ch = [{"headline": "THE FALL", "startMs": 0, "endMs": 1000},
          {"headline": "the fall", "startMs": 1000, "endMs": 2500},
          {"headline": "AFTER", "startMs": 2500, "endMs": 4000}]
    fixed, muts = preflight._fix_dup_headlines(ch)
    assert [c["headline"] for c in fixed] == ["THE FALL", "AFTER"]
    assert fixed[0]["endMs"] == 2500
    assert muts[0]["reason"] == "dup_headline"


def test_headline_overlap_clamped():
    ch = [{"headline": "A", "startMs": 0, "endMs": 5000},
          {"headline": "B", "startMs": 4000, "endMs": 9000}]
    fixed, muts = preflight._fix_headline_overlap(ch)
    assert fixed[1]["startMs"] == 5000
    assert muts[0]["reason"] == "headline_overlap"


def test_detect_stuck_headlines():
    ch = [{"headline": "A", "startMs": 0, "endMs": 80_000}]   # 80s > 70s default
    assert preflight._detect_stuck_headlines(ch, max_s=70.0) == [0]


def _props(caps, ch, narration_ms=200000, fps=30):
    return {"audioSrc": "narration.wav", "narrationMs": narration_ms, "fps": fps,
            "captions": caps, "chapters": ch}


def test_lint_props_fixes_and_passes():
    caps = [{"text": "$1", "startMs": 1000, "endMs": 1480},
            {"text": ",000", "startMs": 1480, "endMs": 2000},
            {"text": ",000.", "startMs": 2000, "endMs": 2000}]   # split number + zero dur
    ch = [{"headline": "A", "startMs": 0, "endMs": 5000}]
    fixed, report = preflight.lint_props(_props(caps, ch), fps=30, narration_ms=200000)
    assert [c["text"] for c in fixed["captions"]] == ["$1,000,000."]
    assert report["blocked"] is False
    assert report["passed"] is True
    assert any(m["type"] == "merge" for m in report["mutations"])


def test_lint_props_blocks_on_unfixable_structural():
    fixed, report = preflight.lint_props(
        {"audioSrc": "", "narrationMs": 0, "fps": 30, "captions": [], "chapters": []},
        fps=30, narration_ms=0)
    assert report["blocked"] is True
    assert any(c["name"] == "structural" and not c["passed"] for c in report["checks"])


def test_lint_props_does_not_mutate_input():
    caps = [{"text": ",000", "startMs": 1000, "endMs": 2000}]
    src = _props(caps, [{"headline": "A", "startMs": 0, "endMs": 5000}])
    preflight.lint_props(src, fps=30, narration_ms=200000)
    assert src["captions"][0]["text"] == ",000"   # original untouched (deep-copied)


# ── Adversarial-review regression tests (Codex findings, 2026-06-15) ──

def test_needs_left_merge_keeps_opening_quote_word():
    # An opening-quote word must NOT be swallowed (would corrupt 'said' + '"No"' → 'said"No"').
    assert preflight._needs_left_merge('"No"') is False
    assert preflight._needs_left_merge("“Yes”") is False
    assert preflight._needs_left_merge('"') is True       # a bare quote is still a continuation
    assert preflight._needs_left_merge(".50") is True     # punct + digits, no letters → merge


def test_opening_quote_word_not_merged():
    caps = [{"text": "said", "startMs": 0, "endMs": 300},
            {"text": '"No"', "startMs": 300, "endMs": 600}]
    fixed, muts = preflight._fix_punct_captions(caps)
    assert [c["text"] for c in fixed] == ["said", '"No"']
    assert muts == []


def test_leading_orphan_punct_is_dropped():
    caps = [{"text": ",000", "startMs": 0, "endMs": 500},
            {"text": "fans", "startMs": 500, "endMs": 900}]
    fixed, muts = preflight._fix_punct_captions(caps)
    assert [c["text"] for c in fixed] == ["fans"]
    assert muts == [{"type": "drop", "token": ",000", "reason": "orphan_punct", "at_ms": 0}]


def test_zero_duration_ghost_in_grace_zone_is_dropped_not_clamped():
    # Starts after audio (within tol) AND zero-duration: must drop, not clamp-then-bump-past-audio.
    caps = [{"text": "x", "startMs": 1490, "endMs": 1490}]
    fixed, muts = preflight._fix_past_audio(caps, narration_ms=1000, tol=500)
    assert fixed == []
    assert muts[0]["reason"] == "ghost_after_audio"


def test_overlap_clamp_leaves_at_least_one_frame():
    # Tight overlap whose clamp would land both ends in the same frame must be extended.
    caps = [{"text": "a", "startMs": 0, "endMs": 117},
            {"text": "b", "startMs": 90, "endMs": 120}]
    fixed, _ = preflight._fix_overlap(caps, fps=30)
    assert preflight._frame_index(fixed[1]["endMs"], 30) > preflight._frame_index(fixed[1]["startMs"], 30)


def test_lint_props_ordering_does_not_spuriously_block():
    # The min-duration → overlap interaction must auto-resolve, not block.
    caps = [{"text": "a", "startMs": 0, "endMs": 117},
            {"text": "b", "startMs": 90, "endMs": 120}]
    ch = [{"headline": "A", "startMs": 0, "endMs": 5000}]
    props = {"audioSrc": "n.wav", "narrationMs": 200000, "fps": 30, "captions": caps, "chapters": ch}
    _, report = preflight.lint_props(props, fps=30, narration_ms=200000)
    assert report["blocked"] is False


def test_digit_only_quoted_word_not_merged():
    # Codex round-2: '"42"' has no letters but is a standalone quoted number, not a
    # continuation — must NOT be swallowed into the previous word.
    assert preflight._needs_left_merge('"42"') is False
    caps = [{"text": "said", "startMs": 0, "endMs": 300},
            {"text": '"42"', "startMs": 300, "endMs": 600}]
    fixed, muts = preflight._fix_punct_captions(caps)
    assert [c["text"] for c in fixed] == ["said", '"42"']
    assert muts == []


def test_contraction_clitic_merges_left():
    # Codex round-2: a split contraction clitic must glue back with no space.
    assert preflight._needs_left_merge("'s") is True
    assert preflight._needs_left_merge("’re") is True
    assert preflight._join_space("it", "'s") == "it's"
    caps = [{"text": "it", "startMs": 0, "endMs": 200},
            {"text": "'s", "startMs": 200, "endMs": 400}]
    fixed, _ = preflight._fix_punct_captions(caps)
    assert [c["text"] for c in fixed] == ["it's"]
