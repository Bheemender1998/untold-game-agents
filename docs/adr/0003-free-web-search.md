# ADR 0003 — Free web search (DuckDuckGo) over Anthropic's paid add-on

**Status:** Accepted / LIVE (2026-06-10)

## Context
The agents need live web context. Anthropic's server-side `web_search_*` tool is
billed (~$10/1000 searches) and requires org enablement.

## Decision
Use `ddgs` (DuckDuckGo, open source, no API key) via a **client-side** tool in
`engine/ideate/web_search.py`: Claude emits a query, we run it locally for free
and feed results back through the existing agentic loop.

## Consequences
- Run cost = Claude tokens only.
- Verified to inject current facts (e.g. a Feb-2026 news follow-up into an idea).
- Risk: DuckDuckGo may rate-limit under heavy parallel use — `search()` degrades
  gracefully (returns a note, never crashes). Add delay/cache only if it bites.
