# The Untold Game — project instructions

Automated YouTube content system for the **The Untold Game** sports-history channel.
Architecture modeled on **ConvictionFinder**: an `engine/` that runs on a daily
Railway cron, a review/approve loop, and (Stage 2+) a publish + learning loop.

## Layout

| Path | Role | Status |
|------|------|--------|
| `engine/ideate/` | The 4 idea-generation agents + free web search | **LIVE** |
| `engine/run_pipeline.py` | CLI: run agents → interactive review dashboard | **LIVE** |
| `engine/config.py` | Model, channel context, viral rubric, queue path | **LIVE** |
| `engine/queue_manager.py` | JSON idea queue (pending → approved → rejected) | **LIVE** |
| `engine/pipeline/` | ideate → script → thumbnail → metadata → schedule | ideate LIVE, rest Stage 2 |
| `engine/publish/` | YouTube Data API v3 upload + scheduler (OAuth) | Stage 2 |
| `engine/ingest/` | YouTube Analytics / Trends loaders (learning loop) | Stage 3 |
| `engine/outcomes/` | Track published-video performance vs predicted score | Stage 3 |
| `engine/taxonomy/` | The 6 content pillars | LIVE |
| `engine/profiles/*.yaml` | channel / pillars / cadence config | LIVE |
| `engine/db/schema.sql` | idea → video → metrics (SQL target) | Stage 3 |
| `dashboard/` | Next.js review UI (CF-style) | planned |
| `docs/adr/`, `docs/execution-plan.md` | decisions + roadmap | LIVE |

## Conventions (inherited from ConvictionFinder)

- **`python3`, not `python`** — this machine has no `python` binary.
- **All imports are absolute `engine.*`** — run via `python3 -m engine.run_pipeline`
  (or the root shim `python3 run_pipeline.py`).
- **Web search is FREE** — `engine/ideate/web_search.py` uses `ddgs` (DuckDuckGo,
  open source, no API key). Do **not** reintroduce Anthropic's paid server-side
  `web_search_*` add-on. See [[../docs/adr/0003-free-web-search]].
- **The Anthropic key is reused from ConvictionFinder**, loaded from `.env`
  (gitignored). Never hardcode it or commit it. CF's key lives in Railway.
- **Add an idea agent**: subclass `BaseAgent` (`engine/ideate/base_agent.py`),
  implement `generate_ideas()`, register it in `engine/pipeline/ideate.py` AGENTS.
- **Self-stub on missing data** — an agent or stage must never crash the run.
- **Fact-gate is auto-chained** — `run_produce` verifies each script (auto-corrects once, re-verifies) and marks the idea `in_production` only if it passes, else `needs_review`. Don't publish a `needs_review` idea without human review. `run_factcheck --id <id> [--fix]` is the standalone re-check (exits non-zero unless clean + complete). Never publish unverified specifics about real people/events. See docs/adr/0005-fact-verification-gate.md.
- Docs/HANDOFF/CLAUDE.md changes must not trigger a deploy/dashboard rebuild.

## Entrypoints

```bash
python3 -m engine.run_pipeline            # all 4 agents (parallel) → review dashboard
python3 -m engine.run_pipeline --agent 1  # one agent (1=history 2=trending 3=gaps 4=evergreen)
python3 -m engine.run_pipeline --review   # review the existing queue, no generation
python3 -m engine.run_pipeline --stats    # queue stats only
```

## Gate discipline

Stage 1 (idea generation) is proven LIVE. Do **not** build Stage 2 (publishing)
features speculatively — prove each stage's value before expanding surface. The
publishing pipeline is justified only once real, approved ideas exist to publish.

## Hard rules (inherited from ConvictionFinder, adapted)

- **NEVER push `main` directly / NEVER work on `main`.** Branch (`feat/<slug>`), PR, merge —
  the pre-push hook (`.claude/settings.json`) blocks a direct push while on main.
- **ALWAYS `python3 -m pytest tests/ -q` after editing `engine/**.py`.** That's the contract;
  the PostToolUse hook (`.claude/hooks/engine-test.sh`) runs it automatically and wakes you on
  failure. Tests run under **`python3`** (main env), never `.venv-video`.
- **Two-venv split is load-bearing** — `python3` for produce/qc/orchestration, `.venv-video`
  for render (Kokoro/whisper/Remotion). Never import across them; shell out (see `run_auto.py`).
- **Integrity gate** — never publish unverified specifics about real people/events, never
  fabricate real footage (ADR-0005). This is TUG's hard gate, the analog of CF's billing guard.
- **Smallest sufficient change** — no speculative abstraction/config; touch only the files the
  stated success criteria require.

## PR + review workflow

Engine (`engine/*.py`) changes ship via the **`ship-video-change`** skill:

```
git checkout -b feat/<slug>
python3 -m pytest tests/ -q                     # contract (hook runs it too)
# dual adversarial review (catch different bug classes):
codex:rescue                                    # Codex second pass
# spawn Agent(superpowers:code-reviewer) → note agentId
# gate: 0 Critical + 0 Important from BOTH
gh pr create --base main --body "...
Adversarial-Reviewed: <agentId>"                # trailer required (pr-review-gate hook enforces)
gh pr merge --squash --delete-branch
```

For a multi-file feature, prefer the full `superpowers:subagent-driven-development` rail
(per-task + final whole-impl review) — how Stage B was built. The **45-min render is never a
gate**; rely on `pytest tests/` + the QC gate + the still-preview trick.

**Dashboard/config/docs-only PRs:** plain `gh pr create --base main` (no trailer, no review).
**Bypass** (docs/renames only): `Review-Skip: <reason>` in the PR body instead of the trailer.

Deploy: the produce/ideate cron can run on Railway from `main`; **render is local** (launchd on
the M2 — Railway can't do the 45-min Chromium render). Never run a render in a hook or in CI.
