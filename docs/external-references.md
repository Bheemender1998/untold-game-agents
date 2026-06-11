# External references — what's worth borrowing (and what isn't)

Reviewed 2026-06-11. For each repo: the verdict and the concrete thing (if any) to lift.
Adopt the *pattern*, wrapped to fit our conventions (two-venv, integrity rule) — never drop code in raw.

## Adopted

- **anthropics/claude-cookbooks** (MIT, Python recipes) — borrowed the **Wikipedia-RAG**
  fact-checking pattern: `engine/ideate/wikipedia.py` queries the MediaWiki API (no key) for an
  authoritative intro extract, fed to the fact-gate judge above noisy DDG snippets. This directly
  cuts the false-positives we hit on Kolkata 2001 (gate flagged 11; 8 were search artifacts).

## Reference (not code — apply over time)

- **anthropics/claude-cookbooks** — also worth lifting later:
  - **Prompt caching** — *marginal for us today*: our stable system prompts (~300–500 tok) are
    below Sonnet 4.6's 2,048-tok cache minimum, so `cache_control` would silently not trigger.
    Revisit only if a prompt prefix grows past the threshold.
  - **Haiku sub-agents** — use the cheaper model for mechanical sub-tasks (claim extraction,
    idea scoring) to cut spend; we currently run everything on Sonnet 4.6.
  - **Automated evals** — Claude-as-judge to score idea/script quality against a rubric.
- **anthropics/prompt-eng-interactive-tutorial** (notebooks) — reference for sharpening prompts.
  Most relevant chapters: Ch.4 (separate data from instructions), Ch.6 (chain-of-thought for the
  fact-check judge), **Ch.8 (avoiding hallucinations)** — maps onto the fact-gate. Our prompts are
  already fairly mature (roles, structured outputs); apply targeted, not wholesale.

## Considered, not adopted

- **anthropics/claude-code-action** (MIT, GitHub Action) — runs Claude review on PRs *server-side*.
  Genuinely fills a gap (our `pr-review-gate.sh` hook only fires in a local session). Deferred:
  needs a GitHub App install + `ANTHROPIC_API_KEY` repo secret and costs API per PR (the same
  shared key that hit a zero balance). Revisit if PRs start coming from outside a local session.
- **anthropics/swift-markdown** (Swift) — **no fit.** Swift-only Markdown parser; this is a Python
  project.
- **motiondivision/motion** (MIT, JS/React animation) — **wrong tool for the video comp.** Remotion's
  `spring`/`interpolate` are frame-deterministic (every frame must reproduce); Motion is built for
  real-time/wall-clock web animation and fights that model. Would only fit the planned Next.js
  dashboard, not the renderer.
