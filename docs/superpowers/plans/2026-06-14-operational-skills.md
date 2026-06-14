# Operational Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four operational playbook skills (`build-video`, `thumbnail-assets`, `publish-video`, `cost-report`) under `.claude/skills/`, documenting the existing TUG CLI surface.

**Architecture:** Each skill is a single `SKILL.md` file matching the existing `run-pipeline` house style: YAML frontmatter (`name` + trigger-bearing `description`), a `Working dir`/`python3` header, exact-command bullets, and a Preconditions/Gotchas tail. No engine code changes; this ships as a docs/config-only PR.

**Tech Stack:** Markdown + YAML frontmatter. Verification via shell (`python3 ... --help` to confirm flags exist).

**Spec:** `docs/superpowers/specs/2026-06-14-operational-skills-design.md`

---

## File Structure

- Create: `.claude/skills/build-video/SKILL.md` — produce → render → QC → preview playbook
- Create: `.claude/skills/thumbnail-assets/SKILL.md` — subject / thumbnail / banner playbook
- Create: `.claude/skills/publish-video/SKILL.md` — publish / re-render playbook
- Create: `.claude/skills/cost-report/SKILL.md` — cost report / triage playbook

Each file is self-contained; no shared state between them. Verification commands reference the existing `engine/run_*.py` entrypoints (read-only `--help`).

---

### Task 1: `build-video` skill

**Files:**
- Create: `.claude/skills/build-video/SKILL.md`

- [ ] **Step 1: Verify the commands the skill will quote actually exist**

Run: `python3 -m engine.run_auto --help && python3 -m engine.run_video --help`
Expected: `run_auto` shows `--count`, `--render`; `run_video` shows `--id`, `--render`. Both exit 0.

- [ ] **Step 2: Create the SKILL.md**

```markdown
---
name: build-video
description: Run the local produce→render→QC loop for a TUG video, with a compose-preview before the 45-min render. Use when the user says "build the video", "produce and render <id>", "run the produce loop", or "/build-video".
---

# Build a video (produce → render → QC → preview)

Working dir: `/Users/bheemendergurram/untold_game_agents`. Always `python3`.
Render is **local only** (M2, `.venv-video`, needs `npx`) — never run it in a hook or CI.

- **Unattended build:** `python3 -m engine.run_auto --count N`
  Produces + renders + QC-gates N ideas → `awaiting_approval`.
- **Dry test (stop before render):** `python3 -m engine.run_auto --count 1 --no-render`
- **Preview-before-render trick:** `python3 -m engine.run_video --id <id>`
  Compose only (no `--render`) → writes `produced/<id>/<fmt>/index.html`. Open it in a
  browser to eyeball the composition, *then* render. The 45-min render is never a gate.
- **Render only (compose already done):** `python3 -m engine.run_video --id <id> --render`
  (or `--mode narrated --render` for voiced long-form).

QC gate: `run_auto` runs `engine/pipeline/qc.py` — render-integrity (file + video/audio
streams + duration tolerance), brightness band (mean luma), caption coverage (props vs
audio). Results land in `produced/<id>/<fmt>/qc.json`; a failed check keeps the idea out
of `awaiting_approval`.

Preconditions / gotchas: `needs_review` (fact-gate) ideas are blocked — clear them via the
`fact-review` skill / `python3 -m engine.run_factcheck --id <id>` first. The render needs
the `.venv-video` interpreter and `npx`; `run_auto` shells out per stage with the right
interpreter.
```

- [ ] **Step 3: Verify frontmatter parses and name matches directory**

Run: `head -4 .claude/skills/build-video/SKILL.md`
Expected: `name: build-video` (matches the directory name); valid `---`-delimited frontmatter.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/build-video/SKILL.md
git commit -m "feat(skill): build-video — produce/render/QC/preview playbook"
```

---

### Task 2: `thumbnail-assets` skill

**Files:**
- Create: `.claude/skills/thumbnail-assets/SKILL.md`

- [ ] **Step 1: Verify the commands the skill will quote actually exist**

Run: `python3 -m engine.run_subject --help && python3 -m engine.run_thumbnail --help && python3 -m engine.run_banner --help`
Expected: `run_subject`/`run_thumbnail` show `--id` and `--format {long,short}`; `run_banner` runs with no required args. All exit 0.

- [ ] **Step 2: Create the SKILL.md**

```markdown
---
name: thumbnail-assets
description: Source the subject photo and composite the thumbnail (and channel banner) for a TUG video. Use when the user says "make the thumbnail", "source a subject for <id>", "thumbnail for <id>", "regenerate the banner", or "/thumbnail-assets".
---

