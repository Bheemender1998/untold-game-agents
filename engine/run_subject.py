"""The Untold Game — auto-source a subject photo (Wikipedia lead image → Pexels fallback)
for a video's thumbnail. A human-supplied subject.png always wins.

Usage:
  python3 -m engine.run_subject --id 648d57e6 --format short
"""
from __future__ import annotations
import argparse

from engine import queue_manager as q
from engine.pipeline import subject


def main() -> None:
    ap = argparse.ArgumentParser(description="The Untold Game — source a subject photo")
    ap.add_argument("--id", required=True, help="idea id")
    ap.add_argument("--format", choices=["long", "short"], default="long")
    args = ap.parse_args()

    idea = q.get_by_id(args.id) or {"id": args.id}
    res = subject.source_subject(idea, args.format)
    src = res["source"]
    if src == "human":
        print(f"· [{args.id}/{args.format}] already has a subject photo — left untouched")
    elif src:
        print(f"✓ [{args.id}/{args.format}] subject.png via {src} — {res['credit']}")
    else:
        print(f"✗ [{args.id}/{args.format}] no photo found — drop one at {res['path']}")


if __name__ == "__main__":
    main()
