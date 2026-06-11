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
  `QC_MIN_CAPTION_COVERAGE`, `QC_MAX_CAPTION_GAP_S`, `QC_DURATION_TOLERANCE`.
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
   --mode narrated`. On non-zero exit, mark `render_failed`, continue.
   (`--no-render` skips steps 2–3 for dry-testing the selection/produce path.)
3. **QC** — `qc.qc_video(id)`. **pass** → mark `awaiting_approval`. **fail** → mark
   `qc_failed` (keep `qc.json`). Never publishes.

One idea failing must never abort the batch.

**Approval CLI** (the human gate):
- `run_auto.py --list` — table of `awaiting_approval` ideas: id, title, one-line QC summary.
- `run_auto.py --approve <id> [--public]` — `uploader.upload(...)` reading
  `produced/<id>/metadata.json`; default privacy `unlisted`, `--public` to go live. On
  success mark `published`, record `youtube_url`.
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

**Mechanism.** A reviewer fixes the real issues, then sets two fields on the idea:
`human_reviewed: True` and a dated `human_review_note`. `run_auto` treats `human_reviewed`
as an alternate **clear-to-render** signal alongside `in_production`. The auto `fact_passed`
flag is never overwritten — the two signals are kept distinct so the record stays truthful
about which gate cleared the video. (A future CLI helper — `run_auto.py --review <id>` — can
set these fields, but manual editing via `queue_manager.update_idea` is the v1 path.)

## Error handling

- Fact-gate fail → `needs_review`, do not render **unless `human_reviewed`** (existing
  produce behavior, respected; override per the section above).
- Render fail (non-zero exit / no `video_path`) → `render_failed`, do not QC.
- QC fail → `qc_failed`, do not publish; `qc.json` retained for inspection.
- Publish is **always** human-initiated — the loop never auto-publishes.
- Each idea is independent; a failure logs and advances the batch.

## Testing

- `qc.py` — unit tests against the existing Escobar `produced/<id>/video/…mp4` (known-good
  → all pass) and a synthetically darkened copy (→ `brightness_band` fails). Pure functions
  for threshold logic tested directly; ffprobe/ffmpeg parsing tested on fixtures.
- `run_auto.py` — `--no-render` path tested against a temp queue (no API, no render):
  verifies selection, status transitions, and batch isolation on a forced failure. Approval
  CLI tested with a mocked `uploader.upload`.

## Reuse seams for the deferred Shorts build

`qc.py` is comp-agnostic (works on any MP4). `run_auto.py`'s stage sequence is the same for
vertical; the future `--vertical` branch swaps the render comp + inserts a short-script
condenser stage and a per-platform publish step. No rewrite of the orchestrator or QC.
