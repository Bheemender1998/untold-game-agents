"""
Stage 3 — METADATA: optimised YouTube title, description, tags, and chapters.

Takes the idea + the produced script and returns publish-ready metadata that the
uploader (engine/publish/uploader.py) consumes directly.
"""
from __future__ import annotations

import json

import anthropic

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


# ── Shorts metadata (purpose-written description, no chapters) ────────────────

_SHORT_DESC_SYSTEM = """You write the description for a YouTube SHORT on a sports-history
channel. In 2-3 short sentences, hook the viewer and tease the intrigue — do NOT spoil the
ending or state the payoff. Plain text only: no markdown, no 'MOOD:' line, no hashtags, no
preamble or labels."""

_SHORT_DESC_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["description", "tags"],
    "additionalProperties": False,
}


def _short_desc_llm(idea: dict, script: str) -> tuple[str, list[str]]:
    """One structured call → (description, tags) for a Short. Raises on failure."""
    client = anthropic.Anthropic(max_retries=5)
    prompt = (f"TITLE: {idea['title_variants'][0]}\n"
              f"SPORT: {idea.get('sport', '')}  PILLAR: {idea.get('pillar', '')}\n\n"
              f"SCRIPT:\n{script}\n\nWrite the Short description and tags.")
    resp = client.messages.create(
        model=MODEL, max_tokens=512, system=_SHORT_DESC_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _SHORT_DESC_SCHEMA}},
    )
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return data["description"].strip(), list(data.get("tags", []))


def generate_short_metadata(idea: dict, script: str) -> dict:
    """Title + a purpose-written 2-3 sentence description + tags for a Short.
    Self-stubs to a minimal description (first clean line) if the LLM call fails. Music
    credit is added later at render time by engine.video.music.write_credit."""
    title = idea["title_variants"][0]
    sport = idea.get("sport", "")
    pillar = idea.get("pillar", "")
    try:
        body, llm_tags = _short_desc_llm(idea, script)
    except Exception:
        # Self-stub: first real narration line, skipping any '# heading' / 'MOOD:' scaffolding.
        body = next((ln.strip() for ln in script.splitlines()
                     if ln.strip() and not ln.strip().startswith("#")
                     and not ln.strip().upper().startswith("MOOD:")), title)
        llm_tags = []
    hashtags = "#Shorts" + (f" #{sport.replace(' ', '')}" if sport else "")
    from engine.config import CHANNEL_HANDLE
    cta = f"\U0001F44D Like · \U0001F4AC Comment · \U0001F514 Subscribe → {CHANNEL_HANDLE}"
    description = f"{body}\n\n{hashtags}\n\n{cta}"
    tags = list(dict.fromkeys([t for t in ["Shorts", sport, pillar, *llm_tags] if t]))[:30]
    return {"title": title, "description": description, "tags": tags}


def run(idea: dict) -> dict:
    """Pipeline stage: attach `metadata` to the idea dict (requires idea['script'])."""
    out = dict(idea)
    out["metadata"] = generate_metadata(idea, idea.get("script", ""))
    return out
