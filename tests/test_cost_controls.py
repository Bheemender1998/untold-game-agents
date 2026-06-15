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


import inspect
import engine.pipeline.metadata as _meta
import engine.pipeline.subject as _subj
import engine.pipeline.script as _script

def test_light_stages_reference_model_light():
    # short_title + short_desc both route to MODEL_LIGHT
    assert inspect.getsource(_meta).count("MODEL_LIGHT") >= 2
    # subject photo-query routes to MODEL_LIGHT
    assert "MODEL_LIGHT" in inspect.getsource(_subj)
    # companion tease agent sets self.model = config.MODEL_LIGHT
    assert "MODEL_LIGHT" in inspect.getsource(_script)

def test_main_metadata_title_stays_on_sonnet():
    # the main metadata (title/description/tags) call must NOT be downgraded
    src = inspect.getsource(_meta)
    assert 'logged_create(self.client, "metadata"' in src
    # the metadata stage line still uses MODEL (Sonnet), not MODEL_LIGHT
    import re
    block = src[src.index('logged_create(self.client, "metadata"'):]
    head = block[:200]
    assert "MODEL_LIGHT" not in head


from engine import run_cost_report

def test_summarize_neon_totals_and_by_stage():
    rows = [("fact_check", 0.50), ("fact_check", 0.25), ("short_title", 0.01)]
    out = run_cost_report.summarize_neon(rows)
    assert out["total"] == 0.76
    assert out["by_stage"]["fact_check"] == 0.75
    assert out["by_stage"]["short_title"] == 0.01

def test_summarize_neon_empty():
    out = run_cost_report.summarize_neon([])
    assert out["total"] == 0.0 and out["by_stage"] == {}
