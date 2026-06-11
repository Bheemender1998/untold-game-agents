---
name: run-pipeline
description: Run the idea-generation agents and/or review the queue for The Untold Game. Use when the user says "run the pipeline", "generate ideas", "run the agents", "/run-pipeline", or wants to see queued ideas.
---

# Run the pipeline

Working dir: `/Users/bheemendergurram/untold_game_agents`. Always `python3`.

The review dashboard is **interactive** (`input()` prompts) — you cannot drive it.
For generation, pipe `n` to skip the dashboard, then show the user the ideas from
the queue. For interactive review, hand the command to the user.

- **Generate (one agent, cheapest):** `echo n | python3 -m engine.run_pipeline --agent 1`
  (1=history 2=trending 3=gaps 4=evergreen). Free DuckDuckGo search; Claude tokens only.
- **Generate (all 4):** `echo n | python3 -m engine.run_pipeline --sequential`
- **Show results:** read `queue/idea_queue.json`; print title/hook/why/scores per idea.
- **Stats:** `python3 -m engine.run_pipeline --stats`
- **Interactive review (user runs):** `python3 -m engine.run_pipeline --review`

Preconditions: `.env` has `ANTHROPIC_API_KEY` (shared with ConvictionFinder);
`pip install -r requirements.txt` done. `[web_search error ...]` = DuckDuckGo
rate-limiting (not a crash); retry or run sequentially.
