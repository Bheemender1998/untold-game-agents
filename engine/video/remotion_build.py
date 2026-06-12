"""
Turn a produced idea + narration + word timings into Remotion input props.

This is the bridge between our Python pipeline and the Remotion composition
(engine/video/remotion/). It reuses the SAME building blocks as the HyperFrames path —
chapter distillation (compose.build_section_headlines / assign_headline_times), atmospheric
Pexels footage (footage.fetch_clips), and whisper word timings (captions) — but emits a
props.json the React composition consumes instead of HyperFrames HTML.
"""
from __future__ import annotations
import os

from engine.video import captions as _captions
from engine.video import compose as _compose
from engine.video import footage as _footage
from engine.video import music as _music
from engine.video import tts as _tts

INTRO_MS = 4000
OUTRO_MS = 3500


def build_props(idea: dict, script_md: str, video_dir: str, audio_filename: str,
                words: list[dict] | None, total_dur: float, fps: int = 30,
                width: int = 1920, height: int = 1080,
                portrait: bool = False,
                intro_ms: int = INTRO_MS, outro_ms: int = OUTRO_MS) -> tuple[dict, list[str]]:
    """Build (props, asset_paths) for the Remotion render.

    props        → written to props.json and passed to `remotion render --props`.
    asset_paths  → files (narration + b-roll clips) to stage into remotion/public/.
    """
    narration = _tts.script_to_narration_text(script_md)

    # Word-level captions: real whisper timings, else a length-weighted estimate.
    if words:
        cap_words = [{"text": w["word"], "startMs": int(round(w["start"] * 1000)),
                      "endMs": int(round(w["end"] * 1000))} for w in words]
    else:
        cap_words = _captions.estimate_word_timings(narration, total_dur)

    # Chapters (headline + anchor + symbolic visual query), timed to the audio.
    sections = _compose.build_section_headlines(idea, script_md)
    heads = _compose.assign_headline_times(sections, words, total_dur, narration)

    # One atmospheric Pexels clip per chapter (symbolic only). Missing → gradient fallback.
    clips = _footage.fetch_clips([s.get("visual", "") for s in sections], video_dir,
                                 portrait=portrait)

    chapters, assets = [], []
    for h, clip in zip(heads, clips):
        ch = {"headline": h["headline"],
              "startMs": int(round(h["start"] * 1000)),
              "endMs": int(round(h["end"] * 1000))}
        if clip:
            ch["bClip"] = os.path.basename(clip)
            try:
                ch["bClipMs"] = int(_captions.audio_duration(clip) * 1000)  # ffprobe works on video too
            except Exception:
                ch["bClipMs"] = None
            assets.append(clip)
        chapters.append(ch)

    props = {
        "title": idea["title_variants"][0],
        "kicker": "THE UNTOLD GAME",
        "audioSrc": os.path.basename(audio_filename),
        "fps": fps,
        "width": width,
        "height": height,
        "introMs": intro_ms,
        "outroMs": outro_ms,
        "narrationMs": int(round(total_dur * 1000)),
        "captions": cap_words,
        "chapters": chapters,
    }

    # Shorts only: a mood-matched background bed mixed low under the narration.
    music_credit = ""
    if portrait:
        frag, music_asset, music_credit = _music.short_music_props(idea)
        if music_asset:
            props.update(frag)
            assets.append(music_asset)

    return props, assets, music_credit
