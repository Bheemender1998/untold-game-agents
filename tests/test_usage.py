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


import json as _json


def _resp(model="claude-sonnet-4-6", **u):
    return types.SimpleNamespace(model=model, usage=_usage(**u))


class _FakeClient:
    """Minimal stand-in: .messages.create(**kwargs) returns the queued response."""
    def __init__(self, resp=None, raises=None):
        self._resp, self._raises = resp, raises
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        if self._raises:
            raise self._raises
        return self._resp


def test_record_writes_row(tmp_path, monkeypatch):
    ledger = tmp_path / "cost.jsonl"
    monkeypatch.setattr(usage, "COST_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("TUG_RUN_ID", "run-xyz")
    usage.record(_resp(inp=1_000_000, out=1_000_000), "script_writer")
    row = _json.loads(ledger.read_text().strip())
    assert row["run_id"] == "run-xyz"
    assert row["stage"] == "script_writer"
    assert row["model"] == "claude-sonnet-4-6"
    assert row["cost_usd"] == 18.0  # 3 + 15


def test_record_never_raises_on_bad_response(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "COST_LEDGER_PATH", str(tmp_path / "c.jsonl"))
    bad = types.SimpleNamespace()  # no .usage / .model
    usage.record(bad, "metadata")  # must not raise


def test_logged_create_records_and_returns(tmp_path, monkeypatch):
    ledger = tmp_path / "c.jsonl"
    monkeypatch.setattr(usage, "COST_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("TUG_RUN_ID", "run-1")
    resp = _resp(out=1_000_000)
    client = _FakeClient(resp=resp)
    out = usage.logged_create(client, "thumbnail", model="claude-sonnet-4-6", max_tokens=32)
    assert out is resp
    assert _json.loads(ledger.read_text().strip())["stage"] == "thumbnail"


def test_logged_create_propagates_api_error(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "COST_LEDGER_PATH", str(tmp_path / "c.jsonl"))
    client = _FakeClient(raises=RuntimeError("api down"))
    import pytest
    with pytest.raises(RuntimeError, match="api down"):
        usage.logged_create(client, "ideate", model="claude-sonnet-4-6")
