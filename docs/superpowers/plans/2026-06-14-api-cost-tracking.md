# API Cost Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture Anthropic token usage at every engine call site, append a priced row to a JSONL ledger, and print a per-run cost summary (with a $10 warn-only budget alert) into the overnight log.

**Architecture:** A new `engine/usage.py` exposes `logged_create(client, stage, **kwargs)` — a drop-in wrapper around `client.messages.create` that records `resp.usage` to `logs/api-cost.jsonl`. Recording is best-effort and never raises (a cost-tracking failure must never crash a production run). `engine/run_cost_report.py` aggregates the ledger by `TUG_RUN_ID` and prints a summary; `scripts/overnight.sh` stamps the run id and calls the reporter at the end.

**Tech Stack:** Python 3 (main env, not `.venv-video`), `anthropic` SDK, pytest. Model is `claude-sonnet-4-6` ($3/1M input, $15/1M output; cache write 1.25×, cache read 0.10×).

**Spec:** `docs/superpowers/specs/2026-06-14-api-cost-tracking-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `engine/config.py` | +`COST_ALERT_USD`, +`COST_LEDGER_PATH` constants |
| `engine/usage.py` | **new** — pricing table, `cost_usd`, `record`, `logged_create` |
| `engine/run_cost_report.py` | **new** — aggregate ledger by run, print summary + budget warning |
| `engine/ideate/base_agent.py` | route `_call` through `logged_create` (stage = `self.name`) |
| `engine/pipeline/fact_gate.py` | route through `logged_create` (stage `fact_check`) |
| `engine/pipeline/metadata.py` | 3 call sites → `metadata` / `short_title` / `short_desc` |
| `engine/video/compose.py` | 2 call sites → `storyboard` / `headlines` |
| `engine/pipeline/thumbnail.py` | 1 call site → `thumbnail` |
| `scripts/overnight.sh` | export `TUG_RUN_ID`; append `run_cost_report` call |
| `tests/test_usage.py` | **new** — pricing, ledger write, self-stub, error propagation |
| `tests/test_run_cost_report.py` | **new** — aggregation by run, threshold warning |
| `CLAUDE.md` | document the `run_cost_report` entrypoint |

**Stage labels (final):** `self.name` for everything through `base_agent._call`
(`sports_history_agent`, `trending_topics_agent`, `competitor_gap_agent`,
`evergreen_agent`, `script_writer`, `short_script_writer`, `companion_tease_writer`),
plus `fact_check`, `metadata`, `short_title`, `short_desc`, `storyboard`,
`headlines`, `thumbnail` for the direct-`messages.create` sites.

---

### Task 1: Config constants

**Files:**
- Modify: `engine/config.py` (after the `MODEL` / `MAX_TOKENS` block, ~line 18)

- [ ] **Step 1: Add the two constants**

In `engine/config.py`, immediately after the line `MAX_TOKENS = 8192 ...`, add:

```python

# ── API cost tracking ─────────────────────────────────────────────────────────
COST_LEDGER_PATH = "logs/api-cost.jsonl"  # one priced JSON row per Anthropic call
COST_ALERT_USD = 10.0                     # per-run budget alert (warn-only, never blocks)
```

- [ ] **Step 2: Verify it imports**

Run: `python3 -c "from engine.config import COST_ALERT_USD, COST_LEDGER_PATH; print(COST_ALERT_USD, COST_LEDGER_PATH)"`
Expected: `10.0 logs/api-cost.jsonl`

- [ ] **Step 3: Commit**

```bash
git add engine/config.py
git commit -m "feat(cost): add COST_ALERT_USD + COST_LEDGER_PATH config"
```

---

### Task 2: `cost_usd` pricer

**Files:**
- Create: `engine/usage.py`
- Test: `tests/test_usage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_usage.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_usage.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.usage'`

- [ ] **Step 3: Write minimal implementation**

Create `engine/usage.py`:

