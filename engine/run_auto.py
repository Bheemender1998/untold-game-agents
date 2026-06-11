"""Stage B orchestrator: unattended produce → render → QC → awaiting_approval, plus the
human approval CLI. Runs in the user's shell (render needs npx). Shells out per stage with
the right interpreter (the produce/render venvs can't coexist in one process)."""
from __future__ import annotations
import os
import signal
import subprocess
import sys

from engine import config
from engine import queue_manager as q

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENV_PY = os.path.join(_ROOT, ".venv-video", "bin", "python")


def _run(cmd: list[str], timeout: float | None = None) -> int:
    """Run a subprocess in its own process group; return exit code.
    On timeout, kill the whole group and return a sentinel 124 (like coreutils timeout)."""
    proc = subprocess.Popen(cmd, cwd=_ROOT, start_new_session=True)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
        return 124


def _select(count: int) -> list[dict]:
    return q.get_pending()[:count]


def _produce_one(idea_id: str) -> str:
    """Run produce as a subprocess; return the idea's resulting status."""
    _run([sys.executable, "-m", "engine.run_produce", "--id", idea_id])
    idea = q.get_by_id(idea_id) or {}
    return idea.get("status", "unknown")


def _render_one(idea_id: str) -> bool:
    """Render via the video venv under a hard timeout. On nonzero/timeout → render_failed."""
    rc = _run([_VENV_PY, "-m", "engine.run_video", "--id", idea_id,
               "--render", "--mode", "narrated"],
              timeout=config.RENDER_TIMEOUT_S)
    if rc != 0:
        why = "render timed out" if rc == 124 else f"render exit {rc}"
        q.update_idea(idea_id, status="render_failed", render_note=why)
        return False
    return True
