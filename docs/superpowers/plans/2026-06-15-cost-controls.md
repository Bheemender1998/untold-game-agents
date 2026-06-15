# Cost Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route four mechanical pipeline stages to the cheaper Haiku model, price Haiku correctly in the cost ledger, and add a Neon-aware cost readout so the Railway cron's spend (Neon-only) is visible.

**Architecture:** A second config knob `MODEL_LIGHT` (Haiku 4.5); the four light call sites pass it explicitly, and `companion_tease_writer` routes via a new `BaseAgent.self.model` hook. `usage.py` gains a Haiku pricing row. `run_cost_report` gains a pure `summarize_neon()` + a `--neon` flag.

**Tech Stack:** Python 3 (main env), Anthropic SDK, psycopg/Neon (read-only), existing `engine/usage.py` ledger.

**Spec:** `docs/superpowers/specs/2026-06-15-cost-controls-design.md`

**Conventions:** `python3`; absolute `engine.*` imports; after editing `engine/**.py` run `python3 -m pytest tests/ -q`. KNOWN-FLAKY (ignore): `tests/test_fact_gate_oracle.py::test_oracle_flags_known_errors_and_supports_correct` (live Anthropic call); always check the suite with `--deselect tests/test_fact_gate_oracle.py::test_oracle_flags_known_errors_and_supports_correct`. Branch is already `feat/cost-controls`. Ship via `ship-video-change` after the plan.

---

## File structure

| File | Change |
|------|--------|
| `engine/config.py` | Add `MODEL_LIGHT` |
| `engine/usage.py` | Add `claude-haiku-4-5` to `PRICING` |
| `engine/ideate/base_agent.py` | `self.model` hook (default `config.MODEL`); `_call` uses `self.model` |
| `engine/pipeline/metadata.py` | `short_title` + `short_desc` → `MODEL_LIGHT` |
| `engine/pipeline/subject.py` | subject photo-query → `MODEL_LIGHT` |
| `engine/pipeline/script.py` | `companion_tease_writer` agent sets `self.model = config.MODEL_LIGHT` |
| `engine/run_cost_report.py` | `summarize_neon()` + `--neon` flag |
| `tests/test_cost_controls.py` | New test file for all of the above |
| `CLAUDE.md` | Update the `run_cost_report` entrypoint line (mention `--neon`) |

---

## Task 1: Config — MODEL_LIGHT

**Files:** Modify `engine/config.py`; Test `tests/test_cost_controls.py`.

- [ ] **Step 1: Write the failing test** — create `tests/test_cost_controls.py`:

```python
from engine import config

def test_model_light_default_is_haiku():
    assert config.MODEL_LIGHT == "claude-haiku-4-5"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_cost_controls.py::test_model_light_default_is_haiku -v`
Expected: FAIL (AttributeError).

- [ ] **Step 3: Add the config** — in `engine/config.py`, immediately after the `MODEL = "claude-sonnet-4-6"` line, add:

```python
# Cheaper model for mechanical, low-stakes stages (short_title, short_desc,
# subject photo-query, companion tease). Sonnet stays everywhere else.
MODEL_LIGHT = os.environ.get("MODEL_LIGHT", "claude-haiku-4-5")
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_cost_controls.py::test_model_light_default_is_haiku -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/config.py tests/test_cost_controls.py
git commit -m "feat(config): add MODEL_LIGHT (Haiku) for mechanical stages"
```

---

## Task 2: Haiku pricing in usage.py

**Files:** Modify `engine/usage.py`; Test `tests/test_cost_controls.py` (append).

