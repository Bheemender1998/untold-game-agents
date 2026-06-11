# ADR 0004 — Open-source video-production stack

**Status:** Accepted (2026-06-11). Scaffolded; render spike pending authorization.

## Context
We can produce script + metadata. Turning those into a finished video was the open
gap. Evaluated 10 open repos to fill it (script → video) on a free/local-first basis.

## Decision — adopted stack
| Stage | Tool | License | Notes |
|------|------|---------|-------|
| Render / assembly (keystone) | **HyperFrames** | Apache-2.0 | HTML→MP4, agent-driven, deterministic. Node 22+ & ffmpeg (present). |
| Captions + timing sync | **Whisper** (whisper.cpp / faster-whisper, `small`) | MIT | Word timestamps drive caption + visual sync. |
| AI imagery | **Fooocus** *or* cloud gen *or* CC stock | GPL-3 / — | See constraint below. |
| Research depth | **ScrapeGraphAI** (+ Ollama local models) | MIT | Optional upgrade to script fact-gathering. |
| Utility LLM (cost) | **Qwen3** (small, via Ollama) | Apache-2.0 | Offload metadata/research from paid Anthropic; keep Sonnet for scripts. |
| Cleared b-roll / research | **yt-dlp** | Unlicense | PD/CC/own footage ONLY — see guardrail. |
| Metadata/growth knowledge | **marketingskills** | — | Feed title/description/thumbnail prompts. Reference, not engine. |

**Not adopted:** AppFlowy (our queue+dashboard already cover content-ops; AGPL, heavy),
design-motion-principles (web-UI animation, not video), spec-kit (dev-process meta-tool,
optional).

## Two gaps the repo list does NOT close
1. **TTS.** None of the 10 do text-to-speech (Whisper is the inverse). Pick a free local
   TTS that runs on M2/8GB — **Piper** or **Kokoro-82M** — or a paid cloud voice.
2. **Footage rights.** No tool grants permission. yt-dlp is gated to PD/CC/own sources.

## Hardware constraint (decisive)
Dev machine = Apple **M2, 8GB RAM**. Render (HyperFrames + headless Chrome + ffmpeg),
Whisper (`small`), and a *small* Qwen3 run — but **not all at once**, and **local SDXL
(Fooocus) is not viable** (~12-16GB needed; 8GB unified would swap-thrash). Therefore on
this box: **imagery comes from cloud gen or CC stock, not local Fooocus.** Fooocus stays
in the design for a larger machine.

## Consequences
- A fully-automated faceless pipeline is viable: script→TTS→Whisper→images→HyperFrames HTML→MP4.
- Scaffolded under `engine/video/`. The keystone render spike needs explicit authorization
  to execute the `hyperframes` npm package (downloads + runs third-party code + Chrome).
- Most of the stack is free; the only likely paid pieces are a TTS voice (optional) and
  cloud image gen (optional if using CC stock).
