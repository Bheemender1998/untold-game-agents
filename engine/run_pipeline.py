"""
The Untold Game — Stage 1 Pipeline Runner
──────────────────────────────────────────
Runs all 4 idea-generation agents (optionally in parallel),
then launches the interactive review dashboard.

Usage:
  python run_pipeline.py              # Run all agents
  python run_pipeline.py --agent 1    # Run only Agent 1 (sports history)
  python run_pipeline.py --review     # Skip generation, go straight to review
  python run_pipeline.py --stats      # Show queue statistics
"""

import argparse
import concurrent.futures
import sys
import os

# Ensure project root is importable

from engine.ideate.sports_history_agent import SportsHistoryAgent
from engine.ideate.trending_topics_agent import TrendingTopicsAgent
from engine.ideate.competitor_gap_agent import CompetitorGapAgent
from engine.ideate.evergreen_agent import EvergreenAgent
from engine.queue_manager import get_pending, approve, reject, stats
from engine.config import MIN_VIRAL_SCORE


# ── ANSI colours (gracefully degrades on Windows) ────────────────────────────
GOLD   = "\033[93m"
GREEN  = "\033[92m"
RED    = "\033[91m"
CYAN   = "\033[96m"
GRAY   = "\033[90m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def header():
    print(f"\n{GOLD}{BOLD}{'═'*60}")
    print("  THE UNTOLD GAME — STAGE 1: IDEA GENERATION PIPELINE")
    print(f"{'═'*60}{RESET}\n")


def run_all_agents(parallel: bool = True):
    agents = [
        SportsHistoryAgent(),
        TrendingTopicsAgent(),
        CompetitorGapAgent(),
        EvergreenAgent(),
    ]

    print(f"{CYAN}Running {len(agents)} agents {'in parallel' if parallel else 'sequentially'}...{RESET}")

    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(a.generate_ideas): a.name for a in agents}
            for future in concurrent.futures.as_completed(futures):
                agent_name = futures[future]
                try:
                    results = future.result()
                    print(f"{GREEN}  ✓ {agent_name} completed — {len(results)} ideas{RESET}")
                except Exception as e:
                    print(f"{RED}  ✗ {agent_name} failed: {e}{RESET}")
    else:
        for agent in agents:
            try:
                agent.generate_ideas()
            except Exception as e:
                print(f"{RED}  ✗ {agent.name} failed: {e}{RESET}")


def run_single_agent(agent_num: int):
    agents = {
        1: SportsHistoryAgent,
        2: TrendingTopicsAgent,
        3: CompetitorGapAgent,
        4: EvergreenAgent,
    }
    if agent_num not in agents:
        print(f"{RED}Invalid agent number. Choose 1-4.{RESET}")
        return
    agent = agents[agent_num]()
    agent.generate_ideas()


def score_bar(score: float, width: int = 10) -> str:
    filled = round(score / 10 * width)
    bar = "█" * filled + "░" * (width - filled)
    color = GREEN if score >= 8 else GOLD if score >= 6 else RED
    return f"{color}{bar}{RESET} {score}"