- [ ] **Step 1: Write the failing test** — append:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_cost_controls.py::test_haiku_priced_nonzero -v`
Expected: FAIL (cost is 0.0 — unknown model).

- [ ] **Step 3: Add the pricing** — in `engine/usage.py`, inside the `PRICING` dict, add a sibling entry after the `claude-sonnet-4-6` block (rates from the claude-api reference: Haiku 4.5 = $1/M in, $5/M out; cache-write 1.25×input, cache-read 0.10×input):

```python
    "claude-haiku-4-5": {
        "input":       1.00 / 1_000_000,
        "output":      5.00 / 1_000_000,
        "cache_write": 1.25 / 1_000_000,
        "cache_read":  0.10 / 1_000_000,
    },
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_cost_controls.py::test_haiku_priced_nonzero -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/usage.py tests/test_cost_controls.py
git commit -m "feat(usage): price claude-haiku-4-5 in the cost ledger"
```

---

## Task 3: BaseAgent self.model hook

**Files:** Modify `engine/ideate/base_agent.py`; Test `tests/test_cost_controls.py` (append).

Currently `BaseAgent.__init__` sets `self.name`/`self.system_prompt`, and `_call` builds `kwargs = {"model": MODEL, ...}` from the module-level `MODEL` import. The hook lets one agent override the model without affecting the four ideate agents.

- [ ] **Step 1: Write the failing tests** — append:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest tests/test_cost_controls.py -k "self_model or default_model" -v`
Expected: FAIL (no `.model` attribute; `_call` uses module `MODEL`).

- [ ] **Step 3: Add the hook** — in `engine/ideate/base_agent.py`:

In `__init__`, add a `self.model` default (keep the other lines):

```python
        self.name = "base_agent"
        self.system_prompt = ""
        self.model = MODEL          # subclasses may override (e.g. MODEL_LIGHT)
```

In `_call`, change the model line in `kwargs` from the module constant to the instance attribute:

```python
            kwargs = {
                "model": self.model,
                "max_tokens": MAX_TOKENS,
                "system": self.system_prompt,
                "messages": messages,
            }
```

(Leave the `from engine.config import MODEL, ...` import as-is — `MODEL` is still the default value.)

- [ ] **Step 4: Run them to verify they pass**

Run: `python3 -m pytest tests/test_cost_controls.py -k "self_model or default_model" -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add engine/ideate/base_agent.py tests/test_cost_controls.py
git commit -m "feat(ideate): BaseAgent.self.model hook (default config.MODEL)"
```

---

## Task 4: Route the four light stages to MODEL_LIGHT

**Files:** Modify `engine/pipeline/metadata.py`, `engine/pipeline/subject.py`, `engine/pipeline/script.py`; Test `tests/test_cost_controls.py` (append).

- [ ] **Step 1: Write the failing test** — append (source-level guard; the BaseAgent behavioral path is already covered by Task 3):

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_cost_controls.py -k "light_stages or title_stays" -v`
Expected: `light_stages` FAILS (MODEL_LIGHT not yet referenced).

- [ ] **Step 3a: metadata.py** — add `MODEL_LIGHT` to the config import (`from engine.config import MODEL, MODEL_LIGHT, MAX_TOKENS`), then change ONLY the `short_title` and `short_desc` call sites:

`short_title` (the `logged_create(client, "short_title", model=MODEL, ...)` call): change `model=MODEL` → `model=MODEL_LIGHT`.
`short_desc` (the `logged_create(client, "short_desc", model=MODEL, ...)` call): change `model=MODEL` → `model=MODEL_LIGHT`.
**Do NOT change** the main `logged_create(self.client, "metadata", model=MODEL, ...)` call — the title stays on Sonnet.

- [ ] **Step 3b: subject.py** — add `MODEL_LIGHT` to the config import (`from engine.config import MODEL_LIGHT` alongside the existing `MODEL` import), then change the subject-query call `model=MODEL` → `model=MODEL_LIGHT`.

- [ ] **Step 3c: script.py** — in the `companion_tease_writer` agent class, after `super().__init__()` and `self.name = "companion_tease_writer"`, add:

```python
        from engine.config import MODEL_LIGHT
        self.model = MODEL_LIGHT     # cheap tease writer; routed via BaseAgent.self.model
```

(If `MODEL_LIGHT` is already imported at the top of `script.py`, use that instead of the local import.)

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_cost_controls.py -k "light_stages or title_stays" -v`
Expected: PASS (both).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -q --deselect tests/test_fact_gate_oracle.py::test_oracle_flags_known_errors_and_supports_correct`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/pipeline/metadata.py engine/pipeline/subject.py engine/pipeline/script.py tests/test_cost_controls.py
git commit -m "feat(pipeline): route short_title/short_desc/subject/companion-tease to MODEL_LIGHT"
```

