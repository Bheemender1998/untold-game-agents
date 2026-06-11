"""
Render the Remotion `UntoldVideo` composition to MP4.

Contract: Remotion renders from the project at engine/video/remotion/ — assets must live
in its public/ folder (referenced via staticFile) and props are passed as a JSON file.
So render(): stage narration + b-roll clips into public/, write props.json, run
`npx remotion render`, and return the output path. Runs in the caller's shell (the harness
sandbox can't exec npx, but the user can).
"""
from __future__ import annotations
import glob
import json
import os
import shutil
import subprocess

REMOTION_DIR = os.path.join(os.path.dirname(__file__), "remotion")
PUBLIC_DIR = os.path.join(REMOTION_DIR, "public")


def _stage_assets(audio_path: str, asset_paths: list[str]) -> None:
    """Refresh public/ with just this render's assets (clear stale clips first)."""
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    for stale in glob.glob(os.path.join(PUBLIC_DIR, "*.mp4")) + \
            glob.glob(os.path.join(PUBLIC_DIR, "*.wav")) + \
            glob.glob(os.path.join(PUBLIC_DIR, "*.mp3")):
        os.remove(stale)
    shutil.copy(audio_path, os.path.join(PUBLIC_DIR, os.path.basename(audio_path)))
    for a in asset_paths:
        shutil.copy(a, os.path.join(PUBLIC_DIR, os.path.basename(a)))


def render(props: dict, audio_path: str, asset_paths: list[str], out_mp4: str,
           concurrency: int = 2) -> str:
    """Render the composition with `props` to out_mp4. Returns out_mp4."""
    if not os.path.exists(os.path.join(REMOTION_DIR, "node_modules")):
        raise RuntimeError(
            "Remotion not installed. One-time setup:\n"
            f"  cd {REMOTION_DIR} && npm install"
        )
    _stage_assets(audio_path, asset_paths)
    props_path = os.path.join(REMOTION_DIR, "props.json")
    with open(props_path, "w") as f:
        json.dump(props, f, indent=2)

    out_abs = os.path.abspath(out_mp4)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    subprocess.run(
        ["npx", "remotion", "render", "src/index.ts", "UntoldVideo", out_abs,
         f"--props={props_path}", f"--concurrency={concurrency}", "--log=info"],
        cwd=REMOTION_DIR, check=True,
    )
    if not os.path.exists(out_abs):
        raise RuntimeError(f"Remotion render ran but no file at {out_abs}.")
    return out_mp4