# Thumbnail assets (subject → thumbnail → banner)

Working dir: `/Users/bheemendergurram/untold_game_agents`. Always `python3`.
Default `--format` is `long`; `short` is the 9:16 vertical variant.

- **Source the subject photo:** `python3 -m engine.run_subject --id <id> [--format short]`
  Wikipedia lead image → Pexels fallback. A hand-dropped
  `produced/<id>/<fmt>/subject.png|jpg` always wins (never overwritten).
- **Composite the thumbnail:** `python3 -m engine.run_thumbnail --id <id> [--format short]`
  Requires a subject photo; builds the "Prestige Feed Killer" cover at
  `produced/<id>/<fmt>/thumbnail.jpg`.
- **Manual override:** drop `subject.png` by hand at `produced/<id>/<fmt>/`, then re-run
  `run_thumbnail`.
- **Channel banner (separate, channel-level):** `python3 -m engine.run_banner`
  → `channel/banner.png` + `channel/description.txt`. Upload the banner as channel art
  and paste the description into "About" in YouTube Studio (manual).

Preconditions / gotchas: `run_thumbnail` exits non-zero if no subject photo exists — run
`run_subject` (or drop one by hand) first. `run_subject` needs `PEXELS_API_KEY` in `.env`
for the stock fallback; without it, only the Wikipedia path works.
```

- [ ] **Step 3: Verify frontmatter parses and name matches directory**

Run: `head -4 .claude/skills/thumbnail-assets/SKILL.md`
Expected: `name: thumbnail-assets`; valid frontmatter.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/thumbnail-assets/SKILL.md
git commit -m "feat(skill): thumbnail-assets — subject/thumbnail/banner playbook"
```

---

### Task 3: `publish-video` skill

**Files:**
- Create: `.claude/skills/publish-video/SKILL.md`

- [ ] **Step 1: Verify the commands the skill will quote actually exist**

Run: `python3 -m engine.run_auto --help`
Expected: shows `--list`, `--approve`, `--public`, `--dry-run`, `--render`, `--review`, `--note`, `--reject`, `--backlink`. Exits 0.

- [ ] **Step 2: Create the SKILL.md**

```markdown
---
name: publish-video
description: Publish an awaiting_approval TUG video to YouTube, or re-render an existing one. Use when the user says "publish <id>", "approve <id>", "upload to YouTube", "re-render <id>", or "/publish-video".
---

# Publish / re-render a video

Working dir: `/Users/bheemendergurram/untold_game_agents`. Always `python3`.
All actions go through the Stage B orchestrator, `engine.run_auto`.

- **List what's awaiting approval:** `python3 -m engine.run_auto --list`
- **Dry-run (auth + metadata check, no insert):** `python3 -m engine.run_auto --approve <id> --dry-run`
- **Publish unlisted (default):** `python3 -m engine.run_auto --approve <id>`
- **Publish public:** `python3 -m engine.run_auto --approve <id> --public`
- **Re-render an existing idea (skips produce):** `python3 -m engine.run_auto --render <id>`
- **Mark human-reviewed before approving:** `python3 -m engine.run_auto --review <id> --note "..."`
- **Reject:** `python3 -m engine.run_auto --reject <id>`
- **Backlink (long ↔ short):** `python3 -m engine.run_auto --backlink <id>`

Preconditions / gotchas (HARD RULES): never publish a `needs_review` / unverified idea
(ADR-0005 integrity gate). Default to **unlisted**; **confirm with the user before
`--public`** — a publish is outward-facing and effectively irreversible. OAuth is handled
by `engine/publish/auth.py` and needs the client secret + token to exist; run the
`--dry-run` first to confirm auth before a real insert.
```

- [ ] **Step 3: Verify frontmatter parses and name matches directory**

