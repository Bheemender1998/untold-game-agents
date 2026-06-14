"""
Turn a produced idea + narration + word timings into Remotion input props.

This is the bridge between our Python pipeline and the Remotion composition
(engine/video/remotion/). It reuses the SAME building blocks as the HyperFrames path —
chapter distillation (compose.build_section_headlines / assign_headline_times), atmospheric
Pexels footage (footage.fetch_clips), and whisper word timings (captions) — but emits a
props.json the React composition consumes instead of HyperFrames HTML.
"""
from __future__ import annotations
import math
import os

from engine import config as _config
from engine.video import captions as _captions
from engine.video import compose as _compose
from engine.video import footage as _footage
from engine.video import music as _music
from engine.video import tts as _tts

INTRO_MS = 4000
OUTRO_MS = 3500
LONG_BROLL_BEAT_S = _config.LONG_BROLL_BEAT_S


def beat_track(narration_ms: int, beat_s: float) -> list[dict]:
    """Split a narration of `narration_ms` into contiguous b-roll beats of ~`beat_s`
    seconds each. Returns [{"startMs", "endMs"}, ...]; the final beat is clamped to
    narration_ms. One clip will be fetched per beat (no single-clip loop)."""
    if narration_ms <= 0 or beat_s <= 0:
        return [{"startMs": 0, "endMs": max(0, narration_ms)}]
    beat_ms = max(1, int(round(beat_s * 1000)))   # guard: a tiny beat_s must not round to 0
    n = max(1, math.ceil(narration_ms / beat_ms))
    beats = []
    for i in range(n):
        start = i * beat_ms
        end = min((i + 1) * beat_ms, narration_ms)
        beats.append({"startMs": start, "endMs": end})
    return beats


def build_props(idea: dict, script_md: str, video_dir: str, audio_filename: str,
                words: list[dict] | None, total_dur: float, fps: int = 30,
                width: int = 1920, height: int = 1080,
                portrait: bool = False,
                intro_ms: int = INTRO_MS, outro_ms: int = OUTRO_MS,
                end_hold_ms: int = 0,
                broll_beat_s: float = LONG_BROLL_BEAT_S) -> tuple[dict, list[str], str]:
    """Build (props, asset_paths, music_credit) for the Remotion render.

    props        → written to props.json and passed to `remotion render --props`.
    asset_paths  → files (narration + b-roll clips) to stage into remotion/public/.
    music_credit → attribution string for the background bed ("" if none).
    """
    narration = _tts.script_to_narration_text(script_md)

    # Word-level captions: real whisper timings, else a length-weighted estimate.
    if words:
        cap_words = [{"text": w["word"], "startMs": int(round(w["start"] * 1000)),
                      "endMs": int(round(w["end"] * 1000))}
                     for w in _captions.digitize_number_words(words)]
    else:
        cap_words = _captions.estimate_word_timings(narration, total_dur)

    # Chapters (headline + anchor + symbolic visual query), timed to the audio.
    sections = _compose.build_section_headlines(idea, script_md)
    heads = _compose.assign_headline_times(sections, words, total_dur, narration)

    # Chapters are headline cards only now (long-form). B-roll is a separate beat track.
    chapters = [{"headline": h["headline"],
                 "startMs": int(round(h["start"] * 1000)),
                 "endMs": int(round(h["end"] * 1000))}
                for h in heads]

    # B-roll beat track: a NEW deduped atmospheric clip per beat (no single-clip loop).
    # Mood drives the pool (short: from the script's MOOD line, persisted on idea["mood"];
    # long: pillar-derived). Generic atmospheric → sport bias intentionally off.
    narration_ms = int(round(total_dur * 1000))
    beats = beat_track(narration_ms, broll_beat_s)
    mood = idea.get("mood") or _tts.mood_for_pillar(idea.get("pillar"))
    beat_queries = _footage.mood_beat_queries(mood, len(beats))
    beat_clips = _footage.fetch_clips(beat_queries, video_dir, portrait=portrait, sport=None)

    b_beats, assets = [], []
    for i, (beat, clip) in enumerate(zip(beats, beat_clips)):
        clip_ms = None
        if clip:
            try:
                clip_ms = int(_captions.audio_duration(clip) * 1000)  # ffprobe works on video too
            except Exception:
                clip_ms = None
        b_beats.append({
            "startMs": beat["startMs"],
            "endMs": beat["endMs"],
            "src": os.path.basename(clip) if clip else None,
            "zoomDir": "in" if i % 2 == 0 else "out",
            "clipMs": clip_ms,   # source media length → loop a short clip instead of freezing
        })
        if clip:
            assets.append(clip)

    # End breath: stretch the last b-roll beat THAT HAS A CLIP to cover the hold, so real story
    # footage (not the gradient) carries the pause before the subscribe card. A clip shorter than
    # the window is looped by BeatClip. If no beat has a clip, the gradient carries it (graceful).
    # No-op when end_hold_ms=0 (long-form).
    if end_hold_ms and b_beats:
        hold_end = b_beats[-1]["endMs"] + end_hold_ms
        target = next((b for b in reversed(b_beats) if b.get("src")), None)
        if target is not None:
            target["endMs"] = hold_end

    props = {
        "title": idea["title_variants"][0],
        "kicker": "THE UNTOLD GAME",
        "audioSrc": os.path.basename(audio_filename),
        "fps": fps,
        "width": width,
        "height": height,
        "introMs": intro_ms,
        "outroMs": outro_ms,
        "endHoldMs": end_hold_ms,
        "narrationMs": narration_ms,
        "captions": cap_words,
        "chapters": chapters,
        "bBeats": b_beats,
    }

    # Mood-matched background bed mixed low under the narration (both formats).
    music_credit = ""
    frag, music_asset, music_credit = _music.short_music_props(idea)
    if music_asset:
        props.update(frag)
        assets.append(music_asset)

    return props, assets, music_credit
