from engine import config

def test_model_light_default_is_haiku():
    assert config.MODEL_LIGHT == "claude-haiku-4-5"


from engine import usage

class _U:  # minimal usage stub
    input_tokens = 1_000_000
    output_tokens = 1_000_000
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0

def test_haiku_priced_nonzero():
    cost = usage.cost_usd(_U(), "claude-haiku-4-5")
    # 1M input @ $1/M + 1M output @ $5/M = $6.00
    assert round(cost, 2) == 6.00
