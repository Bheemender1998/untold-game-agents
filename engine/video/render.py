"""
Render a HyperFrames composition to MP4.

Confirmed render contract (from a real run on this machine):
  - HyperFrames renders inside the initialized project dir `engine/video/renderer/`
    (one-time: `npm install && npx hyperframes init .`).
  - It reads `index.html` in that dir and writes `renders/renderer_<timestamp>.mp4`.

So render(): stage the target composition's index.html (+ any sibling assets like a
narration mp3) into the renderer project, run `npx hyperframes render`, and return
the newest MP4 from `renders/`. Runs in the caller's shell (the harness sandbox
can't execute npx, but the user can).
"""
from __future__ import annotations
import glob
import os
import shutil
import subprocess

RENDERER_DIR = os.path.join(os.path.dirname(__file__), "renderer")
RENDERS_DIR = os.path.join(RENDERER_DIR, "renders")


def render(composition_dir: str, copy_to: str | None = None) -> str:
    """Render composition_dir/index.html to MP4; return the output path.

    If copy_to is given, the MP4 is copied there (stable name) and that path is
    returned; otherwise the timestamped path under renders/ is returned.
    """
    index = os.path.join(composition_dir, "index.html")
    if not os.path.exists(index):
        raise FileNotFoundError(f"No composition at {index} — run `run_video` first.")
    if not os.path.exists(os.path.join(RENDERER_DIR, "package.json")):
        raise RuntimeError(
            "Renderer not initialized. One-time setup:\n"
            f"  cd {RENDERER_DIR} && npm install && npx hyperframes init ."
        )

    # Stage the composition + any sibling assets (narration mp3, images) into the
    # renderer project so relative src="..." references resolve.
    shutil.copy(index, os.path.join(RENDERER_DIR, "index.html"))
    for name in os.listdir(composition_dir):
        src = os.path.join(composition_dir, name)
        if name != "index.html" and os.path.isfile(src):
            shutil.copy(src, os.path.join(RENDERER_DIR, name))

    before = set(glob.glob(os.path.join(RENDERS_DIR, "*.mp4")))
    subprocess.run(["npx", "hyperframes", "render"], cwd=RENDERER_DIR, check=True)
    after = set(glob.glob(os.path.join(RENDERS_DIR, "*.mp4")))

    fresh = sorted(after - before, key=os.path.getmtime) or \
        sorted(after, key=os.path.getmtime)
    if not fresh:
        raise RuntimeError(f"Render ran but no MP4 found in {RENDERS_DIR}.")
    mp4 = fresh[-1]

    if copy_to:
        os.makedirs(os.path.dirname(copy_to), exist_ok=True)
        shutil.copy(mp4, copy_to)
        return copy_to
    return mp4
