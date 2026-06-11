"""
Free web search — open-source, no API key, no paid add-on.

Backed by DuckDuckGo via the `ddgs` package (https://github.com/deedy5/ddgs),
which scrapes DuckDuckGo's public results. This replaces Anthropic's paid
server-side `web_search` tool: the same idea (give Claude live web context),
but it costs nothing beyond Claude tokens.

Exposed to Claude as a *client-side* tool — Claude emits a search query, we run
it here, and feed the results back (see base_agent.BaseAgent._call).
"""
from __future__ import annotations


# Tool definition handed to Claude. Client-side custom tool (we execute it),
# NOT Anthropic's server-side web_search_* tool (which is billed per search).
WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for current, real-world information (recent events, "
        "anniversaries, trending topics, what competitors have published). "
        "Returns a list of result titles, URLs, and snippets. "
        "Call this whenever an idea depends on facts you can't be certain of."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query, e.g. 'NFL forgotten 1980s playoff upsets'",
            },
        },
        "required": ["query"],
    },
}


def search(query: str, max_results: int = 6) -> str:
    """Run a free DuckDuckGo text search and return a plain-text result block.

    Degrades gracefully: on any error (rate limit, network, no results) it
    returns a short note instead of raising, so a single bad search never
    crashes the agent run.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        return "[web_search unavailable: `pip install ddgs`]"

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:  # noqa: BLE001 — never let search kill the run
        return f"[web_search error for '{query}': {e}]"

    if not results:
        return f"[no web results for '{query}']"

    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        url = r.get("href", "") or r.get("url", "")
        body = (r.get("body", "") or "").strip()
        lines.append(f"{i}. {title}\n   {url}\n   {body}")
    return "\n".join(lines)