```python
"""
API cost tracking — prices each Anthropic response and appends to a JSONL ledger.

Wrap every messages.create call site in logged_create(...) so resp.usage is
captured. Recording is best-effort and never raises (self-stub rule): a cost-
tracking failure must never crash a production run.
See docs/superpowers/specs/2026-06-14-api-cost-tracking-design.md.
"""
from __future__ import annotations

import datetime
import json
import os

from engine.config import COST_LEDGER_PATH

# Per-token USD, from the claude-api reference (2026-06): Sonnet 4.6 is
# $3/1M input, $15/1M output; cache writes 1.25x input, cache reads 0.10x input.
PRICING = {
    "claude-sonnet-4-6": {
        "input":       3.00 / 1_000_000,
        "output":     15.00 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
        "cache_read":  0.30 / 1_000_000,
    },
}


def cost_usd(usage, model: str) -> float:
    """USD for one response's usage. Unknown model -> 0.0 (caller logs a warning)."""
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    return (
        (getattr(usage, "input_tokens", 0) or 0) * rates["input"]
        + (getattr(usage, "output_tokens", 0) or 0) * rates["output"]
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * rates["cache_write"]
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * rates["cache_read"]
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_usage.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/usage.py tests/test_usage.py
git commit -m "feat(cost): add usage.cost_usd pricer for Sonnet 4.6"
```

---

### Task 3: `record` + `logged_create`

**Files:**
- Modify: `engine/usage.py`
- Test: `tests/test_usage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_usage.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_usage.py -q`
Expected: FAIL — `AttributeError: module 'engine.usage' has no attribute 'record'`

- [ ] **Step 3: Write the implementation**

Append to `engine/usage.py`:

```python
def _run_id() -> str:
    return os.environ.get("TUG_RUN_ID") or ("adhoc-" + datetime.date.today().isoformat())


def record(resp, stage: str) -> None:
    """Append one priced ledger row for a response. Best-effort; never raises."""
    try:
        u = resp.usage
        model = getattr(resp, "model", "") or ""
        if model not in PRICING:
            print(f"cost-track warning: unknown model {model!r}; logged $0")
        row = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "run_id": _run_id(),
            "stage": stage,
            "model": model,
            "input_tokens": getattr(u, "input_tokens", 0) or 0,
            "output_tokens": getattr(u, "output_tokens", 0) or 0,
            "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cost_usd": round(cost_usd(u, model), 6),
        }
        with open(COST_LEDGER_PATH, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as e:  # cost tracking must never crash a run
        print(f"cost-track warning: {e}")


def logged_create(client, stage: str, **kwargs):
    """client.messages.create(**kwargs) with usage recorded to the ledger.

    The API call itself is NOT wrapped — real API errors propagate unchanged.
    Only the recording is best-effort.
    """
    resp = client.messages.create(**kwargs)
    record(resp, stage)
    return resp
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_usage.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/usage.py tests/test_usage.py
git commit -m "feat(cost): record() + logged_create() ledger writer (self-stubbing)"
```

---

### Task 4: `run_cost_report` aggregator

**Files:**
- Create: `engine/run_cost_report.py`
- Test: `tests/test_run_cost_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_cost_report.py`:

```python
import json

from engine import run_cost_report as rcr


def _seed(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_summarize_filters_by_run(tmp_path):
    led = tmp_path / "c.jsonl"
    _seed(led, [
        {"run_id": "A", "stage": "script_writer", "input_tokens": 1000,
         "output_tokens": 2000, "cache_creation_input_tokens": 0,
         "cache_read_input_tokens": 0, "cost_usd": 3.0},
        {"run_id": "A", "stage": "script_writer", "input_tokens": 0,
         "output_tokens": 0, "cache_creation_input_tokens": 0,
         "cache_read_input_tokens": 0, "cost_usd": 1.0},
        {"run_id": "B", "stage": "metadata", "input_tokens": 5, "output_tokens": 5,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "cost_usd": 99.0},
    ])
    agg = rcr.summarize(list(rcr._rows(str(led))), "A")
    assert set(agg) == {"script_writer"}
    assert agg["script_writer"]["calls"] == 2
    assert agg["script_writer"]["cost"] == 4.0


def test_render_total_no_warning_under_cap(monkeypatch):
    monkeypatch.setattr(rcr.config, "COST_ALERT_USD", 10.0)
    agg = {"metadata": {"calls": 1, "input": 1000, "output": 2000, "cost": 5.0}}
    out = rcr.render(agg, "A")
    assert "TOTAL" in out
    assert "$5.00" in out
    assert "BUDGET" not in out


def test_render_warning_over_cap(monkeypatch):
    monkeypatch.setattr(rcr.config, "COST_ALERT_USD", 10.0)
    agg = {"script_writer": {"calls": 3, "input": 1, "output": 1, "cost": 12.4}}
    out = rcr.render(agg, "A")
    assert "BUDGET" in out
    assert "$12.40 exceeds $10.00" in out


def test_render_empty_says_no_data():
    out = rcr.render({}, "A")
    assert "no cost data" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_run_cost_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.run_cost_report'`

- [ ] **Step 3: Write the implementation**

Create `engine/run_cost_report.py`:

