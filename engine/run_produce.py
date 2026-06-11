"""
The Untold Game — PRODUCE stage entrypoint.

Turns approved ideas into production-ready output: a full narration script and
optimised YouTube metadata. Artifacts land in `produced/<id>/`, and the idea is
marked `in_production` with the artifact paths recorded on it.

Usage:
  python3 -m engine.run_produce                 # all APPROVED ideas
  python3 -m engine.run_produce --id 2922268d   # one idea by id (any status)
  python3 -m engine.run_produce --top 1         # top-scored PENDING idea (dev/testing)
  python3 -m engine.run_produce --top 1 --metadata-only  # skip the script (cheap test)

Runs sequentially (respects the API rate-limit tier). Headless-safe (no prompts).
"""
from __future__ import annotations
import argparse
import json
import os
import tempfile

from engine import queue_manager as q
from engine.pipeline.script import generate_script
from engine.pipeline.metadata import generate_metadata

GOLD, GREEN, RED, GRAY, RESET = "\033[93m", "\033[92m", "\033[91m", "\033[90m", "\033[0m"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCED_DIR = os.path.join(_ROOT, "produced")


def _atomic_write(path: str, content: str) -> None:
    """Write a file atomically (temp + os.replace) so a crash never leaves a
    truncated/half-written artifact on disk."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _select(args) -> list[dict]:
    if args.id:
        idea = q.get_by_id(args.id)
        return [idea] if idea else []
    if args.top:
        return q.get_by_status("pending")[: args.top]
    return q.get_by_status("approved")


def produce(idea: dict, metadata_only: bool = False, factcheck_enabled: bool = True,
            autofix: bool = True, max_claims: int = 25) -> dict:
    """Generate script + metadata for one idea; write artifacts; update the queue.

    The fact-gate is auto-chained: the script is verified (and auto-corrected once,
    then re-verified) before it feeds metadata. The idea is marked `in_production`
    only if the gate passes; otherwise `needs_review`.
    """
    idea_id = idea["id"]
    title = idea["title_variants"][0]
    out_dir = os.path.join(PRODUCED_DIR, idea_id)
    print(f"\n{GOLD}▶ Producing [{idea_id}] {title}{RESET}")

    script = idea.get("script", "")
    script_file = os.path.join(out_dir, "script.md")
    script_from_file = False
    if metadata_only and not script and os.path.exists(script_file):
        with open(script_file) as f:
            script = f.read()  # reuse a previously-written script
            script_from_file = True
    if metadata_only and not script:
        # No script to build metadata from — refuse rather than mark the idea
        # in_production with a script_path that points at a missing file.
        raise FileNotFoundError(
            f"--metadata-only needs an existing script for [{idea_id}] "
            f"({os.path.relpath(script_file, _ROOT)} not found). "
            f"Run a full produce first (drop --metadata-only)."
        )

    os.makedirs(out_dir, exist_ok=True)  # only after the guard — refused runs leave no dir

    # Invalidate the production record BEFORE overwriting the script artifact, so a
    # crash mid-produce can never leave the record claiming in_production/verified
    # while script.md is being rewritten/unverified. Also CLEAR the artifact paths:
    # during the 'producing' window (and if interrupted) the record must not
    # advertise publishable artifacts that no longer match the regenerated script.
    # A new script also invalidates the old render, so video_path is cleared until
    # re-render. All are re-committed at the very end (commit-last) on success.
    if not metadata_only:
        q.update_idea(idea_id, status="producing", fact_passed=False,
                      script_path=None, metadata_path=None,
                      factcheck_path=None, video_path=None)
        print(f"  {GRAY}writing script…{RESET}")
        script = generate_script(idea)

    # Keep script.md in sync with `script` (the content we verify + feed to metadata
    # + record). Always (over)write so a re-run can't leave a STALE on-disk script.
    # Skip only when `script` was just read FROM the file (avoids double header).
    if script and not script_from_file:
        _atomic_write(script_file, f"# {title}\n\n{script}\n")
    if not metadata_only:
        print(f"  {GREEN}✓ script.md ({len(script.split())} words){RESET}")

    # ── Fact-gate (auto-chained) ─────────────────────────────────────────────
    # Verify the script before it feeds metadata. Auto-correct once, re-verify.
    fact_result = None
    if not metadata_only and factcheck_enabled:
        from engine.pipeline import factcheck as fc
        print(f"  {GRAY}fact-checking script…{RESET}")
        fact_result = fc.factcheck(script, max_claims=max_claims)
        if autofix and fact_result["issues"]:
            print(f"  {GRAY}auto-correcting {len(fact_result['issues'])} claim(s) + re-verifying…{RESET}")
            script = fc.correct_script(script, fact_result["issues"])
            _atomic_write(script_file, f"# {title}\n\n{script}\n")
            fact_result = fc.factcheck(script, max_claims=max_claims)
        _atomic_write(os.path.join(out_dir, "factcheck.json"),
                      json.dumps(fact_result, indent=2, ensure_ascii=False))
        if fact_result["passed"]:
            print(f"  {GREEN}✓ fact-gate passed ({fact_result['checked']} claims){RESET}")
        else:
            why = (f"{len(fact_result['issues'])} unresolved"
                   + ("" if fact_result["complete"] else ", coverage incomplete"))
            print(f"  {RED}✗ fact-gate NOT passed ({why}) → needs_review{RESET}")

    print(f"  {GRAY}optimising metadata…{RESET}")
    meta = generate_metadata(idea, script)
    metadata_file = os.path.join(out_dir, "metadata.json")
    _atomic_write(metadata_file, json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"  {GREEN}✓ metadata.json — title: {meta.get('title','?')}{RESET}")

    # Status is gated on the fact-check: production-ready only if verified.
    passed = fact_result is None or fact_result["passed"]
    fields = {"status": "in_production" if passed else "needs_review",
              "metadata_path": os.path.relpath(metadata_file, _ROOT)}
    if os.path.exists(script_file):
        fields["script_path"] = os.path.relpath(script_file, _ROOT)
    if fact_result is not None:
        fields["fact_passed"] = fact_result["passed"]
        fields["factcheck_path"] = os.path.relpath(os.path.join(out_dir, "factcheck.json"), _ROOT)
    q.update_idea(idea_id, **fields)
    return {"metadata": meta, "fact_passed": passed}


def main() -> None:
    ap = argparse.ArgumentParser(description="The Untold Game — produce scripts + metadata")
    ap.add_argument("--id", help="produce a single idea by id (any status)")
    ap.add_argument("--top", type=int, help="produce the top-N PENDING ideas (dev/testing)")
    ap.add_argument("--metadata-only", action="store_true", help="skip script generation (cheap test)")
    ap.add_argument("--no-factcheck", action="store_true", help="skip the fact-gate (not recommended)")
    ap.add_argument("--no-autofix", action="store_true", help="fact-check but don't auto-correct")
    ap.add_argument("--max-claims", type=int, default=25)
    args = ap.parse_args()

    ideas = _select(args)
    if not ideas:
        print(f"{GOLD}No ideas to produce. Approve ideas first "
              f"(`python3 -m engine.run_pipeline --review`) or pass --id / --top.{RESET}")
        return

    print(f"{GOLD}Producing {len(ideas)} idea(s) → {os.path.relpath(PRODUCED_DIR, _ROOT)}/{RESET}")
    done, needs_review, failed = 0, 0, 0
    for idea in ideas:
        try:
            r = produce(idea, metadata_only=args.metadata_only,
                        factcheck_enabled=not args.no_factcheck,
                        autofix=not args.no_autofix, max_claims=args.max_claims)
            done += 1
            if not r["fact_passed"]:
                needs_review += 1
        except Exception as e:  # one failure must not abort the batch
            failed += 1
            print(f"  {RED}✗ [{idea['id']}] failed: {e}{RESET}")
    tail = f", {needs_review} need review (fact-gate)" if needs_review else ""
    print(f"\n{GOLD}Done — {done} produced{tail}, {failed} failed.{RESET}")


if __name__ == "__main__":
    main()
