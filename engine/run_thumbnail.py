"""The Untold Game — THUMBNAIL stage entrypoint.

Composite the 'Prestige Feed Killer' thumbnail for a produced idea from its
human-supplied subject photo (produced/<id>/<fmt>/subject.png|jpg).

Usage:
  python3 -m engine.run_thumbnail --id 2922268d
  python3 -m engine.run_thumbnail --id 2922268d --format short
"""
from __future__ import annotations
import argparse
import os
import sys

from engine import paths, queue_manager as q
from engine.pipeline import thumbnail


def main() -> None:
    ap = argparse.ArgumentParser(description="The Untold Game — generate a video thumbnail")
    ap.add_argument("--id", required=True, help="idea id")
    ap.add_argument("--format", choices=["long", "short"], default="long")
    args = ap.parse_args()

    idea = q.get_by_id(args.id) or {"id": args.id}
    subject = paths.subject_path(args.id, args.format)
    if not os.path.exists(subject):
        print(f"No subject photo for [{args.id}/{args.format}]. Drop one at: {subject}")
        sys.exit(1)
    thumbnail.generate_thumbnail(idea, args.format)
    print(f"✓ thumbnail at {paths.thumbnail_path(args.id, args.format)}")


if __name__ == "__main__":
    main()