```python
"""
Aggregate the API cost ledger (logs/api-cost.jsonl) by run and print a per-stage
summary plus a budget warning if a run exceeds config.COST_ALERT_USD. Reporter
only — always exits 0; never gates a run.
See docs/superpowers/specs/2026-06-14-api-cost-tracking-design.md.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os

from engine import config


def _rows(path: str):
    """Yield parsed ledger rows; skip malformed lines; tolerate a missing file."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    print("cost-report warning: skipping malformed ledger line")
    except (FileNotFoundError, OSError):
        return


def summarize(rows, run_id: str) -> dict:
    """Group this run's rows by stage -> {calls, input, output, cost}."""
    agg = collections.defaultdict(
        lambda: {"calls": 0, "input": 0, "output": 0, "cost": 0.0}
    )
    for r in rows:
        if r.get("run_id") != run_id:
            continue
        s = agg[r.get("stage", "?")]
        s["calls"] += 1
        s["input"] += (r.get("input_tokens", 0)
                       + r.get("cache_creation_input_tokens", 0)
                       + r.get("cache_read_input_tokens", 0))
        s["output"] += r.get("output_tokens", 0)
        s["cost"] += r.get("cost_usd", 0.0)
    return dict(agg)


def render(agg: dict, run_id: str) -> str:
    header = f"── API cost — run {run_id} ──"
    if not agg:
        return header + "\n  no cost data for this run"
    lines = [header]
    total_calls = 0
    total_cost = 0.0
    for stage in sorted(agg):
        s = agg[stage]
        total_calls += s["calls"]
        total_cost += s["cost"]
        lines.append(
            f"  {stage:<16}{s['calls']:>3} calls  "
            f"{s['input'] // 1000:>5}k in {s['output'] // 1000:>5}k out  ${s['cost']:.2f}"
        )
    lines.append("  " + "─" * 51)
    lines.append(f"  {'TOTAL':<16}{total_calls:>3} calls{'':>20}${total_cost:.2f}")
    if total_cost > config.COST_ALERT_USD:
        lines.append(
            f"⚠️  BUDGET: run cost ${total_cost:.2f} "
            f"exceeds ${config.COST_ALERT_USD:.2f} cap"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Summarize API cost for an automation run.")
    p.add_argument("--run", default=None,
                   help="run_id to summarize (default: $TUG_RUN_ID or today's adhoc id)")
    args = p.parse_args(argv)
    run_id = (args.run or os.environ.get("TUG_RUN_ID")
              or ("adhoc-" + datetime.date.today().isoformat()))
    agg = summarize(_rows(config.COST_LEDGER_PATH), run_id)
    print(render(agg, run_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_run_cost_report.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Smoke-test the CLI on an empty ledger**

Run: `python3 -m engine.run_cost_report --run does-not-exist`
Expected: prints `── API cost — run does-not-exist ──` then `  no cost data for this run`, exits 0.

- [ ] **Step 6: Commit**

```bash
git add engine/run_cost_report.py tests/test_run_cost_report.py
git commit -m "feat(cost): run_cost_report — per-run summary + budget warning"
```

---

### Task 5: Wire the 8 call sites through `logged_create`

No new tests — this is a mechanical swap; the full suite + an import smoke guard it. Each edit prepends `client` and a stage string to an existing keyword-only `messages.create` call.

**Files:**
- Modify: `engine/ideate/base_agent.py`
- Modify: `engine/pipeline/fact_gate.py`
- Modify: `engine/pipeline/metadata.py`
- Modify: `engine/video/compose.py`
- Modify: `engine/pipeline/thumbnail.py`

- [ ] **Step 1: `base_agent.py` — import + swap (stage = `self.name`)**

After line 15 (`from engine.ideate.web_search import ...`), add:

```python
from engine.usage import logged_create
```

Replace line 58:

```python
            response = self.client.messages.create(**kwargs)
```

with:

```python
            response = logged_create(self.client, self.name, **kwargs)
