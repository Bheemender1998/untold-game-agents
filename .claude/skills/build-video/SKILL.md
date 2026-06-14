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
