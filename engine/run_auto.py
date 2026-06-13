"""Stage B orchestrator: unattended produce → render → QC → awaiting_approval, plus the
human approval CLI. Runs in the user's shell (render needs npx). Shells out per stage with
the right interpreter (the produce/render venvs can't coexist in one process)."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
from collections import Counter

from engine import config
from engine import queue_manager as q
from engine import paths
from engine.pipeline import qc
from engine.publish import uploader, auth

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENV_PY = os.path.join(_ROOT, ".venv-video", "bin", "python")
_OVERNIGHT_FMT = "long"  # overnight pipeline is long-form only (Phase 2 adds companion shorts)


def _run(cmd: list[str], timeout: float | None = None) -> int:
    """Run a subprocess in its own process group; return exit code.
    On timeout, kill the whole group and return a sentinel 124 (like coreutils timeout)."""
    proc = subprocess.Popen(cmd, cwd=_ROOT, start_new_session=True)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            # POSIX only (os.killpg/getpgid not available on Windows)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass  # process already exited in the race window
        proc.wait()
        return 124


def _select(count: int) -> list[dict]:
    return q.get_pending()[:count]


def _produce_one(idea_id: str) -> str:
    """Run produce as a subprocess; return the idea's resulting status."""
    rc = _run([sys.executable, "-m", "engine.run_produce", "--id", idea_id,
               "--format", _OVERNIGHT_FMT],
              timeout=config.PRODUCE_TIMEOUT_S)
    if rc != 0:
        print(f"· {idea_id}: produce {'timed out' if rc == 124 else f'exit {rc}'} "
              f"(idea may be left in 'producing')")
    idea = q.get_by_id(idea_id) or {}
    return idea.get("status", "unknown")


def _render_one(idea_id: str) -> bool:
    """Render via the video venv under a hard timeout. On nonzero/timeout → render_failed."""
    rc = _run([_VENV_PY, "-m", "engine.run_video", "--id", idea_id,
               "--render", "--mode", "narrated", "--format", _OVERNIGHT_FMT],
              timeout=config.RENDER_TIMEOUT_S)
    if rc != 0:
        why = "render timed out" if rc == 124 else f"render exit {rc}"
        q.update_idea(idea_id, status="render_failed", render_note=why)
        return False
    return True


def _cleared_to_render(idea: dict) -> bool:
    return idea.get("status") == "in_production" or idea.get("human_reviewed") is True


def _render_and_qc(idea_id: str) -> None:
    """Render a cleared idea, QC it, and set awaiting_approval / qc_failed / render_failed."""
    if not _render_one(idea_id):
        print(f"· {idea_id}: render_failed")
        return
    report = qc.qc_video(idea_id, _OVERNIGHT_FMT)
    status = "awaiting_approval" if report["passed"] else "qc_failed"
    q.update_idea(idea_id, status=status)
    print(f"· {idea_id}: {status}")


def pipeline(count: int, no_render: bool) -> Counter:
    """Produce → (render → QC) for the top-`count` pending ideas. One failure never
    aborts the batch. Returns a Counter of each idea's final status."""
    results: Counter = Counter()
    for idea in _select(count):
        idea_id = idea["id"]
        try:
            _produce_one(idea_id)
            current = q.get_by_id(idea_id) or {}
            if not _cleared_to_render(current):
                print(f"· {idea_id}: not cleared ({current.get('status')}) — skipping")
                continue
            if no_render:
                print(f"· {idea_id}: cleared (--no-render, stopping before render)")
                continue
            _render_and_qc(idea_id)
        except Exception as e:  # never abort the batch
            print(f"! {idea_id}: error {e}")
        finally:
            results[(q.get_by_id(idea_id) or {}).get("status", "unknown")] += 1
    return results


def _summary_message(counter: Counter) -> str:
    """Human one-liner for the overnight notification."""
    if not counter:
        return "No ideas produced."
    total = sum(counter.values())
    parts = ", ".join(f"{n} {status}" for status, n in counter.most_common())
    return f"{total} produced: {parts}"


def _notify(message: str, title: str = "The Untold Game — overnight") -> None:
    """Best-effort macOS Notification Center banner. Never raises (notification
    failure must not fail an otherwise-good overnight run)."""
    try:
        subprocess.run(
            ["osascript", "-e",
             f"display notification {json.dumps(message)} with title {json.dumps(title)}"],
            check=False,
        )
    except Exception:
        pass


def _load_metadata(rel_path: str) -> dict:
    with open(os.path.join(_ROOT, rel_path)) as f:
        return json.load(f)


