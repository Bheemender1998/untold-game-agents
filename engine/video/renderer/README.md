# Renderer (HyperFrames)

HTML→MP4 render engine for the video pipeline. Apache-2.0, agent-driven, deterministic.

## Setup (run once, requires your OK to execute the npm package)
```bash
cd engine/video/renderer
npm install            # pulls hyperframes + headless Chrome on first render
npx hyperframes init . # scaffolds a composition (or hand-write index.html)
```

## Use
- `compose.py` generates `index.html` (timed clips, Ken Burns, captions, narration audio).
- `npm run render` → MP4 (deterministic).

Requires Node 22+ and ffmpeg — both already on this machine.
