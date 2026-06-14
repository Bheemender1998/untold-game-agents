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

## Amendment (2026-06-14) — M5 Pro arrives; sub-project C (research depth) measured & deferred

The "decisive" M2/8GB hardware constraint above is **lifted**: the dev box is now an Apple
**M5 Pro, 24 GB**. The three set-aside local-stack pieces (Fooocus, Qwen3/Ollama,
ScrapeGraphAI) are independent sub-projects, each to be proven on its own merits before
adoption — not installed wholesale.

**ScrapeGraphAI / "research depth" (sub-project C) — evaluated with data, deferred.**
Brainstormed against the *actual* pipeline rather than the ADR's framing. Current research
and the fact-gate both rest on the same primitive — DuckDuckGo **snippets**
(`engine/ideate/web_search.py`); ScrapeGraphAI's value is turning a URL into extracted page
content. Targeted the **verification** path (the fact-gate has a concrete recurring human
cost; "thin scripts" has no demonstrated pain). Measured the 20 stored `produced/**/factcheck.json`
shadow runs (377 checked claims):

- Only **15 claims (4%)** are `web + unverified` — the sole bucket page-extraction could help.
  (`web + contradicted` = the gate *correctly* catching real script errors; better evidence
  wouldn't change those.)
- Reading all 15: ~5 are genuinely snippet-thin/retrieval misses, ~5 partial/contested, ~5 are
  real over-claims, source conflicts, flourishes, or **judge-reasoning** gaps (e.g. date
  arithmetic it already had the inputs for). Realistic recovery ≈ **1.5–2% of claims** — and the
  gate runs in **shadow** (`config.FACT_GATE_SHADOW`), so a human reviews all of them regardless.
- Encyclopedic (Wikipedia) `unverified` failures (13) are **as large as** web ones (15), so
  "better web extraction" isn't even the dominant lever.

**Decision:** do not build C now. The heavy framework (langchain + browser) plus its hidden
LLM-backend dependency (Ollama → pulls sub-project B forward, or Sonnet → recurring per-page
cost, against the cost-conscious stance) is unjustified by the data. If the fact-gate is worth
investment, the higher-leverage work the measurement surfaced is **graduating the gate out of
shadow** and **tightening the judge** (date arithmetic, wording tolerance, the blank-correction
retrieval misses) — neither needs the local stack or the M5. A future, much lighter option if
full-page evidence is ever wanted: a `trafilatura` fetch+extract into `gather_evidence` (no
ScrapeGraphAI, no Ollama).

Sub-projects **A (Fooocus)** and **B (Qwen3)** remain open and unmeasured; A is additionally
bounded by the integrity gate (ADR-0005) — local SDXL is viable only for atmospheric/abstract
visuals, never AI-generated portraits of real people.

*(Housekeeping: the production renderer is **Remotion**, not HyperFrames as tabled above — the
keystone choice changed during build. This amendment does not re-open that; noted so the table
isn't read as current.)*
