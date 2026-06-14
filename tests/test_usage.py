import types

from engine import usage


def _usage(inp=0, out=0, cw=0, cr=0):
    return types.SimpleNamespace(
        input_tokens=inp,
        output_tokens=out,
        cache_creation_input_tokens=cw,
        cache_read_input_tokens=cr,
    )


def test_cost_usd_known_model():
    # 1M input @ $3, 1M output @ $15, 1M cache-write @ $3.75, 1M cache-read @ $0.30
    u = _usage(inp=1_000_000, out=1_000_000, cw=1_000_000, cr=1_000_000)
    assert usage.cost_usd(u, "claude-sonnet-4-6") == 3.00 + 15.00 + 3.75 + 0.30


def test_cost_usd_unknown_model_is_zero():
    u = _usage(inp=1_000_000, out=1_000_000)
    assert usage.cost_usd(u, "some-future-model") == 0.0