Run: `head -4 .claude/skills/publish-video/SKILL.md`
Expected: `name: publish-video`; valid frontmatter.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/publish-video/SKILL.md
git commit -m "feat(skill): publish-video — publish/re-render playbook"
```

---

### Task 4: `cost-report` skill

**Files:**
- Create: `.claude/skills/cost-report/SKILL.md`

- [ ] **Step 1: Verify the command + threshold the skill will quote**

Run: `python3 -m engine.run_cost_report --help && python3 -c "from engine import config; print('COST_ALERT_USD', config.COST_ALERT_USD)"`
Expected: `run_cost_report` shows `--run`; prints `COST_ALERT_USD 10` (or the current value). Exits 0.

- [ ] **Step 2: Create the SKILL.md**

```markdown
---
name: cost-report
description: Summarize TUG API spend from the cost ledger and triage budget alerts. Use when the user says "cost report", "how much did the run cost", "check API spend", "$10 alert", or "/cost-report".
---

# API cost report / triage

Working dir: `/Users/bheemendergurram/untold_game_agents`. Always `python3`.

- **All runs in the ledger:** `python3 -m engine.run_cost_report`
- **One run by id:** `python3 -m engine.run_cost_report --run <TUG_RUN_ID>`

How it works: every `messages.create` is priced and appended to `logs/api-cost.jsonl`
(via `engine/usage.py`). The report groups by `run_id`, prints a per-stage breakdown,
and warns when a run exceeds `config.COST_ALERT_USD` ($10). It is **reporter-only** —
always exits 0, never gates a run. `overnight.sh` runs it automatically per run and
folds the summary into the daily log.

Triage: a typical 3-video run is ≈ $0.42; a ~20-script runaway trips the $10 alert. If a
run is unexpectedly high, read the per-stage breakdown (script / metadata / fact-gate /
thumbnail) — the runaway pattern is repeated produce loops re-spending on scripts.
```

- [ ] **Step 3: Verify frontmatter parses and name matches directory**

Run: `head -4 .claude/skills/cost-report/SKILL.md`
Expected: `name: cost-report`; valid frontmatter.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/cost-report/SKILL.md
git commit -m "feat(skill): cost-report — cost report/triage playbook"
```

---

### Task 5: Final verification + PR

**Files:** none (verification + PR only)

- [ ] **Step 1: Confirm all four skills are present and named correctly**

Run: `for s in build-video thumbnail-assets publish-video cost-report; do echo "== $s =="; head -2 .claude/skills/$s/SKILL.md; done`
Expected: each prints `---` then `name: <s>` matching its directory.

- [ ] **Step 2: Confirm no engine code was touched (docs/config-only PR)**

Run: `git diff --name-only main...HEAD`
Expected: only `.claude/skills/**/SKILL.md` and `docs/superpowers/**` paths — no `engine/*.py`.

- [ ] **Step 3: Push and open the PR (no review trailer — docs/config-only)**

```bash
git push -u origin feat/operational-skills
gh pr create --base main \
  --title "feat(skills): build-video, thumbnail-assets, publish-video, cost-report" \
  --body "Four operational playbook skills documenting the existing TUG CLI surface (run_auto / run_video / run_subject / run_thumbnail / run_banner / run_cost_report). Docs/config-only — touches .claude/skills/ + docs/, no engine/*.py.

Spec: docs/superpowers/specs/2026-06-14-operational-skills-design.md
Plan: docs/superpowers/plans/2026-06-14-operational-skills.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 4: Squash-merge**

```bash
gh pr merge --squash --delete-branch
```

---

## Self-Review

**Spec coverage:** All four skills in the spec map to Tasks 1–4; house style (frontmatter/header/bullets/gotchas) is applied in each; the docs/config-only PR path and "no engine code" boundary are verified in Task 5. The spec's deferred Track B (Fooocus/local stack) is explicitly out of scope and not in any task — correct.

**Placeholder scan:** Each SKILL.md is written in full inside its task (no "TBD"/"similar to"). Verification commands are concrete with expected output.

**Type consistency:** Skill slugs (`build-video`, `thumbnail-assets`, `publish-video`, `cost-report`) are identical across directory paths, frontmatter `name`, descriptions, and the Task 5 verification loop. CLI flags quoted match the `run_*.py` argparse confirmed during brainstorming.
