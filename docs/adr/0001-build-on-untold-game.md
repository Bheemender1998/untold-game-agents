# ADR 0001 — Build the full architecture on untold_game_agents

**Status:** Accepted (2026-06-10)

## Context
Two artifacts existed: `untold_game_agents/` (the working Stage-1 idea agents) and
`ContentPilot/` (a separate CF-style scaffold of stubs). Maintaining both split
the work and confused "which is the project".

## Decision
Make `untold_game_agents/` the single, real project. Migrate its working code into
a CF-style `engine/` package, graft ContentPilot's architecture (pipeline/publish/
ingest/outcomes/taxonomy/db/docs/skills) on top, and delete `ContentPilot/`.

## Consequences
- One codebase; the working agents become the LIVE `ideate` stage.
- Forward layers are stubs with a clear stage gating (see execution-plan).
- Imports moved to absolute `engine.*`; a root `run_pipeline.py` shim preserves
  the original command.
