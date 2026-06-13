from engine.video import captions


def _w(word, start, end):
    return {"word": word, "start": start, "end": end}


def test_digitize_collapses_year_words():
    words = [_w("In", 0.0, 0.2), _w("nineteen", 0.2, 0.6), _w("eighty-four", 0.6, 1.1),
             _w("Monaco", 1.1, 1.6)]
    out = captions.digitize_number_words(words)
    assert [w["word"] for w in out] == ["In", "1984", "Monaco"]
    assert out[1]["start"] == 0.2 and out[1]["end"] == 1.1


def test_digitize_collapses_two_thousand_form():
    words = [_w("by", 0.0, 0.2), _w("two", 0.2, 0.4), _w("thousand", 0.4, 0.8),
             _w("three", 0.8, 1.0)]
    out = captions.digitize_number_words(words)
    assert [w["word"] for w in out] == ["by", "2003"]


def test_digitize_leaves_non_numbers_untouched():
    words = [_w("Senna", 0.0, 0.4), _w("led", 0.4, 0.6)]
    out = captions.digitize_number_words(words)
    assert [w["word"] for w in out] == ["Senna", "led"]


def test_digitize_preserves_trailing_punctuation():
    words = [_w("in", 0.0, 0.2), _w("nineteen", 0.2, 0.6), _w("eighty-four.", 0.6, 1.1)]
    out = captions.digitize_number_words(words)
    assert out[1]["word"] == "1984."
