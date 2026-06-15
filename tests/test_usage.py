import types

import pytest

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
    assert usage.cost_usd(u, "claude-sonnet-4-6") == pytest.approx(3.00 + 15.00 + 3.75 + 0.30)


def test_cost_usd_unknown_model_is_zero():
    u = _usage(inp=1_000_000, out=1_000_000)
    assert usage.cost_usd(u, "some-future-model") == 0.0


def test_cost_usd_dated_haiku_id_prices_like_alias():
    # The API returns the dated id `claude-haiku-4-5-20251001`, but PRICING is keyed on
    # the alias `claude-haiku-4-5`. The date suffix must be stripped before the lookup.
    u = _usage(inp=1_000_000, out=1_000_000)  # Haiku: $1 input + $5 output per 1M
    assert usage.cost_usd(u, "claude-haiku-4-5-20251001") == pytest.approx(1.00 + 5.00)


def test_cost_usd_haiku_alias_still_prices():
    u = _usage(inp=1_000_000, out=1_000_000)
    assert usage.cost_usd(u, "claude-haiku-4-5") == pytest.approx(1.00 + 5.00)


def test_cost_usd_non_date_suffix_not_stripped():
    # Only an 8-digit date suffix is stripped — an unrelated trailing token must NOT match.
    u = _usage(inp=1_000_000, out=1_000_000)
    assert usage.cost_usd(u, "claude-haiku-4-5-turbo") == 0.0


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


def test_record_dated_haiku_id_logs_nonzero_cost(tmp_path, monkeypatch, capsys):
    # Regression for #58: the dated Haiku id must price correctly, not log $0.
    ledger = tmp_path / "cost.jsonl"
    monkeypatch.setattr(usage, "COST_LEDGER_PATH", str(ledger))
    usage.record(_resp(model="claude-haiku-4-5-20251001", inp=1_000_000, out=1_000_000), "ideate")
    row = _json.loads(ledger.read_text().strip())
    assert row["model"] == "claude-haiku-4-5-20251001"  # ledger keeps the real returned id
    assert row["cost_usd"] == pytest.approx(6.0)         # priced, not $0
    assert "unknown model" not in capsys.readouterr().out  # no false warning


def test_record_genuinely_unknown_model_warns_and_logs_zero(tmp_path, monkeypatch, capsys):
    ledger = tmp_path / "cost.jsonl"
    monkeypatch.setattr(usage, "COST_LEDGER_PATH", str(ledger))
    usage.record(_resp(model="claude-future-9", inp=1_000_000, out=1_000_000), "ideate")
    row = _json.loads(ledger.read_text().strip())
    assert row["cost_usd"] == 0.0
    assert "unknown model" in capsys.readouterr().out


@pytest.mark.parametrize("model, expected", [
    ("claude-haiku-4-5-20251001", "claude-haiku-4-5"),  # dated id → alias
    ("claude-haiku-4-5", "claude-haiku-4-5"),            # alias unchanged
    ("claude-sonnet-4-6", "claude-sonnet-4-6"),          # no date → unchanged
    ("claude-haiku-4-5-turbo", "claude-haiku-4-5-turbo"),  # non-digit suffix kept
    ("claude-haiku-4-5-1234567", "claude-haiku-4-5-1234567"),    # 7 digits, not stripped
    ("claude-haiku-4-5-123456789", "claude-haiku-4-5-123456789"),  # 9 digits, not stripped
    ("claude-x-20241001-20251001", "claude-x-20241001"),  # only the final date stripped
    (None, ""),
    ("", ""),
])
def test_pricing_key_normalization(model, expected):
    assert usage._pricing_key(model) == expected


def test_record_neon_insert_prices_dated_haiku(tmp_path, monkeypatch):
    # The durable Neon api_costs insert also routes through cost_usd — it must price
    # the dated Haiku id correctly, not insert $0 (the path that feeds the monthly cap).
    monkeypatch.setattr(usage, "COST_LEDGER_PATH", str(tmp_path / "c.jsonl"))
    monkeypatch.setattr("engine.config.DATABASE_URL", "postgres://stub", raising=False)
    captured = {}

    class _FakeConn:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def execute(self, sql, params):
            captured["params"] = params

    from engine.queue import neon_backend
    monkeypatch.setattr(neon_backend, "_conn", lambda: _FakeConn())
    usage.record(_resp(model="claude-haiku-4-5-20251001", inp=1_000_000, out=1_000_000), "ideate")
    # params = (stage, run_id, usd)
    assert captured["params"][0] == "ideate"
    assert captured["params"][2] == pytest.approx(6.0)
