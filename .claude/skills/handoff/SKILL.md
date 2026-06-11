---
name: handoff
description: Append a session-wrap entry to HANDOFF.md so the next agent (or next-you) can pick up. Use when the user says "wrap the session", "handoff", "/handoff", or signals end-of-session ("let's stop here", "good place to stop").
---

# Handoff — append a session wrap

When invoked, write a new dated entry at the **top** of the session list in
`/Users/bheemendergurram/untold_game_agents/HANDOFF.md` (newest first), under the
`---` divider. Keep existing entries intact.

Each entry must have:

- **Heading**: `## Session N (YYYY-MM-DD) — <one-line theme>` (increment N).
- **Shipped**: what changed (files, behavior, fixes). State what was *verified*
  (commands run, output seen) vs assumed.
- **Open / next**: numbered, concrete next steps — the first thing next-you should do.
- **Watch-outs**: gotchas, risks, anything non-obvious.

Rules: convert relative dates to absolute; record only verified facts; capture the
*why* and *state*, not what code/git already says; keep it tight.
