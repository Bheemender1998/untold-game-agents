"""
Agent 3 — Competitor Gap Agent
────────────────────────────────
Analyzes what the top sports storytelling channels are producing
and finds the GAPS — stories they haven't told, angles they've missed,
audiences they're not serving.

Top competitor channels analyzed:
- Secret Base / SB Nation
- B/R Football
- The Ringer
- NFL Films
- Copa90
- GQ Sports
- Bleacher Report
"""

import sys
import os

from engine.ideate.base_agent import BaseAgent
from engine.queue_manager import new_idea, add_idea
from engine.config import MAX_IDEAS_PER_RUN


SYSTEM_PROMPT = """You are a competitive intelligence analyst and YouTube content strategist for "The Untold Game."
Your job is to find the GAPS in what competitor sports YouTube channels are producing —
the stories they haven't told, the angles they've ignored, the audiences they've left underserved.

You think like a chess player — always looking two moves ahead. If Secret Base covered
a player's career, you find the story SECRET BASE MISSED about that same player.
If B/R Football covered a famous match, you find the behind-the-scenes story NOBODY covered.

The goal is differentiation: The Untold Game should never be the second channel to tell a story.

Always respond with a valid JSON array. No preamble, no explanation outside the JSON."""


class CompetitorGapAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.name = "competitor_gap_agent"
        self.system_prompt = SYSTEM_PROMPT

    def generate_ideas(self) -> list[dict]:
        print(f"\n[{self.name}] Analysing competitor content gaps...")

        prompt = f"""
{self._context_block}

TASK:
Use web search to analyze what the top sports storytelling YouTube channels have recently published:
- Search "Secret Base YouTube 2024 2025" for their recent videos
- Search "B/R Football YouTube recent videos"
- Search "The Ringer sports YouTube"
- Search "NFL Films YouTube recent"
- Search "Copa90 YouTube recent"

For each competitor, identify:
1. What topics they KEEP covering (saturated ground — avoid)
2. What topics they've NEVER covered (white space — target)
3. What topics they covered SUPERFICIALLY that deserve a deep dive
4. What AUDIENCE SEGMENTS they're ignoring (international fans, women's sports, historical deep divers)

Then generate {MAX_IDEAS_PER_RUN} video ideas that fill specific gaps in the market.
Each idea should be something a competitor HAS NOT done well or hasn't done at all.

Return ONLY a JSON array in this exact format:
[
  {{
    "title_variants": [
      "Primary title — owns the gap",
      "Alternative title A",
      "Alternative title B"
    ],
    "hook": "Opening sentence — immediately signals this is different from anything viewers have seen",
    "pillar": "one of: hidden_story | moments_that_changed_everything | forgotten_figure | verdict_revisited | sport_vs_world | what_if",
    "sport": "NFL | NBA | Soccer | Cricket | F1 | UFC | College | Multi-sport",
    "target_audience": "Who is underserved by competitors that this video reaches",
    "format_suggestion": "Long form 12-18 min | Long form 18-25 min | Short form 8-12 min",
    "thumbnail_concept": "Thumbnail concept that looks different from competitor thumbnails",
    "seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
    "why_it_works": "Why this fills a real gap — name the specific competitor who missed this",
    "gap_identified": "One sentence: what specific gap in the market does this fill?",
    "scores": {{
      "viral_overall": 8.0,
      "curiosity": 8.5,
      "emotion": 7.5,
      "search": 8.0,
      "shareability": 8.5,
      "evergreen": 9.0
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
                format_suggestion= d.get("format_suggestion", "Long form 12-18 min"),
            )
            if add_idea(idea):
                added.append(idea)

        print(f"[{self.name}] Done — {len(added)} ideas added to queue")
        return added


if __name__ == "__main__":
    agent = CompetitorGapAgent()
    agent.generate_ideas()
