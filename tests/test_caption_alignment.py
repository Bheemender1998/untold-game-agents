from engine.video import captions


def _ww(pairs):  # [(word, start, end), ...] -> whisper word dicts
    return [{"word": w, "start": s, "end": e} for w, s, e in pairs]


def test_replaces_misheard_word_with_script_text_keeping_timing():
    whisper = _ww([("Coach", 0.0, 0.4), ("Eber", 0.4, 0.9), ("understood", 0.9, 1.5)])
    out = captions.align_to_script(whisper, "Coach Iba understood")
    assert [w["word"] for w in out] == ["Coach", "Iba", "understood"]
    assert out[1]["start"] == 0.4 and out[1]["end"] == 0.9
    assert all(out[i]["start"] <= out[i + 1]["start"] for i in range(len(out) - 1))


def test_interpolates_word_whisper_dropped():
    whisper = _ww([("He", 0.0, 0.2), ("went", 0.2, 0.6), ("Munich", 0.6, 1.2)])
    out = captions.align_to_script(whisper, "He went to Munich")
    assert [w["word"] for w in out] == ["He", "went", "to", "Munich"]
    assert 0.2 <= out[2]["start"] <= out[3]["start"] <= 1.2


def test_drops_whisper_words_not_in_script():
    whisper = _ww([("The", 0.0, 0.2), ("um", 0.2, 0.4), ("end", 0.4, 0.8)])
    out = captions.align_to_script(whisper, "The end")
    assert [w["word"] for w in out] == ["The", "end"]


def test_multiword_equal_block_keeps_per_word_whisper_timing():
    # The common case: whisper transcribes a run of words correctly, so SequenceMatcher
    # returns ONE big "equal" block. Each script word must keep its OWN whisper start/end —
    # NOT a char-length spread across the block span — so real pacing and the inter-word
    # silences (dramatic pauses) survive. (Regression: the block was flattened to a
    # contiguous char-weighted spread ≈ estimate_word_timings, desyncing every caption.)
    whisper = _ww([
        ("They", 0.00, 0.25),
        ("won.", 0.30, 0.70),     # small gap before
        ("Every", 1.50, 1.80),    # 0.80s dramatic pause before
        ("game", 1.82, 2.00),
    ])
    out = captions.align_to_script(whisper, "They won. Every game")
    assert [w["word"] for w in out] == ["They", "won.", "Every", "game"]
    for o, (s, e) in zip(out, [(0.00, 0.25), (0.30, 0.70), (1.50, 1.80), (1.82, 2.00)]):
        assert abs(o["start"] - s) < 1e-6 and abs(o["end"] - e) < 1e-6, o
    # the 0.80s pause before "Every" must survive (was collapsed to ~0 by the bug)
    assert out[2]["start"] - out[1]["end"] > 0.5


def test_distributes_timing_across_multi_word_replace():
    whisper = _ww([("USA", 0.0, 1.0)])
    out = captions.align_to_script(whisper, "U.S. A")
    assert [w["word"] for w in out] == ["U.S.", "A"]
    assert out[0]["start"] == 0.0 and out[-1]["end"] == 1.0
    assert out[0]["end"] == out[1]["start"]


def test_two_separate_deleted_words_stay_monotonic():
    # script has "x" (after A) and "y" (after B) that whisper dropped; they must NOT both land
    # in the A->B gap. Timestamps must be non-decreasing and each near its real neighbours.
    whisper = [{"word": "A", "start": 0.0, "end": 0.2},
               {"word": "B", "start": 0.4, "end": 0.6},
               {"word": "C", "start": 0.8, "end": 1.0}]
    out = captions.align_to_script(whisper, "A x B y C")
    assert [w["word"] for w in out] == ["A", "x", "B", "y", "C"]
    starts = [w["start"] for w in out]
    assert starts == sorted(starts)                    # strictly monotonic order
    assert out[1]["start"] < out[2]["start"]           # x before B
    assert out[3]["start"] > out[2]["start"]           # y AFTER B


def test_empty_inputs_fall_back():
    assert captions.align_to_script([], "anything") == []
    w = _ww([("hi", 0.0, 0.3)])
    assert captions.align_to_script(w, "") == w
