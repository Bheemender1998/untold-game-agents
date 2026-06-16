# Conditional Ideation Top-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local overnight run generate ideas only when the shared pending queue is below a floor (`IDEATE_TOPUP_MIN`, default 12); otherwise skip ideation and go straight to produce→render→QC.

**Architecture:** A pure `_topup_needed(pending_count, floor)` helper holds the decision; a new optional `--ensure-min [N]` flag on `run_pipeline` consults it against `len(get_pending())` and returns early (no generation) when the queue is at/above the floor. `overnight.sh` adds the bare flag; the Railway cron is untouched (it calls `run_single_agent` directly, not `main()`). Threshold lives in one config constant.

**Tech Stack:** Python 3 (stdlib `argparse`), pytest with monkeypatch. Reuses `engine.config`, `engine.queue_manager.get_pending`.

**Spec:** `docs/superpowers/specs/2026-06-15-conditional-ideation-topup-design.md`

**Conventions:** `python3` only; absolute `engine.*` imports; run `python3 -m pytest tests/ -q` after every `engine/**.py` edit (PostToolUse hook also runs it). Commit after each task.

---

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `engine/config.py` | `IDEATE_TOPUP_MIN` constant (env-overridable). | Modify (after `CRON_MONTHLY_CAP_USD`, ~line 166) |
| `engine/run_pipeline.py` | `_topup_needed` helper; `--ensure-min` flag + guard in `main()`. | Modify (import ~line 25; helper near top; flag + guard in `main()` ~line 189/200) |
| `scripts/overnight.sh` | Add `--ensure-min` to the step-1 ideate call. | Modify |
| `tests/test_topup.py` | Unit + integration tests for the helper and the guard. | Create |
| `CLAUDE.md` | Note local top-up is conditional. | Modify (deploy paragraph) |

---

## Task 1: Config constant + `_topup_needed` helper

**Files:**
- Modify: `engine/config.py` (after `CRON_MONTHLY_CAP_USD = ...`, ~line 166)
- Modify: `engine/run_pipeline.py` (add helper near the top, after the ANSI colour block)
- Test: `tests/test_topup.py`

- [ ] **Step 1: Add the config constant**

In `engine/config.py`, immediately after the line `CRON_MONTHLY_CAP_USD = float(os.environ.get("CRON_MONTHLY_CAP_USD", "15.0"))`:

```python
# Local overnight (overnight.sh) tops up the idea queue ONLY when fewer than this many
# ideas are pending; otherwise it skips ideation and goes straight to produce→render→QC.
# The Railway cron remains the primary generator (~every 2 days). Env-overridable.
IDEATE_TOPUP_MIN = int(os.environ.get("IDEATE_TOPUP_MIN", "12"))
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_topup.py`:

```python
from engine import run_pipeline
from engine import config


def test_topup_needed_below_floor():
    assert run_pipeline._topup_needed(5, 12) is True


def test_topup_not_needed_above_floor():
    assert run_pipeline._topup_needed(20, 12) is False


def test_topup_not_needed_at_floor():
    # At exactly the floor we already have "enough" → skip (>= floor means skip).
    assert run_pipeline._topup_needed(12, 12) is False


def test_topup_min_config_default_is_twelve():
    # Default floor when IDEATE_TOPUP_MIN is unset.
    assert config.IDEATE_TOPUP_MIN == 12
```

- [ ] **Step 3: Run to verify it fails**

Run: `python3 -m pytest tests/test_topup.py -q`
Expected: FAIL — `AttributeError: module 'engine.run_pipeline' has no attribute '_topup_needed'`.
(`test_topup_min_config_default_is_twelve` passes only if `IDEATE_TOPUP_MIN` is unset in the env; it is added in Step 1.)

- [ ] **Step 4: Add the helper**

In `engine/run_pipeline.py`, after the ANSI colour block (the `GOLD = ...` lines near the top, before the first `def`), add:

```python
def _topup_needed(pending_count: int, floor: int) -> bool:
    """Generate ideas only when the queue is below the floor (>= floor → skip)."""
    return pending_count < floor
```

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m pytest tests/test_topup.py -q`
Expected: PASS (4 tests). Then `python3 -m pytest tests/ -q` — no regressions.

- [ ] **Step 6: Commit**

```bash
git add engine/config.py engine/run_pipeline.py tests/test_topup.py
git commit -m "feat(cron): IDEATE_TOPUP_MIN config + _topup_needed helper"
```

---

## Task 2: `--ensure-min` flag + guard in `main()`

**Files:**
- Modify: `engine/run_pipeline.py` (import ~line 25; argparse ~line 187-189; guard ~line 200, before agent dispatch)
- Test: `tests/test_topup.py`

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_topup.py`:

```python
import sys


def _run_main(monkeypatch, argv, pending_count):
    """Drive run_pipeline.main() with a stubbed queue + spy on generation."""
    calls = {"all": 0, "single": 0}
    monkeypatch.setattr(sys, "argv", ["run_pipeline", *argv])
    monkeypatch.setattr(run_pipeline, "get_pending",
                        lambda *a, **k: [{"id": i} for i in range(pending_count)])
    monkeypatch.setattr(run_pipeline, "run_all_agents",
                        lambda *a, **k: calls.__setitem__("all", calls["all"] + 1))
    monkeypatch.setattr(run_pipeline, "run_single_agent",
                        lambda *a, **k: calls.__setitem__("single", calls["single"] + 1))
    monkeypatch.setattr(run_pipeline, "print_stats", lambda *a, **k: None)
    run_pipeline.main()
    return calls


def test_ensure_min_skips_generation_when_queue_full(monkeypatch):
    calls = _run_main(monkeypatch, ["--no-review", "--ensure-min"], pending_count=20)
    assert calls["all"] == 0 and calls["single"] == 0


def test_ensure_min_generates_when_queue_low(monkeypatch):
    calls = _run_main(monkeypatch, ["--no-review", "--ensure-min"], pending_count=5)
    assert calls["all"] == 1


def test_ensure_min_explicit_value_overrides_floor(monkeypatch):
    # Floor 3: 5 pending ≥ 3 → skip even though it's below the default 12.
    calls = _run_main(monkeypatch, ["--no-review", "--ensure-min", "3"], pending_count=5)
    assert calls["all"] == 0


def test_no_flag_always_generates(monkeypatch):
    # Today's behaviour preserved: no --ensure-min → generate regardless of depth.
    calls = _run_main(monkeypatch, ["--no-review"], pending_count=999)
    assert calls["all"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_topup.py -q`
