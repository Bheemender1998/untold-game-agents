"""
Agent 2 — Trending Sports Agent
─────────────────────────────────
Scans current sports discourse — Reddit, Twitter/X, Google Trends,
sports news — to find topics with high RIGHT-NOW momentum that
can be given The Untold Game's signature historical depth treatment.

The logic: trending topic + historical angle = views from today's fans
AND long-term search traffic.
"""

import sys
import os

from engine.ideate.base_agent import BaseAgent
from engine.queue_manager import new_idea, add_idea
from engine.config import MAX_IDEAS_PER_RUN
from datetime import datetime


SYSTEM_PROMPT = """You are a sports content strategist and trend analyst for "The Untold Game" YouTube channel.
Your specialty is identifying what sports fans are passionately discussing RIGHT NOW and
finding the historical angle that makes it a perfect Untold Game video.

You understand that viral YouTube videos often combine:
- A trending topic (why people are searching today)
- A historical depth layer (why it matters beyond today's news)
- A surprising revelation (the untold angle)

Always respond with a valid JSON array. No preamble, no explanation outside the JSON."""


class TrendingTopicsAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.name = "trending_topics_agent"
        self.system_prompt = SYSTEM_PROMPT

    def generate_ideas(self) -> list[dict]:
        today = datetime.now().strftime("%B %Y")
        print(f"\n[{self.name}] Scanning trending sports topics ({today})...")

        prompt = f"""
{self._context_block}

TASK:
Today's date context: {today}

Use web search to find what sports fans are actively discussing RIGHT NOW:
1. Search Reddit r/sports, r/nfl, r/nba, r/soccer, r/formula1 for hot posts this week
2. Search Twitter/X sports trending topics
3. Search "sports controversy {today}" and "sports news {today}"
4. Look for upcoming anniversaries of major sports events
5. Find any players, teams, or moments currently in the news that have a deeper untold story

For each trending topic you find, identify:
- The HISTORICAL or UNTOLD angle that gives it depth beyond today's news
- Why The Untold Game's audience would care
- How to frame it so it's EVERGREEN (not just a news reaction video)

Generate exactly {MAX_IDEAS_PER_RUN} video ideas that combine trending relevance with historical depth.

Return ONLY a JSON array in this exact format:
[
  {{
    "title_variants": [
      "Primary title — historical angle on trending topic",
      "Alternative title A",
      "Alternative title B"
    ],
    "hook": "The opening sentence that hooks viewers — references the trend but pivots to the untold angle",
    "pillar": "one of: hidden_story | moments_that_changed_everything | forgotten_figure | verdict_revisited | sport_vs_world | what_if",
    "sport": "NFL | NBA | Soccer | Cricket | F1 | UFC | College | Multi-sport",
    "target_audience": "Who will click — be specific about what they already care about",
    "format_suggestion": "Long form 12-18 min | Long form 18-25 min | Short form 8-12 min",
    "thumbnail_concept": "Visual concept — what image + text combination will stop the scroll",
    "seo_keywords": ["trending keyword", "historical keyword", "keyword3", "keyword4", "keyword5"],
    "why_it_works": "Why the trending + historical combination makes this irresistible right now",
    "trending_trigger": "What is trending RIGHT NOW that makes this timely",
    "scores": {{
      "viral_overall": 8.5,
      "curiosity": 9.0,
      "emotion": 8.0,
      "search": 9.5,
      "shareability": 8.0,
      "evergreen": 6.5
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
    agent = TrendingTopicsAgent()
    agent.generate_ideas()
