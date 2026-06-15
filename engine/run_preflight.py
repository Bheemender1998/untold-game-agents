"""
The Untold Game — PRE-FLIGHT QC lint.

Lints a produced video's props.json (captions + chapters) BEFORE the render:
auto-fixes deterministic caption/headline/timing defects, reports the rest.
Exits non-zero if any CRITICAL defect remains unfixed (the render gate).

Usage:
  python3 -m engine.run_preflight --id <id>                 # report only
  python3 -m engine.run_preflight --id <id> --fix           # rewrite props.json + captions.srt
  python3 -m engine.run_preflight --id <id> --format short  # the short cut
"""
from __future__ import annotations
import argparse
import json
import os
import sys

from engine import paths
from engine.video import captions, preflight

GOLD, GREEN, RED, YELLOW, GRAY, RESET = (
    "\033[93m", "\033[92m", "\033[91m", "\033[33m", "\033[90m", "\033[0m")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _print_report(report: dict) -> None:
    for c in report["checks"]:
        if c["passed"] and not c["fixed"]:
            continue
        mark = (f"{GREEN}✓ fixed" if c["passed"] and c["fixed"]
                else f"{RED}✗ {c['severity'].upper()}" if c["severity"] == "critical"
                else f"{YELLOW}⚠ warn")
        print(f"{mark}{RESET}  {c['name']}: {c['detail']}"
              + (f"  ({c['fixed']} auto-fixed)" if c["fixed"] else ""))
    for m in report["mutations"]:
        print(f"{GRAY}   · {m['type']}: {m.get('into') or m.get('token')} [{m['reason']}]{RESET}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-flight QC lint for a produced props.json")
    ap.add_argument("--id", required=True)
    ap.add_argument("--format", choices=["long", "short"], default="long")
    ap.add_argument("--fix", action="store_true", help="rewrite props.json + captions.srt with fixes")
    args = ap.parse_args()

    vdir = paths.video_dir(args.id, args.format)
    props_path = os.path.join(vdir, "props.json")
    if not os.path.exists(props_path):
        print(f"{RED}No props.json at {os.path.relpath(props_path, _ROOT)}. "
              f"Run `python3 -m engine.run_video --id {args.id}` first.{RESET}")
        return 2
    with open(props_path) as f:
        props = json.load(f)

    print(f"{GOLD}▶ Pre-flight QC [{args.id}/{args.format}] — linting props.json…{RESET}")
    fixed, report = preflight.lint_props(props, props.get("fps", 30), props.get("narrationMs", 0))
    _print_report(report)

    qc_path = os.path.join(paths.artifact_dir(args.id, args.format), "qc_lint.json")
    with open(qc_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"{GRAY}report → {os.path.relpath(qc_path, _ROOT)}{RESET}")

    if args.fix:
        with open(props_path, "w") as f:
            json.dump(fixed, f, indent=2)
        srt_chunks = captions.chunk_words_to_captions(
            [{"word": c["text"], "start": c["startMs"] / 1000.0, "end": c["endMs"] / 1000.0}
             for c in fixed["captions"]])
        captions.to_srt(srt_chunks, os.path.join(vdir, "captions.srt"))
        print(f"{GREEN}✓ wrote fixed props.json + captions.srt{RESET}")

    if report["blocked"]:
        failing = [c["name"] for c in report["checks"]
                   if c["severity"] == "critical" and not c["passed"]]
        print(f"{RED}✗ BLOCKED — unfixed CRITICAL: {', '.join(failing)}. "
              f"Do NOT render until resolved.{RESET}")
        return 1
    print(f"{GREEN}✓ PASSED — no unfixed CRITICAL defects.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
