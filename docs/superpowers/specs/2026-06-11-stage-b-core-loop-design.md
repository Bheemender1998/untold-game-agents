# Stage B — Automation Core Loop (design)

**Date:** 2026-06-11
**Status:** approved (brainstorm) → ready for implementation plan
**Scope decision:** Core loop first. Long-form YouTube only.

## Goal

Turn the proven manual pipeline (produce → render → publish) into an **unattended
core loop** with a **human approval gate before publish**. A human runs one command,
the system produces + renders + quality-checks a video and parks it `awaiting_approval`;
the human reviews and approves from the CLI, which publishes it.

Target cadence ~2/day, but cadence/scheduling (launchd) is **deferred** — this pass is
"run it by hand, approve from CLI."

## Out of scope (deferred, each its own future build)

- **launchd scheduler** — cron the loop overnight on the M2.
- **Claude-vision people-check** — per-clip face detection in QC.
- **Web approval UI** — a dashboard for the approval gate.
- **Shorts / TikTok / Instagram** — vertical (1080×1920) comp + short-script condenser +
  per-platform posting (TikTok/IG each need their own OAuth). Reuses `qc.py` and
  `run_auto.py` as a `--vertical` branch when built; not a rewrite.

## Key architectural decision — subprocess orchestration

The project has **two Python environments**: `python3` carries `anthropic` (produce);
`.venv-video/bin/python` carries Kokoro/whisper (render). A single process cannot import
both. Therefore `run_auto.py` orchestrates by **shelling out to each stage with the
correct interpreter** — matching the existing `run_produce` / `run_video` split, and
ensuring render runs in a shell where `npx` (Chromium render, ~45 min) is available. An
in-process pipeline is not possible without merging the venvs.

## Components

### 1. `engine/pipeline/qc.py` — local quality gate (no API)

`qc_video(idea_id: str) -> dict` runs three local checks, writes `produced/<id>/qc.json`,
and returns a structured report `{passed: bool, checks: [{name, passed, detail}], ...}`.

| Check | Mechanism | Catches |
|-------|-----------|---------|
| `render_integrity` | `ffprobe` — file exists, has both a video and an audio stream, and video duration is within `QC_DURATION_TOLERANCE` of the **narration audio** duration (the ground-truth length both are built from) | truncated / failed / silent / audio-video-mismatch renders |
| `brightness_band` | `ffmpeg signalstats` mean luma (`YAVG`) across sampled frames must sit within `[min, max]` | the darkness bug (latter-half near-black) |
| `caption_coverage` | whisper word-timings (already produced) must span ≥ `MIN_CAPTION_COVERAGE` of audio duration with no gap > `MAX_CAPTION_GAP_S` | caption-less / silent stretches |

- Thresholds live in `config.py`: `QC_BRIGHTNESS_MIN`, `QC_BRIGHTNESS_MAX`,
  `QC_MIN_CAPTION_COVERAGE`, `QC_MAX_CAPTION_GAP_S`, `QC_DURATION_TOLERANCE`. The
  orchestrator's `RENDER_TIMEOUT_S` (default 5400 = 90 min) lives here too.
- Shells `ffprobe`/`ffmpeg` (already required by the render stack). No network, no API.
- Self-stubs on missing inputs (e.g. no word-timings file → that check reports
  `passed: false, detail: "no timings"`, never crashes).
- `passed` is the AND of all checks.

### 2. `engine/run_auto.py` — orchestrator CLI (runs in the user's shell)

**Pipeline mode** — `run_auto.py [--count N] [--no-render]` (default `N=1`):
For each of the top-`N` `pending` ideas (highest viral score first):
1. **produce** — subprocess `python3 -m engine.run_produce --id <id>`. Re-read the idea;
   proceed to render only if **cleared**: status `in_production` (auto fact-gate passed)
   **OR** `human_reviewed: True` (manual override — see below). Otherwise (`needs_review`
   and not human-reviewed) **stop this idea**, log, continue to the next. Never render an
   unverified, un-reviewed script.
2. **render** — subprocess `.venv-video/bin/python -m engine.run_video --id <id> --render
   --mode narrated`, with a **hard timeout** of `RENDER_TIMEOUT_S` (config; default 90 min).
   On non-zero exit **or timeout**, mark `render_failed`, continue. A hung Chromium never
   exits on its own, so the timeout is the real failure detector — not the exit code.
   The render is launched in its **own process group** (`start_new_session=True`); on
   `subprocess.TimeoutExpired` the whole group is killed (`os.killpg`), because the venv
   python spawns `npx` → Chromium grandchildren that survive a kill of the immediate child.
   (`--no-render` skips steps 2–3 for dry-testing the selection/produce path.)
3. **QC** — `qc.qc_video(id)`. **pass** → mark `awaiting_approval`. **fail** → mark
   `qc_failed` (keep `qc.json`). Never publishes.

One idea failing must never abort the batch. The per-idea render timeout also bounds the
worst-case wall-clock of a `--count N` run to `N × RENDER_TIMEOUT_S`.

**Approval CLI** (the human gate) — fully decoupled from produce/render; every subcommand
operates on an existing idea, so the approval/publish path is testable on its own:
- `run_auto.py --list` — table of `awaiting_approval` ideas: id, title, one-line QC summary.
- `run_auto.py --approve <id> [--public] [--dry-run]` — `uploader.upload(...)` reading
  `produced/<id>/metadata.json`; default privacy `unlisted`, `--public` to go live. On
  success mark `published`, record `youtube_url`. **`--dry-run`** loads metadata + runs the
  OAuth auth/refresh (`publish.auth`) and validates the upload payload, but **skips the
  `videos.insert`** — a real, no-side-effect smoke test that catches expired tokens and bad
  metadata before a live publish.
