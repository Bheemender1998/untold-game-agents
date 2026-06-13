"""
The Untold Game — VIDEO stage entrypoint.

Builds a HyperFrames composition (index.html) from a produced idea's script, then
optionally renders it to MP4. One spine, two modes:

  --mode text      kinetic typography, NO audio. Runs on this M2/8GB with only
                   HyperFrames — no TTS, no Fooocus. The shippable-today path.
  --mode narrated  hybrid layout (section headline + verbatim synced caption) over a
                   narration track. TTS is auto-detected: Kokoro if installed, else the
                   macOS `say` voice (zero install). Captions sync to faster-whisper word
                   timings when present, else a reading-time estimate. No --audio needed —
                   narration is generated from the script. Pass --audio to reuse a file.

Usage:
  python3 -m engine.run_video --id <id>                      # text mode, compose only
  python3 -m engine.run_video --id <id> --render             # also render to MP4
  python3 -m engine.run_video --id <id> --mode narrated --render   # generate voice + render
  python3 -m engine.run_video --id <id> --mode narrated --tts say --voice Daniel --render

Headless-safe (no prompts).
"""
from __future__ import annotations
import argparse
import json
import os
import shutil

from engine import config
from engine import queue_manager as q
from engine import paths
from engine.video import captions, compose, tts

