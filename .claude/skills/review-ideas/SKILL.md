---
name: review-ideas
description: Summarize and triage the queued video ideas for The Untold Game without the interactive dashboard. Use when the user says "show me the ideas", "review the queue", "/review-ideas", or wants a readout of pending ideas.
---

# Review ideas (non-interactive readout)

Read `/Users/bheemendergurram/untold_game_agents/queue/idea_queue.json` and present
pending ideas sorted by `scores.viral_overall` (highest first). For each: title
(+ best alt), hook, pillar · sport · format, why_it_works, thumbnail, SEO keywords,
score line.

Then give an honest triage: which ideas are genuinely specific and makeable vs
generic; flag score inflation (the model grades high — trust ranking + substance,
not absolute numbers). Do **not** edit approve/reject in the JSON — that's the
user's call via `python3 -m engine.run_pipeline --review`.
