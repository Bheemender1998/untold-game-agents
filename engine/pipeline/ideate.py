"""Stage 0 — IDEATE (LIVE). Thin wrapper over the working idea-generation agents."""
from __future__ import annotations

from engine.ideate.sports_history_agent import SportsHistoryAgent
from engine.ideate.trending_topics_agent import TrendingTopicsAgent
from engine.ideate.competitor_gap_agent import CompetitorGapAgent
from engine.ideate.evergreen_agent import EvergreenAgent

AGENTS = [SportsHistoryAgent, TrendingTopicsAgent, CompetitorGapAgent, EvergreenAgent]


def run() -> list:
    """Run every agent; returns all freshly-queued idea dicts."""
    ideas = []
    for cls in AGENTS:
        ideas.extend(cls().generate_ideas())
    return ideas
