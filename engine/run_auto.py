"""Stage B orchestrator: unattended produce → render → QC → awaiting_approval, plus the
human approval CLI. Runs in the user's shell (render needs npx). Shells out per stage with
the right interpreter (the produce/render venvs can't coexist in one process)."""
from __future__ import annotations
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import urllib.parse
from collections import Counter
from contextlib import contextmanager

from engine import config
from engine import queue_manager as q
from engine import paths
from engine.pipeline import qc
from engine.pipeline import subject, thumbnail
from engine.publish import uploader, auth

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENV_PY = os.path.join(_ROOT, ".venv-video", "bin", "python")
_OVERNIGHT_FMT = "long"  # overnight pipeline is long-form only (Phase 2 adds companion shorts)
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


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


def _ensure_thumbnail(idea_id: str, fmt: str) -> None:
    """Best-effort: ensure produced/<id>/<fmt>/thumbnail.jpg exists after a render.

    Skips if a thumbnail already exists (never clobbers hand-composited work).
    Self-stubs on any failure — a missing thumbnail must never break render/QC."""
    try:
        thumb = paths.thumbnail_path(idea_id, fmt)
        if os.path.exists(thumb):
            print(f"· {idea_id}/{fmt}: thumbnail exists — skipping auto-generation")
            return
        idea = q.get_by_id(idea_id) or {"id": idea_id}
        res = subject.source_subject(idea, fmt) or {}  # Wikipedia → Pexels; human subject wins
        if not res.get("source"):
            print(f"⚠ {idea_id}/{fmt}: no subject photo found — thumbnail skipped "
                  f"(hand-source before approving)")
            return
        thumbnail.generate_thumbnail(idea, fmt)
        print(f"✓ {idea_id}/{fmt}: thumbnail composited via {res['source']}")
    except Exception as e:                              # never break the render/batch
        print(f"⚠ {idea_id}/{fmt}: thumbnail auto-generation failed — {e}")


def _cleared_to_render(idea: dict) -> bool:
    return idea.get("status") == "in_production" or idea.get("human_reviewed") is True


def _render_and_qc(idea_id: str) -> None:
    """Render a cleared idea, QC it, and set awaiting_approval / qc_failed / render_failed."""
    if not _render_one(idea_id):
        print(f"· {idea_id}: render_failed")
        return
    _ensure_thumbnail(idea_id, _OVERNIGHT_FMT)   # auto-compose thumbnail on render
    # Sync the description's chapter timestamps from the rendered props.json (real per-chapter
    # times) — the produce-time LLM estimate is wrong; this is the authoritative correction.
    from engine.pipeline import chapters
    if chapters.sync_from_render(idea_id, _OVERNIGHT_FMT):
        print(f"· {idea_id}: chapter timestamps synced from render")
    report = qc.qc_video(idea_id, _OVERNIGHT_FMT)
    status = "awaiting_approval" if report["passed"] else "qc_failed"
    q.update_idea(idea_id, status=status)
    print(f"· {idea_id}: {status}")
    if status == "awaiting_approval":
        _companion_short(idea_id)   # 3 long + 3 short: each cleared long spawns its companion short


def _produce_companion(idea_id: str) -> dict:
    """Derive + write the companion short artifacts (in-process; no web fact-gate)."""
    from engine import run_produce
    idea = q.get_by_id(idea_id) or {}
    return run_produce.produce_companion_short(idea)


