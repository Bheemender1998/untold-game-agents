"""
Video-production layer — turn produced/<id>/{script.md,metadata.json} into an MP4.

Adopted open-source stack (see docs/adr/0004-open-source-video-stack.md):
  tts.py      narration audio   ← Piper / Kokoro (local) or a cloud TTS
  captions.py word timestamps   ← Whisper (whisper.cpp, small model)
  visuals.py  imagery           ← Fooocus (local SDXL) OR cloud gen OR CC stock
  footage.py  cleared b-roll    ← yt-dlp (public-domain / CC / own only — NOT copyrighted footage)
  compose.py  timeline.html     ← Claude writes a HyperFrames HTML composition
  render.py   video.mp4         ← HyperFrames (HTML→MP4, deterministic) + ffmpeg

Hardware note: this dev machine is an M2/8GB. Render + captions are fine; local
SDXL (Fooocus) is not realistically viable here (needs ~12-16GB) — prefer cloud
image gen or licensed/CC stock. See the ADR.
"""
