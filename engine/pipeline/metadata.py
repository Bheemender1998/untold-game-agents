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
from engine.usage import logged_create
from engine.pipeline.script import title_numbers_within

METADATA_SYSTEM = """You are a YouTube SEO and packaging strategist for "The Untold Game"
(sports-history documentaries). You turn a finished script into publish-ready metadata
that maximises click-through and watch time without clickbait that betrays the content.

- TITLE: <= 100 chars, no ALL CAPS spam. Open the gap by withholding the resolution, never by
  editorializing — make the unanswered question irresistible ("Ten days after this own goal, he
  was dead.") without giving away the payoff and without asserting framing not literally supported
  by the script ("The Lie America Believed" is spin, not withholding — banned). Same specifics
  rule as the script: exact verified values or none, no invented superlatives.
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
        response = logged_create(self.client, "metadata",
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

_SHORT_TITLE_SYSTEM = """You write the TITLE for a YouTube SHORT on a sports-history channel.
One line, <= ~70 characters so it stays legible on a phone. Punchy and front-loaded.

Open the gap by withholding the resolution, never by editorializing: make the unanswered question
irresistible without giving away the payoff, and assert no framing not literally supported by the
script. Use ONLY facts in the script — introduce no name, number, or date that isn't there. Any
specific you include must be the EXACT value from the script: never round, never invent a
superlative. Plain text only: no surrounding quotes, no hashtags, no emoji, no preamble or labels."""

_SHORT_TITLE_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}


def _short_title_llm(idea: dict, script: str) -> str:
    """One structured call → a punchy, front-loaded, gap-opening SHORT title. Raises on failure.
    Length (~70 chars) is a prompt-level soft target only — structured outputs do NOT enforce
    maxLength on this raw output_config.format path, so do not add it to the schema."""
    client = anthropic.Anthropic(max_retries=5)
    prompt = (f"SPORT: {idea.get('sport', '')}  PILLAR: {idea.get('pillar', '')}\n\n"
              f"SCRIPT:\n{script}\n\nWrite the Short title.")
    resp = logged_create(client, "short_title",
        model=MODEL, max_tokens=64, system=_SHORT_TITLE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _SHORT_TITLE_SCHEMA}},
    )
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return data["title"].strip()


def _short_title(idea: dict, script: str) -> str:
    """The Short's title: a dedicated front-loaded, gap-opening LLM title, guarded by the
    digit-containment backstop. Self-stubs to title_variants[0] if the LLM call fails, returns
    empty, or the backstop rejects the title (a number absent from the fact-gated script)."""
    fallback = idea["title_variants"][0]
    try:
        title = _short_title_llm(idea, script)
    except Exception:
        return fallback
    if not title:
        return fallback
    ok, _ = title_numbers_within(title, script)
    return title if ok else fallback


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
    resp = logged_create(client, "short_desc",
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
    title = _short_title(idea, script)
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