def _qc_summary(idea_id: str) -> str:
    path = paths.qc_path(idea_id, _OVERNIGHT_FMT)
    try:
        with open(path) as f:
            r = json.load(f)
    except (OSError, ValueError):
        return "no qc.json"
    if r.get("passed"):
        return "QC pass"
    failed = [c["name"] for c in r.get("checks", []) if not c.get("passed")]
    return "QC FAIL: " + ", ".join(failed)


def cmd_list() -> None:
    rows = q.get_by_status("awaiting_approval")
    if not rows:
        print("No videos awaiting approval.")
        return
    for i in rows:
        title = (i.get("title_variants") or ["?"])[0]
        print(f"{i['id']}  {title[:50]}  [{_qc_summary(i['id'])}]")


def cmd_review(idea_id: str, note: str = "") -> None:
    import datetime
    stamp = datetime.date.today().isoformat()
    note_line = f"{stamp}: {note}" if note else stamp
    q.update_idea(idea_id, human_reviewed=True, human_review_note=note_line)
    print(f"✓ {idea_id} marked human_reviewed")


def cmd_render(idea_id: str) -> None:
    """Render a single already-cleared idea (skips produce — preserves a hand-fixed script).
    This is the human-review override render path: --review <id>, then --render <id>."""
    idea = q.get_by_id(idea_id) or {}
    if not idea:
        sys.exit(f"No idea found for id {idea_id}")
    if not _cleared_to_render(idea):
        sys.exit(f"{idea_id} not cleared to render (status={idea.get('status')}, "
                 f"human_reviewed={idea.get('human_reviewed')}). Run --review {idea_id} first.")
    _render_and_qc(idea_id)


def cmd_reject(idea_id: str) -> None:
    q.update_idea(idea_id, status="rejected")
    print(f"✓ {idea_id} rejected")


def cmd_approve(idea_id: str, public: bool, dry_run: bool) -> None:
    idea = q.get_by_id(idea_id) or {}
    if not idea:
        sys.exit(f"No idea found for id {idea_id}")
    if idea.get("status") != "awaiting_approval":
        sys.exit(f"{idea_id} is '{idea.get('status')}', not awaiting_approval — refusing to publish")
    meta = _load_metadata(idea["metadata_path"])
    video = os.path.join(_ROOT, idea["video_path"])
    privacy = "public" if public else "unlisted"
    if dry_run:
        auth.get_credentials()  # exercise OAuth/token refresh — catches expiry
        if not (meta.get("title") and os.path.exists(video)):
            sys.exit(f"dry-run FAILED for {idea_id}: metadata/video invalid")
        print(f"✓ dry-run OK for {idea_id} (auth + metadata valid; not published)")
        return
    yt_id = uploader.upload(video_path=video, title=meta["title"],
                            description=meta.get("description", ""),
                            tags=meta.get("tags"), privacy=privacy)
    q.update_idea(idea_id, status="published",
                  long_youtube_url=f"https://youtu.be/{yt_id}")
    print(f"✓ published {idea_id} → https://youtu.be/{yt_id} ({privacy})")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="The Untold Game — Stage B orchestrator")
    ap.add_argument("--count", type=int, default=1, help="ideas to produce+render this run")
    ap.add_argument("--no-render", action="store_true", help="stop before render (dry test)")
    ap.add_argument("--list", action="store_true", help="list awaiting_approval videos")
    ap.add_argument("--review", metavar="ID", help="mark an idea human_reviewed")
    ap.add_argument("--note", default="", help="note for --review")
    ap.add_argument("--approve", metavar="ID", help="publish an awaiting_approval video")
    ap.add_argument("--public", action="store_true", help="--approve as public (default unlisted)")
    ap.add_argument("--dry-run", action="store_true", help="--approve: auth+metadata check, no insert")
    ap.add_argument("--reject", metavar="ID", help="mark an idea rejected")
    ap.add_argument("--render", metavar="ID", help="render a single cleared idea (skips produce)")
    args = ap.parse_args()

    if args.list:
        cmd_list()
    elif args.review:
        cmd_review(args.review, args.note)
    elif args.reject:
        cmd_reject(args.reject)
    elif args.approve:
        cmd_approve(args.approve, public=args.public, dry_run=args.dry_run)
    elif args.render:
        cmd_render(args.render)
    else:
        results = pipeline(count=args.count, no_render=args.no_render)
        if not args.no_render:
            _notify(_summary_message(results))


if __name__ == "__main__":
    main()
