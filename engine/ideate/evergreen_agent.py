"""
Agent 4 — Evergreen Content Agent
────────────────────────────────────
Generates timeless video ideas that will get views for months and years —
not tied to news cycles, not trend-dependent.

These are the videos that become the backbone of the channel:
the ones that rank in search, get recommended to new subscribers,
and drive steady sub growth long after the upload date.

Focuses on: universal human stories, legendary debates, definitive rankings,
deep character studies, and "history explains the present" angles.
"""

import sys
import os

from engine.ideate.base_agent import BaseAgent
from engine.queue_manager import new_idea, add_idea
from engine.config import MAX_IDEAS_PER_RUN


SYSTEM_PROMPT = """You are an evergreen content strategist for "The Untold Game" YouTube channel.
Your specialty is identifying video ideas that will perform for YEARS, not days.

You think about:
1. SEARCH EVERGREENS — "best X of all time", "history of X", "why X matters"
2. DEBATE EVERGREENS — questions sports fans will argue about forever
3. CHARACTER EVERGREENS — deep dives on legendary figures with universal appeal
4. GENRE EVERGREENS — stories with human themes (redemption, betrayal, obsession) that transcend sports

The test for evergreen: Would this video get views if uploaded today? In 1 year? In 5 years?
If yes to all three, it's evergreen.

Always respond with a valid JSON array. No preamble, no explanation outside the JSON."""


class EvergreenAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.name = "evergreen_agent"
        self.system_prompt = SYSTEM_PROMPT

    def generate_ideas(self) -> list[dict]:
        print(f"\n[{self.name}] Generating evergreen content ideas...")

        prompt = f"""
{self._context_block}

TASK:
Use web search to research:
1. What sports history questions do people search for repeatedly on YouTube?
2. What are the most-debated sports topics that never get resolved?
3. Search "most watched sports documentaries" and "best sports YouTube videos all time"
4. What legendary sports figures have NEVER had a proper YouTube deep dive?
5. What sports eras or dynasties are historically underrepresented online?

Generate exactly {MAX_IDEAS_PER_RUN} EVERGREEN video ideas.

Each idea must pass the 5-year test: will this still get views in 5 years?
Focus on:
- Definitive character studies of legendary/controversial figures
- "The true story of..." historical deep dives
- Legendary debates with new evidence or framing
- "History of [sport/era/team]" that doesn't exist on YouTube yet
- Universal human themes (betrayal, obsession, redemption) wrapped in sport

Return ONLY a JSON array in this exact format:
[
  {{
    "title_variants": [
      "Primary title — timeless and search-optimised",
      "Alternative title A",
      "Alternative title B"
    ],
    "hook": "Opening that works in 2025, 2027, and 2030 — not a single date reference",
    "pillar": "one of: hidden_story | moments_that_changed_everything | forgotten_figure | verdict_revisited | sport_vs_world | what_if",
    "sport": "NFL | NBA | Soccer | Cricket | F1 | UFC | College | Multi-sport",
    "target_audience": "Primary audience — and secondary audience outside core sports fans",
    "format_suggestion": "Long form 12-18 min | Long form 18-25 min | Short form 8-12 min",
    "thumbnail_concept": "Timeless thumbnail — archival image or conceptual design, no date references",
    "seo_keywords": ["high-volume keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
    "why_it_works": "Why this will get views for years — search volume + emotional timelessness",
    "five_year_test": "One sentence: why will this still be relevant in 2030?",
    "scores": {{
      "viral_overall": 8.0,
      "curiosity": 8.0,
      "emotion": 8.5,
      "search": 9.0,
      "shareability": 7.5,
      "evergreen": 9.5
    }}
  }}
]
"""
        raw = self._call(prompt, use_search=True)
        ideas_data = self._extract_json(raw)

        added = []
        for d in ideas_data:
            scores = d.get("scores", {})
            idea = new_idea(
                title_variants   = d["title_variants"],
                hook             = d["hook"],
                pillar           = d["pillar"],
                sport            = d["sport"],
                target_audience  = d["target_audience"],
                viral_score      = scores.get("viral_overall", 5.0),
                curiosity_score  = scores.get("curiosity", 5.0),
                emotion_score    = scores.get("emotion", 5.0),
                search_score     = scores.get("search", 5.0),
                share_score      = scores.get("shareability", 5.0),
                evergreen_score  = scores.get("evergreen", 5.0),
                seo_keywords     = d.get("seo_keywords", []),
                why_it_works     = d.get("why_it_works", ""),
                source_agent     = self.name,
                thumbnail_concept= d.get("thumbnail_concept", ""),
                format_suggestion= d.get("format_suggestion", "Long form 18-25 min"),
            )
            if add_idea(idea):
                added.append(idea)

        print(f"[{self.name}] Done — {len(added)} ideas added to queue")
        return added


if __name__ == "__main__":
    agent = EvergreenAgent()
    agent.generate_ideas()
