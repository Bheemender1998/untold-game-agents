# Operational skills for The Untold Game — design

**Date:** 2026-06-14
**Status:** Approved (brainstorm), pending spec review

## Problem

Several day-to-day TUG workflows are run by hand each session from the CLI surface
(`run_auto`, `run_video`, `run_subject`, `run_thumbnail`, `run_banner`,
`run_cost_report`). They are not yet codified as skills, so each session re-derives
the exact flags, the order of steps, and the safety gates. We already have five
project skills (`run-pipeline`, `review-ideas`, `fact-review`, `ship-video-change`,
`handoff`); this adds four more operational playbooks in the same house style.

## Scope

Four new skills under `.claude/skills/`, each a thin operational playbook (the
`run-pipeline` SKILL.md shape: `Working dir` + `python3` header, bullet commands,
preconditions/gotchas). **No engine code changes.** Skills touch `.claude/skills/`
only, so this ships as a docs/config-only PR — no pytest contract, no review trailer.

Non-goals: no new CLI flags, no wrapper scripts, no changes to `run_auto` et al.
The skills document the *existing* surface; they do not extend it.

## The four skills

### 1. `build-video` — produce → render → QC → preview

The full local video build loop.

- **Unattended:** `python3 -m engine.run_auto --count N` → produce + render + QC →
  `awaiting_approval`.
- **Preview-before-render trick:** `python3 -m engine.run_video --id <id>`
  (compose only, *no* `--render`) writes `produced/<id>/<fmt>/index.html`; open it in
  a browser to eyeball the composition, then render. The 45-min render is never a gate.
- **QC gate:** `run_auto` runs `engine/pipeline/qc.py` — render-integrity
  (file + video/audio streams + duration within tolerance), brightness band (mean
  luma), caption coverage (props vs audio). Results land in
  `produced/<id>/<fmt>/qc.json`; a failed check keeps the idea out of
  `awaiting_approval`.
- **Gotchas:** render is **local only** (M2, `.venv-video`, needs `npx`) — never in a
  hook or CI. `needs_review` (fact-gate) ideas are blocked; clear them via the
  `fact-review` skill / `run_factcheck` first.

**Triggers:** "build the video", "produce and render `<id>`", "render the loop",
"run the produce loop", `/build-video`.

### 2. `thumbnail-assets` — subject / thumbnail / banner

Source the subject photo and composite the thumbnail (and, separately, the channel
banner).

- `python3 -m engine.run_subject --id <id> [--format short]` — Wikipedia lead image →
  Pexels fallback. A hand-dropped `produced/<id>/<fmt>/subject.png|jpg` always wins.
- `python3 -m engine.run_thumbnail --id <id> [--format short]` — requires a subject
  photo; composites the "Prestige Feed Killer" thumbnail.
- **Manual override:** drop `subject.png` by hand at `produced/<id>/<fmt>/` → re-run
  `run_thumbnail`.
- **Channel banner (separate, channel-level):** `python3 -m engine.run_banner` →
  `channel/banner.png` + `channel/description.txt`; manual upload to YouTube Studio.
- Default `--format` is `long`; `short` is the 9:16 vertical variant.

**Triggers:** "make the thumbnail", "source a subject for `<id>`", "thumbnail for
`<id>`", "regenerate the banner", `/thumbnail-assets`.

### 3. `publish-video` — publish / re-render

Publish an `awaiting_approval` video to YouTube, or re-render an existing one.

- **List awaiting:** `python3 -m engine.run_auto --list`
- **Dry-run (auth + metadata check, no insert):** `run_auto --approve <id> --dry-run`
- **Publish unlisted (default):** `run_auto --approve <id>`
- **Publish public:** `run_auto --approve <id> --public`
- **Re-render existing (skips produce):** `run_auto --render <id>` — how `bb8585d1`
  was re-rendered on 2026-06-14.
- **Review / reject / backlink:** `run_auto --review <id> --note "…"`,
  `run_auto --reject <id>`, `run_auto --backlink <id>`.
- **Integrity gate (hard rule):** never publish `needs_review` / unverified content.
  Default to **unlisted**; **confirm with the user before `--public`** — publishing is
  outward-facing and effectively irreversible. OAuth is handled by
  `engine/publish/auth.py` (needs client secret + token).

**Triggers:** "publish `<id>`", "approve `<id>`", "upload to YouTube", "re-render
`<id>`", `/publish-video`.

### 4. `cost-report` — cost report / triage

Summarize API spend from the ledger and triage budget alerts.

- **All runs:** `python3 -m engine.run_cost_report`
- **One run:** `python3 -m engine.run_cost_report --run <TUG_RUN_ID>`
- Ledger is `logs/api-cost.jsonl`; alert threshold `config.COST_ALERT_USD` ($10);
  reporter-only (always exits 0, never gates a run); `overnight.sh` runs it per run.
- **Triage:** typical 3-video run ≈ $0.42; a ~20-script runaway trips the $10 alert.
  A high run → break the cost down by stage (script / metadata / fact-gate /
  thumbnail); the runaway pattern is repeated produce loops.

**Triggers:** "cost report", "how much did the run cost", "check API spend",
"$10 alert", `/cost-report`.

## House style (match existing skills)

Each `SKILL.md`:
- YAML frontmatter: `name` (kebab slug) + `description` (one line ending with the
  trigger phrases, mirroring `run-pipeline`).
- `Working dir: /Users/bheemendergurram/untold_game_agents. Always python3.` header.
- Bullet list of exact commands, then a short Preconditions/Gotchas paragraph.
- Keep them thin — they document the existing surface, nothing more.

## Testing / verification

These are documentation files; there is no code path to unit-test. Verification:
- Each `SKILL.md` parses (valid frontmatter, `name` matches its directory).
- Every command quoted exists in the current CLI (cross-checked against the
  `run_*.py` argparse definitions during authoring).
- Skills appear in the available-skills list after creation.

## Out of scope / deferred

Track B — reviving the set-aside local stack (Fooocus local SDXL, Qwen3 via Ollama,
ScrapeGraphAI) now that the M5 Pro overturns ADR-0004's "decisive" 8GB constraint —
is a separate brainstorm + ADR-0004 update, to be done after these skills ship.
