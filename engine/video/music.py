"""
Mood-matched background music for Shorts.

Selection is deterministic (seeded by idea id) over a per-mood folder of cleared
royalty-free tracks. A generated manifest.json carries each track's license
attribution. Selection, prop-injection, and credit-surfacing are separate so each
can be tested in isolation. Pure Python — no Remotion/Node dependency.
"""
from __future__ import annotations
import glob
import hashlib
import json
import os

MUSIC_DIR = os.path.join(os.path.dirname(__file__), "music")
MANIFEST = os.path.join(MUSIC_DIR, "manifest.json")
ATTRIBUTION = os.path.join(MUSIC_DIR, "attribution.json")
MOODS = ("tense", "triumphant", "somber", "hype")
MUSIC_VOLUME = 0.12
_EXTS = (".mp3", ".wav")


def _load_attribution(music_dir: str) -> dict:
    path = os.path.join(music_dir, "attribution.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def build_manifest(music_dir: str | None = None) -> dict:
    """Scan music_dir/<mood>/ for audio, write <music_dir>/manifest.json, return it.

    Shape: {mood: [{"file": "<mood>/<name>", "attribution": "<str>"}]}. Only the four
    canonical MOODS are scanned; _unused/ and stray files are ignored. Idempotent.
    """
    music_dir = music_dir or MUSIC_DIR
    attribution = _load_attribution(music_dir)
    manifest: dict[str, list[dict]] = {}
    for mood in MOODS:
        tracks = []
        for path in sorted(glob.glob(os.path.join(music_dir, mood, "*"))):
            if os.path.splitext(path)[1].lower() not in _EXTS:
                continue
            name = os.path.basename(path)
            tracks.append({"file": f"{mood}/{name}",
                           "attribution": attribution.get(name, "")})
        manifest[mood] = tracks
    with open(os.path.join(music_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def _read_manifest(music_dir: str) -> dict:
    path = os.path.join(music_dir, "manifest.json")
    if not os.path.exists(path):
        return build_manifest(music_dir)
    with open(path) as f:
        return json.load(f)


def pick_track(mood: str, seed: str, music_dir: str | None = None) -> dict | None:
    """Deterministically choose a track for `mood`, seeded by `seed` (the idea id).

    Returns {"path": <abs path>, "attribution": <str>} or None when the mood is
    unknown/empty. Same seed → same track; different seeds rotate over the folder.
    """
    music_dir = music_dir or MUSIC_DIR
    if mood not in MOODS:
        return None
    tracks = _read_manifest(music_dir).get(mood, [])
    if not tracks:
        return None
    idx = int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(tracks)
    chosen = tracks[idx]
    return {"path": os.path.join(music_dir, chosen["file"]),
            "attribution": chosen.get("attribution", "")}


def short_music_props(idea: dict, music_dir: str | None = None) -> tuple[dict, str | None, str]:
    """For a Short: pick a bed for the idea's mood.

    Returns (props_fragment, asset_path, credit). On a miss: ({}, None, "") so the
    caller renders silent (self-stub). props_fragment merges into the Remotion props.
    """
    music_dir = music_dir or MUSIC_DIR
    from engine.video import tts
    mood = idea.get("mood") or tts.mood_for_pillar(idea.get("pillar"))
    chosen = pick_track(mood, idea.get("id", ""), music_dir)
    if not chosen:
        return {}, None, ""
    from engine import config
    credit = chosen["attribution"] or config.MUSIC_CREDIT_DEFAULT
    frag = {"musicSrc": os.path.basename(chosen["path"]), "musicVolume": MUSIC_VOLUME}
    return frag, chosen["path"], credit


def write_credit(video_dir: str, metadata_path: str, credit: str) -> None:
    """Surface a non-empty attribution: sidecar file + one-time append to the
    metadata.json description. No-op when credit is empty. Idempotent."""
    if not credit:
        return
    with open(os.path.join(video_dir, "music_credit.txt"), "w") as f:
        f.write(credit)
    if not os.path.exists(metadata_path):
        return
    with open(metadata_path) as f:
        meta = json.load(f)
    line = f"Music: {credit}"
    desc = meta.get("description", "")
    if line not in desc:
        meta["description"] = (desc + "\n\n" + line).strip()
        with open(metadata_path, "w") as f:
            json.dump(meta, f, indent=2)