- `run_auto.py --review <id> [--note "..."]` — **v1, not deferred.** Cleanly sets
  `human_reviewed: True` + a dated `human_review_note` (the override fires often — see the
  override section — so the safe one-command path ships in v1, not raw `update_idea` editing).
- `run_auto.py --render <id>` — **render a single already-cleared idea, skipping produce.**
  This is the override-render path: `pipeline()` only selects `pending` ideas and re-runs
  produce (which regenerates the script), so a human-reviewed idea (status `needs_review`/
  `in_production`, not `pending`, with a hand-fixed script) is **not** reachable through the
  batch loop. `--render <id>` gates on `_cleared_to_render` then renders + QCs that one idea —
  preserving the reviewed script. Refuses (exits) if the idea isn't cleared.
- `run_auto.py --reject <id>` — mark `rejected`.

Headless-safe (no interactive prompts), sequential (TPM-safe), absolute `engine.*` imports.

### 3. Status model additions

New statuses: `awaiting_approval`, `qc_failed`, `render_failed`.

Full flow:
```
pending → producing → in_production │ needs_review
        → (render) → render_failed │ (QC) → qc_failed │ awaiting_approval
        → [human approve] → published   │ [human reject] → rejected
```

## Human-review override (clear-to-render)

The auto fact-gate is deliberately conservative and uses free DuckDuckGo search, which is
**noisy on well-documented topics** — it surfaces unrelated matches and weak sources, so a
factually-correct script on a famous event rarely reaches `passed` (zero issues AND complete
coverage). ADR-0005 anticipates this: the gate is a *flag*, and human review is the override.

Real example (Kolkata 2001, idea `85a68197`): the gate flagged 10–11 claims; on review, one
was a genuine error and the rest were search artifacts (it once pulled an *Edgbaston 2025*
match and cited a Facebook post). After fixing the real errors and cross-checking the
scorecard, the idea was cleared by setting `human_reviewed: True` while `fact_passed` stayed
`False` (honest: the auto-gate didn't pass; a human did).

**Mechanism.** A reviewer fixes the real issues, then `run_auto.py --review <id> [--note ...]`
sets `human_reviewed: True` + a dated `human_review_note`. `_cleared_to_render` treats
`human_reviewed` as an alternate **clear-to-render** signal alongside `in_production`. The auto
`fact_passed` flag is never overwritten — the two signals are kept distinct so the record stays
truthful about which gate cleared the video. The reviewer then renders the idea with
**`run_auto.py --render <id>`**, which **skips produce** (so the hand-fixed script is not
regenerated) and renders + QCs that one idea. This `--review <id>` → `--render <id>` pair is
the override path; the batch `pipeline()` cannot serve it, because it only selects `pending`
ideas and always re-runs produce. Both setter and render-path ship in v1 (not deferred) —
raw `queue_manager.update_idea` editing under time pressure is the footgun they remove.

## Error handling

- Fact-gate fail → `needs_review`, do not render **unless `human_reviewed`** (existing
  produce behavior, respected; override per the section above).
- Render fail (non-zero exit / **timeout** / no `video_path`) → `render_failed`, do not QC.
- QC fail → `qc_failed`, do not publish; `qc.json` retained for inspection.
- Publish is **always** human-initiated — the loop never auto-publishes.
- Each idea is independent; a failure logs and advances the batch.

### Retry semantics (v1: no auto-retry)

`render_failed` and `qc_failed` are **sticky terminal states for that run** — `run_auto`
does **not** auto-retry. Rationale: a render that hung once (Chromium crash, OOM) will most
likely hang again, so auto-retry just burns another `RENDER_TIMEOUT_S`; and a QC failure
(e.g. the darkness bug) is a defect to inspect, not transient noise. A human inspects the
flagged idea, fixes the cause, and **re-attempts via `run_auto.py --render <id>`** (the
single-idea render path, which skips produce and re-runs render + QC on that one cleared
idea). An automatic-retry policy (bounded attempts, backoff) is a deferred enhancement,
not v1.

## Testing

Tests run under **`python3`** (the main env), not `.venv-video`. `qc.py` and `run_auto.py`
import only stdlib + `subprocess` + existing `engine.*` modules — never the venv-only libs
(Kokoro/whisper) — which is *why* the render is shelled out rather than imported. So `pytest`
lives in the main env and the suite needs no GPU/render toolchain (only `ffprobe`/`ffmpeg` on
`PATH` for the QC fixture tests).

- `qc.py` — unit tests against the existing Escobar render
  `produced/bdffcdb7/video/…mp4` (idea id `bdffcdb7`; known-good → all checks pass) and a
  synthetically darkened copy (→ `brightness_band` fails). Pure threshold logic tested
  directly; `ffprobe`/`ffmpeg` parsing tested on fixtures.
- `run_auto.py` — `--no-render` path tested against a temp queue (no API, no render):
  verifies selection, status transitions, the `human_reviewed` clear-to-render path, and
  batch isolation on a forced failure. Approval CLI tested two ways: (a) with a mocked
  `uploader.upload` for the status transitions, and (b) a **real `--approve --dry-run`
  smoke test** against a pre-existing `awaiting_approval` idea — exercises live OAuth
  refresh + metadata-payload validation (catching token expiry / bad metadata) without
  performing the actual `videos.insert`.

## Reuse seams for the deferred Shorts build

`qc.py` is comp-agnostic (works on any MP4). `run_auto.py`'s stage sequence is the same for
vertical; the future `--vertical` branch swaps the render comp + inserts a short-script
condenser stage and a per-platform publish step. No rewrite of the orchestrator or QC.