```

- [ ] **Step 2: `fact_gate.py` — import + swap (stage `fact_check`)**

After line 26 (`from engine.ideate.web_search import search as web_search`), add:

```python
from engine.usage import logged_create
```

Replace the call at line 32 (`resp = _client.messages.create(`) so the opening line reads:

```python
    resp = logged_create(
        _client, "fact_check",
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
```

- [ ] **Step 3: `metadata.py` — import + 3 swaps**

After line 14 (`from engine.config import MODEL, MAX_TOKENS`), add:

```python
from engine.usage import logged_create
```

Replace `response = self.client.messages.create(` (line 76) → `response = logged_create(self.client, "metadata",`
Replace `resp = client.messages.create(` (line 118, in `_short_title_llm`) → `resp = logged_create(client, "short_title",`
Replace `resp = client.messages.create(` (line 164, in `_short_desc_llm`) → `resp = logged_create(client, "short_desc",`

(Each keeps its existing `model=..., max_tokens=..., ...` arguments unchanged on the following lines.)

- [ ] **Step 4: `compose.py` — import + 2 swaps**

Add near the other engine imports at the top of the file:

```python
from engine.usage import logged_create
```

Replace `resp = client.messages.create(` (line 67, in `build_storyboard`) → `resp = logged_create(client, "storyboard",`
Replace `resp = client.messages.create(` (line 281, in `build_section_headlines`) → `resp = logged_create(client, "headlines",`

- [ ] **Step 5: `thumbnail.py` — import + 1 swap**

Add near the top imports:

```python
from engine.usage import logged_create
```

Replace `resp = client.messages.create(` (line 201, in `_thumbnail_text_llm`) → `resp = logged_create(client, "thumbnail",`

- [ ] **Step 6: Import smoke + full suite**

Run: `python3 -c "import engine.ideate.base_agent, engine.pipeline.fact_gate, engine.pipeline.metadata, engine.video.compose, engine.pipeline.thumbnail; print('imports ok')"`
Expected: `imports ok`

Run: `python3 -m pytest tests/ -q`
Expected: PASS (all existing tests + the new cost tests).

- [ ] **Step 7: Commit**

```bash
git add engine/ideate/base_agent.py engine/pipeline/fact_gate.py engine/pipeline/metadata.py engine/video/compose.py engine/pipeline/thumbnail.py
git commit -m "feat(cost): route all 8 Anthropic call sites through logged_create"
```

---

### Task 6: Overnight run id + reporter call + docs

**Files:**
- Modify: `scripts/overnight.sh`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Stamp a run id in `overnight.sh`**

In `scripts/overnight.sh`, after the `if [ -f .env ]; ... fi` line (env load) and before `mkdir -p logs`, add:

```bash

# One id ties every API call in tonight's run together for the cost report.
export TUG_RUN_ID="$(date +%Y-%m-%dT%H:%M:%S)"
```

- [ ] **Step 2: Append the reporter to the logged block**

In the same file, inside the `{ ... } >>"$LOG" 2>&1` block, change the tail from:

```bash
  python3 -m engine.run_auto --count 3 || echo "(run_auto exited $? — see above)"
  echo "=== done $(date) ==="
```

to:

```bash
  python3 -m engine.run_auto --count 3 || echo "(run_auto exited $? — see above)"
  echo "-- API cost summary for this run --"
  python3 -m engine.run_cost_report --run "$TUG_RUN_ID" || true
  echo "=== done $(date) ==="
```

- [ ] **Step 3: Verify the script still parses**

Run: `bash -n scripts/overnight.sh && echo "syntax ok"`
Expected: `syntax ok`

- [ ] **Step 4: Document the entrypoint in `CLAUDE.md`**

In the `## Entrypoints` fenced block, after the `run_banner` line, add:

```bash
python3 -m engine.run_cost_report [--run <id>]  # per-run API cost summary from logs/api-cost.jsonl (overnight.sh runs this automatically; warns if a run exceeds COST_ALERT_USD=$10)
```

- [ ] **Step 5: Commit**

```bash
git add scripts/overnight.sh CLAUDE.md
git commit -m "feat(cost): stamp TUG_RUN_ID + emit cost summary in overnight run; docs"
```

---

## Self-Review notes

- **Spec coverage:** ledger (Task 3), per-run summary (Task 4), $10 warn-only alert
  (Task 4 `render`), run-id grouping (Tasks 3+6), all 8 call sites (Task 5), config
  constants (Task 1), overnight wiring (Task 6), docs (Task 6), tests (Tasks 2–4). ✅
- **Stage naming** is consistent: `logged_create(client, stage, **kwargs)` everywhere;
  `self.name` for `_call`, explicit strings for the 6 direct sites.
- **Self-stub:** `record` wraps everything in `try/except Exception`; the `messages.create`
  call in `logged_create` is deliberately outside the try so API errors propagate
  (test `test_logged_create_propagates_api_error`).
- **Ledger path** is patched per-test via `monkeypatch.setattr(usage, "COST_LEDGER_PATH", ...)`;
  production path `logs/api-cost.jsonl` exists because `overnight.sh` runs `mkdir -p logs`
  and the repo already tracks `logs/.gitkeep`.
```
