---
name: preflight-qc
description: Run the pre-flight QC lint on a produced video's props.json before the 45-min render — auto-fix caption/headline/timing defects (split numbers, zero-duration captions, overlaps, duplicate/stuck headlines) and block the render on unfixed CRITICAL defects. Use when the user says "lint the captions", "pre-flight check <id>", "check props before render", or "/preflight-qc".
---

# Pre-flight QC lint

Wraps `python3 -m engine.run_preflight`. Operates on `produced/<id>/<fmt>/video/props.json`
(build it first with `run_video` *without* `--render`). The lint also runs automatically
inside `run_video.py` before every Remotion render.

## Steps

1. Ensure props exist: `python3 -m engine.run_video --id <id> [--format short]` (no `--render`).
2. Report only: `python3 -m engine.run_preflight --id <id> [--format short]`.
3. Apply fixes: add `--fix` (rewrites `props.json` + `captions.srt`).
4. Read `produced/<id>/<fmt>/qc_lint.json` — `checks` (severity/passed/fixed) and the
   `mutations` audit trail (exactly what text/timestamps were changed and why).

## Gate

Exits non-zero (and `run_video` skips the render, marking the idea `needs_review`) when any
CRITICAL check is still failing after the single auto-fix pass. CRITICAL: split-number/
orphan-punct captions, ghost-after-audio, zero/sub-frame duration, non-monotonic captions,
headline overlap, duplicate headline, structural. WARN (never blocks): fillers dropped,
oversize token, stuck headline.

Scope: pre-flight (props.json) only. Post-render checks live in `engine/pipeline/qc.py`.
