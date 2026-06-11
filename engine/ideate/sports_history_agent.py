"""
Agent 1 — Sports History Agent
────────────────────────────────
Digs into the historical record to surface forgotten moments,
overlooked dynasties, and buried stories that haven't been told on YouTube.
Uses web search to verify historical accuracy and check for existing coverage gaps.
"""

import sys
import os

from engine.ideate.base_agent import BaseAgent
from engine.queue_manager import new_idea, add_idea
from engine.config import MAX_IDEAS_PER_RUN


SYSTEM_PROMPT = """You are a sports historian and YouTube content strategist for "The Untold Game" channel.
Your specialty is uncovering forgotten moments, overlooked dynasties, buried records, and
misremembered history across NFL, NBA, Soccer, Cricket, Formula 1, UFC, and college sports.

You think like a documentary filmmaker — you're looking for stories with:
- A protagonist the viewer will root for (or against)
- A turning point that changed everything
- A "you won't believe this" revelation
- Rich archival potential (old footage, photos, documents)

Always respond with a valid JSON array. No preamble, no explanation outside the JSON."""


class SportsHistoryAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        self.name = "sports_history_agent"
        self.system_prompt = SYSTEM_PROMPT

    def generate_ideas(self) -> list[dict]:
        print(f"\n[{self.name}] Searching for forgotten sports history stories...")

        prompt = f"""
{self._context_block}

TASK:
Search the web for underreported, forgotten, or misremembered sports history stories
that would make outstanding YouTube videos for The Untold Game channel.

Focus on stories that:
1. Happened but were never properly documented on YouTube
2. Involve a dramatic turning point most fans don't know about
3. Have strong "I can't believe I never knew this" energy
4. Span NFL, NBA, soccer, cricket, F1, or UFC history

Use web search to:
- Find sports history topics trending on Reddit r/sports, r/nfl, r/soccer etc.
- Check what the top sports history YouTube channels (Secret Base, B/R Football) have NOT covered
- Look for anniversary stories (events from 10, 20, 25, 50 years ago this year)

Generate exactly {MAX_IDEAS_PER_RUN} video ideas.

Return ONLY a JSON array in this exact format:
[
  {{
    "title_variants": [
      "Primary title option",
      "Alternative title option A",
      "Alternative title option B"
    ],
    "hook": "The opening sentence that would start the video narration",
    "pillar": "one of: hidden_story | moments_that_changed_everything | forgotten_figure | verdict_revisited | sport_vs_world | what_if",
    "sport": "NFL | NBA | Soccer | Cricket | F1 | UFC | College | Multi-sport",
    "target_audience": "Who specifically will click on this",
    "format_suggestion": "Long form 12-18 min | Long form 18-25 min | Short form 8-12 min",
    "thumbnail_concept": "One sentence describing the thumbnail visual",
    "seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
    "why_it_works": "2-3 sentences on the viral/emotional mechanics of this idea",
    "scores": {{
      "viral_overall": 8.5,
      "curiosity": 9.0,
      "emotion": 8.0,
      "search": 7.5,
      "shareability": 8.5,
      "evergreen": 8.0
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
    agent = SportsHistoryAgent()
    agent.generate_ideas()