def _companion_short(idea_id: str) -> None:
    """Produce → render → QC the companion short for a long that's awaiting approval.
    Self-stubbing: any failure flags short_status and returns (never breaks the long)."""
    try:
        res = _produce_companion(idea_id)
        if not res.get("within_long", True):
            q.update_idea(idea_id, short_status="short_needs_review")
            print(f"· {idea_id}: companion short needs_review (containment guard)")
            return
        rc = _run([_VENV_PY, "-m", "engine.run_video", "--id", idea_id,
                   "--render", "--mode", "narrated", "--format", "short"],
                  timeout=config.RENDER_TIMEOUT_S)
        if rc != 0:
            q.update_idea(idea_id, short_status="short_render_failed",
                          short_render_note=("timed out" if rc == 124 else f"exit {rc}"))
            print(f"· {idea_id}: companion short render_failed")
            return
        report = qc.qc_video(idea_id, "short")
        if report["passed"]:
            _ensure_thumbnail(idea_id, "short")   # auto-compose short thumbnail
            q.update_idea(idea_id, short_status="short_awaiting_approval",
                          short_video_path=os.path.relpath(
                              os.path.join(paths.video_dir(idea_id, "short"), "video.mp4"), _ROOT))
            print(f"· {idea_id}: companion short short_awaiting_approval")
        else:
            q.update_idea(idea_id, short_status="short_qc_failed")
            print(f"· {idea_id}: companion short short_qc_failed")
    except Exception as e:                       # never break the long / batch
        q.update_idea(idea_id, short_status="short_failed", short_render_note=str(e))
        print(f"· {idea_id}: companion short failed — {e}")


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
        # Pass text as argv, never interpolated into the AppleScript source: osascript
        # rejects json.dumps's \uXXXX escapes (e.g. the title's em-dash) with
        # "-2741: unknown token", which silently dropped the completion banner.
        # "--" ends option parsing so a message/title starting with "-" is treated as
        # an operand, not an osascript flag (which would silently drop the banner too).
        subprocess.run(
            ["osascript",
             "-e", "on run argv",
             "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
             "-e", "end run",
             "--", message, title],
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


@contextmanager
def _approve_lock(idea_id: str):
    """Per-idea exclusive lock so two concurrent --approve runs can't both upload (the
    YouTube API has no idempotency key — two racing inserts create two videos, which is
    exactly how a triple-duplicate happened). Refuses (exits) if the lock is already held."""
    d = paths.artifact_dir(idea_id, _OVERNIGHT_FMT)
    os.makedirs(d, exist_ok=True)
    f = open(os.path.join(d, ".approve.lock"), "w")
    try:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit(f"{idea_id}: another --approve is already running — refusing (avoids a duplicate upload)")
        yield
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


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
    with _approve_lock(idea_id):
        # Re-check UNDER the lock: a concurrent run that beat us here may have just published.
        # Lock (blocks concurrency) + this re-check (catches the already-uploaded case) together
        # make a double-upload impossible.
        fresh = q.get_by_id(idea_id) or {}
        if fresh.get("long_youtube_url") or fresh.get("status") == "published":
            sys.exit(f"{idea_id}: already published ({fresh.get('long_youtube_url')}) — refusing duplicate upload")
        thumb = paths.thumbnail_path(idea_id, "long")
        if not os.path.exists(thumb):
            print(f"⚠ {idea_id}: no custom thumbnail — uploading with YouTube's default frame")
            thumb = None
        yt_id = uploader.upload(video_path=video, title=meta["title"],
                                description=meta.get("description", ""),
                                tags=meta.get("tags"), privacy=privacy,
                                thumbnail_path=thumb)
        q.update_idea(idea_id, status="published",
                      long_youtube_url=f"https://youtu.be/{yt_id}")
        print(f"✓ published {idea_id} → https://youtu.be/{yt_id} ({privacy})")
        long_url = f"https://youtu.be/{yt_id}"
        # Companion short (if produced + clean): upload with the long URL embedded in its
        # description (inherits the long's privacy). Inside the lock so it can't dup either.
        if idea.get("short_status") == "short_awaiting_approval" and idea.get("short_video_path"):
            try:
                smeta = _load_metadata(idea["short_metadata_path"])
                svideo = os.path.join(_ROOT, idea["short_video_path"])
                sdesc = f"{smeta.get('description', '')}\n\n▶ Full story on our channel: {long_url}".strip()
                sthumb = paths.thumbnail_path(idea_id, "short")
                if not os.path.exists(sthumb):
                    print(f"⚠ {idea_id}: companion short has no custom thumbnail — uploading with default frame")
                    sthumb = None
                short_id = uploader.upload(video_path=svideo, title=smeta["title"],
                                           description=sdesc, tags=smeta.get("tags"), privacy=privacy,
                                           thumbnail_path=sthumb)
                q.update_idea(idea_id, short_youtube_url=f"https://youtu.be/{short_id}")
                print(f"✓ companion short {idea_id} → https://youtu.be/{short_id} ({privacy})")
            except Exception as e:                  # short failure must not undo the long
                print(f"⚠ {idea_id}: long published but companion short upload failed — {e}")


def _video_id(url: str) -> str:
    """Extract the 11-char YouTube video id from a youtu.be/<id>, watch?v=<id>
    (any query-param order), /shorts/<id>, or /embed/<id> URL. Raises ValueError
    if no valid id can be parsed (so we never patch a wrong/garbage video)."""
    parsed = urllib.parse.urlparse(url.strip())
    candidate = None
    if parsed.query:
        candidate = (urllib.parse.parse_qs(parsed.query).get("v") or [None])[0]
    if candidate is None:
        candidate = parsed.path.rstrip("/").split("/")[-1]
    if not candidate or not _YT_ID_RE.match(candidate):
        raise ValueError(f"could not extract a valid YouTube video id from {url!r}")
    return candidate


def cmd_backlink(idea_id: str) -> None:
    """Append the idea's long URL to its already-published short's description."""
    idea = q.get_by_id(idea_id) or {}
    if not idea:
        sys.exit(f"No idea found for id {idea_id}")
    if idea.get("short_backlinked"):
        sys.exit(f"{idea_id}: already back-linked (short_backlinked=True)")
    long_url = idea.get("long_youtube_url")
    short_url = idea.get("short_youtube_url")
    if not (long_url and short_url):
        sys.exit(f"{idea_id}: need both long_youtube_url and short_youtube_url "
                 f"(long={long_url!r}, short={short_url!r})")
    suffix = f"▶ Full story on our channel: {long_url}"
    uploader.append_to_description(_video_id(short_url), suffix, skip_if_contains=long_url)
    q.update_idea(idea_id, short_backlinked=True)
    print(f"✓ {idea_id}: back-linked short {short_url} → {long_url}")


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
    ap.add_argument("--backlink", metavar="ID",
                    help="append the long's URL to its published short's description")
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
    elif args.backlink:
        cmd_backlink(args.backlink)
    elif args.render:
        cmd_render(args.render)
    else:
        results = pipeline(count=args.count, no_render=args.no_render)
        if not args.no_render:
            _notify(_summary_message(results))


if __name__ == "__main__":
    main()