GOLD, GREEN, RED, GRAY, RESET = "\033[93m", "\033[92m", "\033[91m", "\033[90m", "\033[0m"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    ap = argparse.ArgumentParser(description="The Untold Game — build a video composition")
    ap.add_argument("--id", required=True, help="produced idea id (has produced/<id>/<fmt>/script.md)")
    ap.add_argument("--mode", choices=["text", "narrated"], default="text")
    ap.add_argument("--audio", help="reuse an existing narration file (narrated mode); "
                    "default is to generate it from the script")
    ap.add_argument("--tts", choices=["kokoro", "say"], help="TTS provider override (default: auto)")
    ap.add_argument("--voice", help="voice name (kokoro: e.g. af_sarah; say: e.g. Daniel)")
    ap.add_argument("--engine", choices=["remotion", "hyperframes"], default="remotion",
                    help="narrated render engine: remotion (designed b-roll + kinetic captions, "
                    "default) or hyperframes (legacy text-on-gradient)")
    ap.add_argument("--render", action="store_true",
                    help="also render to MP4 (Remotion or HyperFrames per --engine)")
    ap.add_argument("--format", choices=["long", "short"], default="long",
                    help="output format: long (1920×1080 landscape, default) or "
                    "short (1080×1920 vertical)")
    args = ap.parse_args()

    idea = q.get_by_id(args.id)
    if not idea:
        print(f"{RED}No idea {args.id} in the queue.{RESET}"); return

    script_file = paths.script_path(args.id, args.format)
    if not os.path.exists(script_file):
        print(f"{RED}No script at {os.path.relpath(script_file, _ROOT)}. "
              f"Run `python3 -m engine.run_produce --id {args.id}` first.{RESET}"); return
    with open(script_file) as f:
        script_md = f.read()

    video_dir = paths.video_dir(args.id, args.format)
    os.makedirs(video_dir, exist_ok=True)

    # ── Narrated mode: produce (or reuse) narration audio, then time the captions ──
    audio_ref, words, total_dur = None, None, None
    if args.mode == "narrated":
        audio_path = os.path.join(video_dir, "narration.wav")
        if args.audio:
            if not os.path.exists(args.audio):
                print(f"{RED}--audio {args.audio} not found.{RESET}"); return
            audio_ref = os.path.basename(args.audio)
            audio_path = os.path.join(video_dir, audio_ref)
            shutil.copy(args.audio, audio_path)
            print(f"{GRAY}Reusing narration {audio_ref}{RESET}")
        else:
            provider = args.tts or tts.available_provider()
            if not provider:
                print(f"{RED}No TTS provider. `pip install kokoro-onnx` or run on macOS "
                      f"(say + ffmpeg).{RESET}"); return
            narration_text = tts.apply_pronunciation(tts.script_to_narration_text(script_md))
            print(f"{GOLD}▶ Narrating [{args.id}] via {provider}…{RESET}")
            try:
                voice = tts.narration_voice(idea, override=args.voice, provider=provider)
                speed, gap_s = tts.narration_pace(args.format)
                tts.synthesize(narration_text, audio_path, provider=args.tts, voice=voice,
                               speed=speed, gap_s=gap_s)
            except Exception as e:
                print(f"{RED}TTS failed: {e}{RESET}"); return
            audio_ref = "narration.wav"

        total_dur = captions.audio_duration(audio_path)
        glossary = captions.proper_nouns(tts.script_to_narration_text(script_md))
        tx = captions.transcribe(audio_path, initial_prompt=glossary)   # {words, segments} | None
        words = tx["words"] if tx else None           # downstream wants the word list (raw — kept for anchor matching)
        synced = "word-synced (whisper)" if words else "estimated timing (no faster-whisper)"
        print(f"{GREEN}✓ narration {total_dur:.0f}s — captions: {synced}{RESET}")

    # ── Remotion path (narrated): designed b-roll + kinetic captions ──
    if args.mode == "narrated" and args.engine == "remotion":
        from engine.video import remotion_build, render_remotion
        is_short = args.format == "short"
        print(f"{GOLD}▶ Building Remotion props [{args.id}] — {idea['title_variants'][0]}{RESET}")
        props, assets, music_credit = remotion_build.build_props(
            idea, script_md, video_dir, audio_ref, words, total_dur,
            width=(1080 if is_short else 1920),
            height=(1920 if is_short else 1080),
            portrait=is_short,
            intro_ms=(0 if is_short else remotion_build.INTRO_MS),
            outro_ms=(2500 if is_short else remotion_build.OUTRO_MS),
            broll_beat_s=(config.SHORT_BROLL_BEAT_S if is_short else config.LONG_BROLL_BEAT_S),
        )
        with open(os.path.join(video_dir, "props.json"), "w") as f:
            json.dump(props, f, indent=2)
        srt_chunks = (captions.chunk_words_to_captions(captions.digitize_number_words(words)) if words
                      else captions.estimate_caption_timings(
                          tts.script_to_narration_text(script_md), total_dur))
        captions.to_srt(srt_chunks, os.path.join(video_dir, "captions.srt"))
        n_bg = sum(1 for c in props["chapters"] if c.get("bClip"))
        print(f"{GREEN}✓ {len(props['chapters'])} chapters · {len(props['captions'])} caption words · "
              f"{n_bg}/{len(props['chapters'])} b-roll clips → "
              f"{os.path.relpath(os.path.join(video_dir, 'props.json'), _ROOT)}{RESET}")
        for ch in props["chapters"][:4]:
            print(f"{GRAY}   · {ch['headline']}{RESET}")
        if n_bg == 0:
            print(f"{GRAY}   (no b-roll — set PEXELS_API_KEY for atmospheric clips; "
                  f"gradient fallback used){RESET}")
        if not args.render:
            print(f"{GRAY}Props ready. Add --render to render via Remotion.{RESET}")
            return
        mp4_dest = os.path.join(video_dir, "video.mp4")
        print(f"{GOLD}▶ Rendering (Remotion)…{RESET}")
        try:
            mp4 = render_remotion.render(props, os.path.join(video_dir, audio_ref), assets, mp4_dest,
                                         composition_id=("UntoldShort" if is_short else "UntoldVideo"))
        except Exception as e:
            print(f"{RED}render failed: {e}{RESET}")
            print(f"{GRAY}One-time setup: cd engine/video/remotion && npm install{RESET}")
            return
        meta_path = os.path.join(os.path.dirname(os.path.abspath(video_dir)), "metadata.json")
        from engine.video import music as _music
        _music.write_credit(video_dir, meta_path, music_credit)
        _vp_field = "short_video_path" if args.format == "short" else "video_path"
        q.update_idea(args.id, **{_vp_field: os.path.relpath(mp4, _ROOT)})
        print(f"{GREEN}✓ {os.path.relpath(mp4, _ROOT)}{RESET}")
        return

    # ── HyperFrames path (text mode, or narrated --engine hyperframes) ──
    print(f"{GOLD}▶ Composing [{args.id}] mode={args.mode} — {idea['title_variants'][0]}{RESET}")
    out_html = os.path.join(video_dir, "index.html")
    result = compose.build(idea, script_md, out_html, mode=args.mode,
                           audio_path=audio_ref, words=words, total_dur=total_dur)
    print(f"{GREEN}✓ {len(result['beats'])} beats, ~{result['duration']}s → "
          f"{os.path.relpath(out_html, _ROOT)}{RESET}")
    for b in result["beats"][:4]:
        kick = f"[{b['kicker']}] " if b.get("kicker") else ""
        print(f"{GRAY}   · {kick}{b['text']}{RESET}")

    # Write an .srt next to the composition (narrated mode) for review / upload captions.
    if args.mode == "narrated" and result.get("captions"):
        srt = captions.to_srt(result["captions"], os.path.join(video_dir, "captions.srt"))
        print(f"{GRAY}   captions → {os.path.relpath(srt, _ROOT)}{RESET}")

    rel_html = os.path.relpath(out_html, _ROOT)
    if not args.render:
        print(f"{GRAY}Composition: {rel_html}  —  add --render to render the MP4.{RESET}")
        return

    from engine.video import render
    mp4_dest = os.path.join(video_dir, "video.mp4")
    print(f"{GOLD}▶ Rendering (HyperFrames)…{RESET}")
    try:
        mp4 = render.render(video_dir, copy_to=mp4_dest)
    except Exception as e:
        print(f"{RED}render failed: {e}{RESET}")
        print(f"{GRAY}One-time renderer setup: cd engine/video/renderer && "
              f"npm install && npx hyperframes init .{RESET}")
        return
    _vp_field = "short_video_path" if args.format == "short" else "video_path"
    q.update_idea(args.id, **{_vp_field: os.path.relpath(mp4, _ROOT)})
    print(f"{GREEN}✓ {os.path.relpath(mp4, _ROOT)}{RESET}")


if __name__ == "__main__":
    main()
