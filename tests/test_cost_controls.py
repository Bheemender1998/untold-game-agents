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


from engine.ideate import base_agent

def test_base_agent_default_model_is_config_model():
    assert base_agent.BaseAgent().model == config.MODEL

def test_call_uses_self_model(monkeypatch):
    captured = {}
    class _Block:  type = "text"; text = "ok"
    class _Usage:  input_tokens = 1; output_tokens = 1; cache_creation_input_tokens = 0; cache_read_input_tokens = 0
    class _Resp:
        content = [_Block()]; stop_reason = "end_turn"; model = "x"; usage = _Usage()
    def fake_logged_create(client, name, **kwargs):
        captured.update(kwargs); return _Resp()
    monkeypatch.setattr(base_agent, "logged_create", fake_logged_create)
    a = base_agent.BaseAgent()
    a.system_prompt = "s"
    a.model = "custom-model-x"
    a._call("hi", use_search=False)
    assert captured["model"] == "custom-model-x"
