"""
Stage 3 — METADATA: optimised YouTube title, description, tags, and chapters.

Takes the idea + the produced script and returns publish-ready metadata that the
uploader (engine/publish/uploader.py) consumes directly.
"""
from __future__ import annotations

import json

from engine.ideate.base_agent import BaseAgent
from engine.config import MODEL, MAX_TOKENS

METADATA_SYSTEM = """You are a YouTube SEO and packaging strategist for "The Untold Game"
(sports-history documentaries). You turn a finished script into publish-ready metadata
that maximises click-through and watch time without clickbait that betrays the content.

- TITLE: <= 100 chars, curiosity-driven, front-load the hook, no ALL CAPS spam.
- DESCRIPTION: first 2 lines are the hook (visible before "...more"); then a 2-3 sentence
  summary; then a "Chapters:" block with timestamps; then a short SEO paragraph naturally
  using the keywords; then a CTA line (subscribe). Use real line breaks.
- TAGS: <= 30, specific entities + search terms from the script and seo_keywords.
- CHAPTERS: derive from the script's sections. The first chapter MUST be 00:00. Estimate
  timestamps from section length assuming ~150 spoken words per minute. Keep titles tight."""

# Structured-output schema — guarantees valid JSON (Sonnet 4.6 supports output_config.format),
# so no fragile regex/json.loads-on-model-prose.
_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"time": {"type": "string"}, "title": {"type": "string"}},
                "required": ["time", "title"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "description", "tags", "chapters"],
    "additionalProperties": False,
}


class MetadataWriter(BaseAgent):
    def __init__(self):
        super().__init__()
        self.name = "metadata_writer"
        self.system_prompt = METADATA_SYSTEM

    def write(self, idea: dict, script: str) -> dict:
        prompt = f"""{self._context_block}

Produce optimised metadata for this video.

CANDIDATE TITLES (refine, don't just copy):
{chr(10).join('- ' + t for t in idea['title_variants'])}

HOOK:         {idea['hook']}
SPORT:        {idea['sport']}  ·  PILLAR: {idea['pillar']}
SEO KEYWORDS: {', '.join(idea['seo_keywords'])}

SCRIPT:
{script}"""
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)


def generate_metadata(idea: dict, script: str) -> dict:
    """Return {title, description, tags, chapters} for an idea + its script."""
    return MetadataWriter().write(idea, script)


def run(idea: dict) -> dict:
    """Pipeline stage: attach `metadata` to the idea dict (requires idea['script'])."""
    out = dict(idea)
    out["metadata"] = generate_metadata(idea, idea.get("script", ""))
    return out