---

## Task 5: Neon-aware cost readout (`run_cost_report --neon`)

**Files:** Modify `engine/run_cost_report.py`; Test `tests/test_cost_controls.py` (append).

The Railway cron's spend lands only in the Neon `api_costs` table (Railway fs is ephemeral), never in `logs/api-cost.jsonl`. `--neon` summarizes that table.

- [ ] **Step 1: Write the failing test** — append (pure aggregation, no DB):

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_cost_controls.py -k summarize_neon -v`
Expected: FAIL (no `summarize_neon`).

- [ ] **Step 3: Implement `summarize_neon` + the `--neon` flag** — in `engine/run_cost_report.py`, add the pure function:

```python
def summarize_neon(rows):
    """Aggregate Neon api_costs rows. rows: iterable of (agent, usd). Pure (no DB)."""
    total = 0.0
    by_stage = {}
    for agent, usd in rows:
        usd = float(usd)
        total += usd
        by_stage[agent] = by_stage.get(agent, 0.0) + usd
    return {
        "total": round(total, 4),
        "by_stage": {k: round(v, 4) for k, v in
                     sorted(by_stage.items(), key=lambda kv: -kv[1])},
    }
```

Then in `main()`, add a `--neon` argument and branch BEFORE the existing JSONL path:

```python
    p.add_argument("--neon", action="store_true",
                   help="summarize the durable Neon api_costs ledger (includes the Railway cron)")
    args = p.parse_args(argv)
    if args.neon:
        from engine import config
        if not config.DATABASE_URL:
            print("--neon requires DATABASE_URL to be set")
            return 1
        from engine.queue import neon_backend
        with neon_backend._conn() as c:
            rows = c.execute("SELECT agent, usd FROM api_costs").fetchall()
            trailing30 = c.execute(
                "SELECT COALESCE(sum(usd), 0) FROM api_costs "
                "WHERE ts > now() - interval '30 days'").fetchone()[0]
        agg = summarize_neon(rows)
        print(f"Neon api_costs — total ${agg['total']:.2f} | "
              f"trailing-30-day ${float(trailing30):.2f}")
        for stage, usd in agg["by_stage"].items():
            print(f"  {stage:24} ${usd:.4f}")
        return 0
```

Wire `args` so the existing JSONL flow still runs when `--neon` is absent (keep the current `--run` handling after this branch; if `main` currently parses args into `args` already, reuse it — do not double-parse).

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 -m pytest tests/test_cost_controls.py -k summarize_neon -v`
Expected: PASS (both). (The `--neon` DB branch is verified manually: `python3 -m engine.run_cost_report --neon` with `DATABASE_URL` set.)

- [ ] **Step 5: Commit**

```bash
git add engine/run_cost_report.py tests/test_cost_controls.py
git commit -m "feat(cost-report): --neon summarizes the durable Neon ledger (incl. cron)"
```

---

## Task 6: Docs

**Files:** Modify `CLAUDE.md`.

- [ ] **Step 1: Update the entrypoint line** — in `CLAUDE.md`, find the `run_cost_report` entrypoint line and append a note that `--neon` summarizes the Neon ledger (the only view that includes the Railway cron's spend). Keep it to the existing one-line style.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note run_cost_report --neon (Neon ledger incl. cron)"
```

---

## Final checks before PR

- [ ] `python3 -m pytest tests/ -q --deselect tests/test_fact_gate_oracle.py::test_oracle_flags_known_errors_and_supports_correct` green.
- [ ] Confirm Sonnet stays on `fact_check`, `script_writer`, `thumbnail`, the main `metadata` title, `storyboard`, `headlines` (only the four named stages moved).
- [ ] Ship via `ship-video-change`: dual adversarial review (Codex + Claude), 0 Critical / 0 Important, PR with `Adversarial-Reviewed:` trailer, squash-merge.
