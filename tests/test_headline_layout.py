from engine.video import compose


def _h(headline, s, e):
    return {"headline": headline, "start": s, "end": e}


def test_merges_consecutive_duplicate_headlines():
    hs = [_h("IBA VS THE SOVIETS", 0.0, 5.0), _h("IBA VS THE SOVIETS", 5.0, 6.0),
          _h("THE FINAL SECONDS", 6.0, 12.0)]
    out = compose._dedup_and_clamp_headlines(hs, total_s=12.0)
    assert [h["headline"] for h in out] == ["IBA VS THE SOVIETS", "THE FINAL SECONDS"]
    assert out[0]["start"] == 0.0 and out[0]["end"] == 6.0


def test_sub_floor_headline_merges_into_neighbour():
    hs = [_h("A", 0.0, 8.0), _h("B", 8.0, 9.0), _h("C", 9.0, 15.0)]
    out = compose._dedup_and_clamp_headlines(hs, total_s=15.0)
    assert all(h["end"] - h["start"] >= compose.HEADLINE_MIN_S for h in out)
    assert [h["headline"] for h in out] == ["A", "C"]


def test_well_spaced_headlines_untouched():
    hs = [_h("A", 0.0, 6.0), _h("B", 6.0, 12.0)]
    out = compose._dedup_and_clamp_headlines(hs, total_s=12.0)
    assert out == hs
