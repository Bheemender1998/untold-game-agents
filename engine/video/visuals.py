"""
Imagery for the [VISUAL] cues.

On this M2/8GB box, local SDXL (Fooocus) is not viable (needs ~12-16GB; would
swap-thrash). Realistic sources, in order of preference here:
  1. Cloud image gen (cheap API) — best quality/effort on 8GB.
  2. Licensed / CC0 stock (Pexels/Wikimedia Commons) — free, real photos.
  3. Fooocus local — only if run on a bigger machine.

Each [VISUAL: ...] cue in the script becomes one image request.
"""
from __future__ import annotations


def cues_from_script(script_md: str) -> list[str]:
    """Extract the [VISUAL: ...] / [ARCHIVAL: ...] cue descriptions from the script."""
    import re
    return re.findall(r"\[(?:VISUAL|ARCHIVAL)[:：]\s*(.+?)\]", script_md)


def fetch_images(cues: list[str], out_dir: str, source: str = "stock") -> list[str]:
    """Produce one image file per cue into out_dir. source: 'stock'|'cloud'|'fooocus'.
    TODO: implement the chosen source. Returns image paths in cue order."""
    raise NotImplementedError(
        "Pick a source (cloud gen / CC stock / Fooocus) — see the ADR for the 8GB tradeoff."
    )