Expected: FAIL — `--ensure-min` is an unrecognized argument (argparse `SystemExit`), so the skip/override tests fail.

- [ ] **Step 3: Add the import**

In `engine/run_pipeline.py`, change the config import (currently `from engine.config import MIN_VIRAL_SCORE`) to:

```python
from engine.config import MIN_VIRAL_SCORE, IDEATE_TOPUP_MIN
```

- [ ] **Step 4: Add the flag**

In `main()`, after the `--no-review` argument (`run_pipeline.py:187-188`), add:

```python
    parser.add_argument("--ensure-min", nargs="?", type=int, const=IDEATE_TOPUP_MIN,
                        default=None,
                        help="only generate if fewer than N ideas are pending (bare flag "
                             "uses config.IDEATE_TOPUP_MIN); otherwise skip ideation")
```

- [ ] **Step 5: Add the guard**

In `main()`, immediately after the `if args.review:` block returns (i.e. after its `return`, before `if args.agent:` at ~line 201), add:

```python
    if args.ensure_min is not None:
        pending = len(get_pending())
        if not _topup_needed(pending, args.ensure_min):
            print(f"{GRAY}Queue has {pending} pending ≥ floor {args.ensure_min} — "
                  f"skipping ideation.{RESET}")
            return
        print(f"{GRAY}Queue has {pending} pending < floor {args.ensure_min} — "
              f"topping up.{RESET}")
```

(Confirm `GRAY` and `RESET` are defined in the ANSI block — they are.)

- [ ] **Step 6: Run to verify it passes**

Run: `python3 -m pytest tests/test_topup.py -q`
Expected: PASS (8 tests). Then `python3 -m pytest tests/ -q` — no regressions.

- [ ] **Step 7: Commit**

```bash
git add engine/run_pipeline.py tests/test_topup.py
git commit -m "feat(cron): --ensure-min flag gates ideation on queue depth"
```

---

## Task 3: Wire into overnight.sh + docs

**Files:**
- Modify: `scripts/overnight.sh`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the overnight ideate call**

In `scripts/overnight.sh`, change the step-1 line:

```bash
  python3 -m engine.run_pipeline --no-review || echo "(ideate failed — non-fatal, continuing)"
```
to:
```bash
  python3 -m engine.run_pipeline --no-review --ensure-min || echo "(ideate failed — non-fatal, continuing)"
```

And change the preceding echo comment line:
```bash
  echo "-- ideate: top up the queue (headless) --"
```
to:
```bash
  echo "-- ideate: top up the queue only if below IDEATE_TOPUP_MIN (headless) --"
```

- [ ] **Step 2: Update CLAUDE.md deploy paragraph**

In `CLAUDE.md`, find the deploy paragraph that begins `Deploy: the **ideate cron runs on Railway**`. Immediately after the sentence ending `…reads the same Neon queue.`, insert:

```
The **local overnight** (launchd, daily 01:00) tops up ideas only when the queue is below
`IDEATE_TOPUP_MIN` (default 12) — otherwise it skips ideation and goes straight to
produce→render→QC; the Railway cron stays the primary generator.
```

- [ ] **Step 3: Verify nothing broke**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

Also sanity-check the flag end-to-end without touching the DB (stub-free dry check of argparse):
Run: `python3 -m engine.run_pipeline --help | grep -A2 ensure-min`
Expected: the `--ensure-min` help text appears.

- [ ] **Step 4: Commit**

```bash
git add scripts/overnight.sh CLAUDE.md
git commit -m "docs(cron): overnight tops up only below IDEATE_TOPUP_MIN"
```

---

## Final verification (after all tasks)

- [ ] `python3 -m pytest tests/ -q` — full suite green.
- [ ] `python3 -m engine.run_pipeline --help` shows `--ensure-min`.
- [ ] Manual reasoning check: with the live queue at 77 pending and floor 12, `--ensure-min`
      prints "skipping ideation" and exits without generating. (Do NOT run live generation just
      to test — the unit tests cover both branches.)
- [ ] Rebase onto latest `main` (it advanced to the auto-thumbnail merge #65 while this branch
      was parked) before opening the PR: `git fetch origin && git rebase origin/main`.
- [ ] Ship via `ship-video-change` (engine `.py` changed): dual adversarial review (Codex +
      Claude code-reviewer), 0 Critical/0 Important from both, PR with `Adversarial-Reviewed:`
      trailer, squash-merge.
- [ ] Update the automation memory (`neon-queue-railway-cron-live`) to note the conditional
      local top-up.

## Notes

- `_select`/produce selection is intentionally untouched — top-N by `viral_score DESC`.
- The Railway cron (`run_cron` → `run_single_agent`) does not call `main()`, so `--ensure-min`
  cannot affect it; it remains the capped primary generator.
- The guard counts `get_pending()` once per run (one Neon query / one JSON load) — negligible.