def review_dashboard():
    """Interactive terminal dashboard for reviewing and approving ideas."""
    ideas = get_pending(min_score=MIN_VIRAL_SCORE)

    if not ideas:
        print(f"\n{GOLD}No pending ideas in the queue.{RESET}")
        print(f"Run {CYAN}python run_pipeline.py{RESET} to generate ideas first.\n")
        return

    print(f"\n{BOLD}{'─'*60}")
    print(f"  REVIEW DASHBOARD — {len(ideas)} pending ideas")
    print(f"  Sorted by viral score (highest first)")
    print(f"{'─'*60}{RESET}\n")

    for i, idea in enumerate(ideas, 1):
        s = idea["scores"]
        titles = idea["title_variants"]

        print(f"{BOLD}{CYAN}[{i}/{len(ideas)}] ID: {idea['id']}  ·  {idea['source_agent']}{RESET}")
        print(f"\n  {BOLD}Title:{RESET}    {titles[0]}")
        if len(titles) > 1:
            print(f"  {GRAY}Alt A:{RESET}    {titles[1]}")
        if len(titles) > 2:
            print(f"  {GRAY}Alt B:{RESET}    {titles[2]}")

        print(f"\n  {BOLD}Hook:{RESET}     {idea['hook']}")
        print(f"  {BOLD}Sport:{RESET}    {idea['sport']}  ·  {idea['pillar']}  ·  {idea['format_suggestion']}")
        print(f"  {BOLD}Audience:{RESET} {idea['target_audience']}")
        print(f"\n  {BOLD}Why it works:{RESET} {idea['why_it_works']}")

        if idea.get("thumbnail_concept"):
            print(f"  {BOLD}Thumbnail:{RESET}    {idea['thumbnail_concept']}")

        print(f"\n  {BOLD}SEO keywords:{RESET} {', '.join(idea['seo_keywords'])}")

        # Score display
        print(f"\n  {BOLD}Scores:{RESET}")
        print(f"    Viral overall  {score_bar(s['viral_overall'])}")
        print(f"    Curiosity      {score_bar(s['curiosity'])}")
        print(f"    Emotion        {score_bar(s['emotion'])}")
        print(f"    Search         {score_bar(s['search'])}")
        print(f"    Shareability   {score_bar(s['shareability'])}")
        print(f"    Evergreen      {score_bar(s['evergreen'])}")

        print(f"\n  {BOLD}Action:{RESET} ", end="")
        print(f"[{GREEN}a{RESET}]pprove  [{RED}r{RESET}]eject  [{GOLD}s{RESET}]kip  [{CYAN}q{RESET}]uit")

        choice = input("  → ").strip().lower()

        if choice == "a":
            approve(idea["id"])
            print(f"  {GREEN}✓ Approved — moving to Stage 2 queue{RESET}")
        elif choice == "r":
            reason = input(f"  {GRAY}Rejection reason (optional): {RESET}").strip()
            reject(idea["id"], reason)
            print(f"  {RED}✗ Rejected{RESET}")
        elif choice == "q":
            print(f"\n{GOLD}Review paused. Resume any time with --review{RESET}\n")
            break
        else:
            print(f"  {GRAY}Skipped{RESET}")

        print(f"\n{'─'*60}\n")

    print_stats()


def print_stats():
    s = stats()
    print(f"\n{BOLD}Queue statistics:{RESET}")
    print(f"  Total ideas:       {s['total']}")
    for status, count in s.get("by_status", {}).items():
        color = GREEN if status == "approved" else RED if status == "rejected" else GOLD
        print(f"  {status.capitalize():15} {color}{count}{RESET}")
    print(f"\n  By agent:")
    for agent, count in s.get("by_agent", {}).items():
        print(f"    {agent:30} {count}")
    print(f"\n  Avg viral score:   {s['avg_viral_score']}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="The Untold Game — Stage 1 Pipeline")
    parser.add_argument("--agent", type=int, choices=[1, 2, 3, 4],
                        help="Run a single agent (1=history, 2=trending, 3=gaps, 4=evergreen)")
    parser.add_argument("--review", action="store_true",
                        help="Skip generation, go to review dashboard")
    parser.add_argument("--stats", action="store_true",
                        help="Print queue statistics and exit")
    parser.add_argument("--sequential", action="store_true",
                        help="Run agents sequentially instead of in parallel")
    parser.add_argument("--no-review", action="store_true",
                        help="Skip the interactive review prompt (use for headless/cron runs)")
    args = parser.parse_args()

    header()

    if args.stats:
        print_stats()
        return

    if args.review:
        review_dashboard()
        return

    if args.agent:
        run_single_agent(args.agent)
    else:
        run_all_agents(parallel=not args.sequential)

    print(f"\n{GOLD}All agents complete.{RESET}")
    print_stats()

    # The review dashboard is interactive (input()). Never prompt when running
    # headless (cron/CI: no TTY) or when --no-review is set — otherwise input()
    # raises EOFError and the run fails/hangs in production.
    if args.no_review or not sys.stdin.isatty():
        print(f"\n{GRAY}Headless run — skipping review. "
              f"Run `python3 -m engine.run_pipeline --review` to approve ideas.{RESET}")
        return

    print(f"\n{BOLD}Launch review dashboard?{RESET} [{GREEN}y{RESET}/n] ", end="")
    try:
        choice = input()
    except EOFError:
        return
    if choice.strip().lower() != "n":
        review_dashboard()


if __name__ == "__main__":
    main()
