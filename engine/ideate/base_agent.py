"""
Base Agent
──────────
All 4 idea-generation agents inherit from this.
Handles the Anthropic client, web_search tool, and robust JSON parsing.
"""

import json
import re
import anthropic
from engine.config import MODEL, MAX_TOKENS, CHANNEL_CONTEXT, VIRAL_RUBRIC

# Free, open-source web search (DuckDuckGo) — replaces Anthropic's paid
# server-side web_search add-on. Defined as a client-side tool we execute.
from engine.ideate.web_search import WEB_SEARCH_TOOL, search as run_web_search
from engine.usage import logged_create


class BaseAgent:
    """
    Shared foundation for all idea-generation agents.

    Subclasses must implement:
      - self.name (str)
      - self.system_prompt (str)
      - generate_ideas() -> list[dict]
    """

    def __init__(self):
        # max_retries: the org is on a low TPM tier and web-search context bulks
        # up prompts — let the SDK back off and retry 429s instead of crashing.
        self.client = anthropic.Anthropic(max_retries=5)
        self.name = "base_agent"
        self.system_prompt = ""

    # ── Core API call ──────────────────────────────────────────────────────────

    def _call(self, user_message: str, use_search: bool = True) -> str:
        """
        Call Claude with optional web search.
        Handles tool_use blocks automatically — loops until final text.
        Returns the full text response.
        """
        tools = [WEB_SEARCH_TOOL] if use_search else []
        messages = [{"role": "user", "content": user_message}]
        full_text = ""

        # Agentic loop — keeps going until no more tool_use blocks
        while True:
            kwargs = {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "system": self.system_prompt,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools

            response = logged_create(self.client, self.name, **kwargs)

            # Collect text and tool_use blocks
            text_blocks = []
            tool_use_blocks = []
            for block in response.content:
                if block.type == "text":
                    text_blocks.append(block.text)
                elif block.type == "tool_use":
                    tool_use_blocks.append(block)

            full_text += " ".join(text_blocks)

            # Warn loudly if the model ran out of output budget — the JSON will
            # be truncated and _extract_json will fail. Bump MAX_TOKENS in config.
            if response.stop_reason == "max_tokens":
                print(f"[{self.__class__.__name__}] WARNING: hit max_tokens "
                      f"({MAX_TOKENS}); output truncated. Raise MAX_TOKENS in config.py.")

            # If no tool calls, we're done
            if not tool_use_blocks or response.stop_reason == "end_turn":
                break

            # Append assistant turn, then run each requested search locally
            # (free DuckDuckGo) and feed the results back as tool_results.
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tb in tool_use_blocks:
                if tb.name == "web_search":
                    query = (tb.input or {}).get("query", "")
                    result_content = run_web_search(query)
                else:
                    result_content = f"[unknown tool: {tb.name}]"
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tb.id,
                    "content": str(result_content),
                })
            messages.append({"role": "user", "content": tool_results})

        return full_text.strip()

    # ── JSON extraction ────────────────────────────────────────────────────────

    def _extract_json(self, text: str) -> list[dict]:
        """
        Extract a JSON array from a Claude response.
        Tries fenced code blocks first, then raw array search.
        """
        # Try ```json ... ``` fence
        fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        if fence:
            return json.loads(fence.group(1))

        # Try bare array
        arr = re.search(r"(\[.*\])", text, re.DOTALL)
        if arr:
            return json.loads(arr.group(1))

        raise ValueError(f"No JSON array found in response:\n{text[:500]}")

    # ── Shared context injected into every prompt ──────────────────────────────

    @property
    def _context_block(self) -> str:
        return f"""
CHANNEL CONTEXT:
{CHANNEL_CONTEXT}

VIRAL SCORING RUBRIC:
{VIRAL_RUBRIC}
"""
