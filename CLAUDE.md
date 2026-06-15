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
| `engine/pipeline/` | ideate → script → thumbnail → banner → metadata → schedule (thumbnail subjects can be auto-sourced via `run_subject` (Wikimedia Commons → Pexels), or dropped by hand at `produced/<id>/<fmt>/subject.png`) | ideate/script/metadata/thumbnail/banner LIVE; schedule Stage 2 |
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
python3 -m engine.run_produce --id <id> [--format short] [--metadata-only]  # script+metadata (—metadata-only = retitle, no re-render)
python3 -m engine.run_thumbnail --id <id> [--format short]  # composite thumbnail from produced/<id>/<fmt>/subject.png
python3 -m engine.run_preflight --id <id> [--format short] [--fix]  # pre-flight QC lint of props.json (auto-fix caption/headline defects; --fix rewrites props.json + captions.srt). Runs automatically inside run_video before each render.
python3 -m engine.run_subject --id <id> [--format short]   # auto-source subject.png (Wikipedia lead image → Pexels fallback; human photo wins)
python3 -m engine.run_banner              # generate channel/banner.png + description.txt (manual upload to Studio)
python3 -m engine.run_cost_report [--run <id>]  # per-run API cost summary from logs/api-cost.jsonl (overnight.sh runs this automatically; warns if a run exceeds COST_ALERT_USD=$10)
python3 -m engine.run_cost_report --neon        # summarize the durable Neon api_costs ledger (the only view that includes the Railway cron's spend)
```

## Skills (`.claude/skills/`)

Operational playbooks that wrap the entrypoints above — invoke by name instead of
re-deriving flags each session:

| Skill | Wraps |
|-------|-------|
| `run-pipeline` | `run_pipeline` — generate ideas / review the queue |
| `review-ideas` | non-interactive queue triage readout |
| `build-video` | `run_auto` / `run_video` — produce → render → QC → preview |
| `thumbnail-assets` | `run_subject` → `run_thumbnail` (+ `run_banner`) |
| `publish-video` | `run_auto --approve/--render` — publish or re-render |
| `cost-report` | `run_cost_report` — API spend summary + triage |
| `fact-review` | human-grade re-check of a `needs_review` script |
| `preflight-qc` | `run_preflight` — lint props.json before render |
| `ship-video-change` | the release rail for `engine/*.py` changes |
| `handoff` | append a session wrap to `HANDOFF.md` |

## Gate discipline

Stage 1 (idea generation) is proven LIVE. Do **not** build Stage 2 (publishing)
features speculatively — prove each stage's value before expanding surface. The
publishing pipeline is justified only once real, approved ideas exist to publish.

A render is **blocked** if the pre-flight QC lint (`engine/video/preflight.py`, auto-run in
`run_video` before each Remotion render) finds an unfixed CRITICAL caption/headline/timing
defect — the idea is marked `needs_review`. Deterministic defects (split numbers, zero-duration
captions, overlaps, duplicate headlines) are auto-corrected once, then re-verified. See
docs/superpowers/specs/2026-06-15-preflight-qc-lint-design.md.

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

Deploy: the **ideate cron runs on Railway** every 2-3 days (`python3 -m engine.run_cron`),
writing new ideas to **Neon** (the single source of truth when `DATABASE_URL` is set).
Local flows — `run_pipeline --review`, `run_produce`, `run_auto` — read the same Neon queue.
**Render is still local** (launchd on the M5 — Railway can't do the 45-min Chromium render).
The JSON queue (`queue/idea_queue.json`) is the offline/test fallback when `DATABASE_URL` is unset.
Required Railway env vars: `DATABASE_URL` (Neon connection string), `ANTHROPIC_API_KEY`,
`CRON_PER_RUN_CAP_USD`, `CRON_MONTHLY_CAP_USD`. Never run a render in a hook or in CI.
