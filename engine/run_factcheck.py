"""
The Untold Game — FACT-CHECK gate.

Verifies every concrete claim in a produced script against the web. Report only,
or --fix to rewrite the script correcting/cutting flagged claims (backs up the old
one to script.md.bak). Writes produced/<id>/factcheck.json.

Usage:
  python3 -m engine.run_factcheck --id <id>          # report
  python3 -m engine.run_factcheck --id <id> --fix    # report + correct script.md

Sequential (respects the API rate-limit tier). Headless-safe.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys

from engine.pipeline import factcheck
from engine import paths

GOLD, GREEN, RED, YELLOW, GRAY, RESET = (
    "\033[93m", "\033[92m", "\033[91m", "\033[33m", "\033[90m", "\033[0m")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _print_report(result: dict) -> None:
    issues = result["issues"]
    print(f"{GRAY}checked {result['checked']} claims · {result['supported']} supported · "
          f"{len(issues)} flagged{RESET}")
    for i in issues:
        colour = RED if i["verdict"] == "contradicted" else YELLOW
        mark = "✗ CONTRADICTED" if i["verdict"] == "contradicted" else "⚠ UNVERIFIED"
        print(f"\n{colour}{mark}{RESET}  {i['claim']}")
        if i.get("correction"):
            print(f"{GREEN}   → correct: {i['correction']}{RESET}")
        if i.get("source"):
            print(f"{GRAY}   source: {i['source']}{RESET}")
    if not result["complete"]:
        print(f"\n{YELLOW}⚠ COVERAGE INCOMPLETE — extraction hit the {result['max_claims']}-claim "
              f"cap, so more claims may be UNCHECKED. Re-run with --max-claims higher.{RESET}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fact-check gate for a produced script")
    ap.add_argument("--id", required=True)
    ap.add_argument("--format", choices=["long", "short"], default="long")
    ap.add_argument("--fix", action="store_true", help="rewrite script.md correcting flagged claims, then re-verify")
    ap.add_argument("--max-claims", type=int, default=25)
    args = ap.parse_args()

    script_file = paths.script_path(args.id, args.format)
    fc_path = paths.factcheck_path(args.id, args.format)
    if not os.path.exists(script_file):
        print(f"{RED}No script at {os.path.relpath(script_file, _ROOT)}.{RESET}")
        return 2
    with open(script_file) as f:
        script_md = f.read()

    print(f"{GOLD}▶ Fact-checking [{args.id}] — extracting + verifying claims…{RESET}")
    result = factcheck.factcheck(script_md, max_claims=args.max_claims)
    _print_report(result)

    # --fix: correct, then RE-VERIFY the corrected script so we never declare done
    # while corrections left (or introduced) flagged claims.
    if args.fix and result["issues"]:
        print(f"\n{GOLD}▶ Correcting script.md…{RESET}")
        corrected = factcheck.correct_script(script_md, result["issues"])
        shutil.copy(script_file, script_file + ".bak")
        with open(script_file, "w") as f:
            f.write(corrected)
        print(f"{GRAY}re-verifying corrected script…{RESET}")
        result = factcheck.factcheck(corrected, max_claims=args.max_claims)
        _print_report(result)

    with open(fc_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n{GRAY}report → {os.path.relpath(fc_path, _ROOT)}{RESET}")

    # Honest verdict + gate: pass ONLY if zero issues AND coverage complete.
    if result["passed"]:
        print(f"{GREEN}✓ PASSED — all {result['checked']} claims supported, coverage complete.{RESET}")
        return 0

    reasons = []
    if result["issues"]:
        reasons.append(f"{len(result['issues'])} flagged")
    if not result["complete"]:
        reasons.append("coverage incomplete")
    hint = "" if args.fix else " Run with --fix to correct, then it re-verifies."
    print(f"{RED}✗ NOT PASSED ({', '.join(reasons)}). Do NOT publish until resolved.{hint}{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
