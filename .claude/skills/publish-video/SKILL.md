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
