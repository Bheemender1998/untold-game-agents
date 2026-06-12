# Overnight render automation + standalone YouTube Shorts — design

**Date:** 2026-06-12
**Status:** Approved (brainstorm) → pending spec review → planning
**Author:** session 9

Two independent projects, brainstormed together because they ship in the same push.
They can be built and merged independently. **A is the headline** (wake up to ready
videos); **B is the new format** (Shorts). Build A first — it is smaller and reuses the
existing, tested orchestrator — then B.

---

## Project A — Overnight render automation

### Goal
By morning, last night's ideas are produced, rendered, QC'd, and sitting in
`awaiting_approval`. The user approves/publishes by hand. Nothing publishes unattended.

### Mechanism
A **launchd** agent on the M2 (render is local — Railway can't do the 45-min Chromium
render), firing a wrapper script on a schedule. No hook, no CI.

- **launchd plist:** `~/Library/LaunchAgents/com.untoldgame.overnight.plist`
  - `StartCalendarInterval` → **01:00 daily**.
  - `StandardOutPath` / `StandardErrorPath` → the dated log (below).
  - Note: if the Mac is asleep at 01:00, launchd fires on next wake, not at 01:00.
    Guaranteeing a wall-clock 01:00 run (`pmset schedule wake` / `caffeinate`) is a
    documented follow-up, not in this cut.
- **Wrapper:** `scripts/overnight.sh`
  1. `cd` repo root; export an explicit `PATH` (node/npx for Remotion, system python);
     `source .env` for the Anthropic key. *(launchd runs in a minimal env — an explicit
     PATH + sourced `.env` is the #1 thing that breaks unattended Mac jobs.)*
  2. **Ideate** — top up the queue (`python3 -m engine.run_pipeline`). Non-fatal on
     failure (13 ideas already pending as of this writing).
  3. **Produce + render + QC** — `python3 -m engine.run_auto --count 3`. Already does
     produce → render → QC → `awaiting_approval` per idea; one failure never aborts the
     batch. 3 × ~45-min renders ≈ done by ~04:00.
  4. **Report** — tee all output to `logs/overnight-YYYY-MM-DD.log`, then a **macOS
     notification** (`osascript -e 'display notification …'`) with the summary counts
     (e.g. "3 produced: 2 awaiting approval, 1 qc_failed").
  5. **No auto-publish.** Morning approval via `python3 -m engine.run_auto --approve`.

### Config / sizing (decided)
- **Count:** 3 videos/night. **Start:** 01:00. Worst case (3 renders capped at 90 min
  each by `RENDER_TIMEOUT_S`) ≈ 04:30 — still before wake.

### New code (small)
- `scripts/overnight.sh` — the wrapper (PATH/env setup, the 3 steps, log tee).
- Summary + notification logic — count `awaiting_approval` / `qc_failed` /
  `render_failed` after the batch and emit the `osascript` banner. Lives in the wrapper
  (or a tiny `engine.run_auto --summary` helper if cleaner; decide at plan time).
- `com.untoldgame.overnight.plist` — committed to the repo (e.g. under `deploy/launchd/`)
  with `launchctl load` install instructions; the live copy is symlinked/copied into
  `~/Library/LaunchAgents/`.

Everything downstream (`run_auto`, produce, render, QC) already exists and is tested.

### Risks handled
- Minimal launchd env → explicit PATH + sourced `.env`.
- Stuck render → already capped at 90 min (`RENDER_TIMEOUT_S`).
- Sleep at 01:00 → fires on wake; wall-clock guarantee is a noted follow-up.

---

## Project B — Standalone YouTube Shorts

### Goal
Native vertical Shorts (9:16, 30–50s), each its own purpose-written short script — hook +
one untold fact + payoff — with mood-matched royalty-free background music. Not derived
from long videos in this cut.

### Visual conventions (researched, mapped to our setup)
Grounded in current faceless-Shorts best practice (miraflow, virvid, opus hook formulas):

| Convention | Our setup today | Change for Shorts |
|---|---|---|
| 9:16, 1080×1920, fill screen | Remotion props-driven, defaults 1920×1080 | Pass vertical dims |
| 30–50s, high completion | Long multi-section scripts | **Short script mode** |
| Hook in first 0.5s, caption from frame 1, no title card | `introMs` title section | Drop intro card; hook caption from frame 1 |
| Big word-by-word captions, center third, key word emphasised | **Already ship per-word spring pop-in captions + SRT** | Larger font + vertical safe-zone position |
| Caption safe zone clear of top channel strip & bottom buttons | Horizontal layout puts captions low | New vertical safe band (~15–80% height) |
| Visual cut every 2–4s, B-roll | `footage.py` B-roll pipeline | 9:16 reframe (center-crop via object-fit cover) |
| Light mood-matched music | — | New music layer (below) |

We already own the two hardest pieces: **synced word-by-word captions** and the
**B-roll footage pipeline**.

### Idea source (decided)
Reuse the **same idea queue** — sports-history facts serve both formats. A format flag
selects long vs short. No parallel "shorts queue."

### 1. Short script — `run_produce --short`
New script-generation mode writing a **30–50s script (~90–130 words)**: one
scroll-stopping hook (first spoken line lands <0.5s), one untold fact built tight, one
payoff line. **Single section** — no multi-chapter structure. Emits a **`mood`** field
(`tense` / `triumphant` / `somber` / `hype`) for music selection.
**Fact-gate runs exactly as today** — same integrity gate, non-negotiable (ADR-0005).

### 2. Vertical render — `run_video --format short`
- Passes `width=1080, height=1920` to Remotion.
- **New `UntoldShort` composition** (`src/UntoldShort.tsx` + Root registration). Reuses
  `Background`, `Captions`, `Audio`; **drops the slow intro title card** (hook caption
  from frame 1) and **drops chapter cards** (single section); captions positioned in the
  **vertical safe band** at a larger font.
  - *Decision:* a separate composition keeps the long-form `UntoldVideo` untouched and
    each composition focused (rejected: overloading `UntoldVideo` with a layout branch).
- Footage: `Background` renders clips `object-fit: cover`, so 16:9 B-roll center-crops to
  fill 9:16 automatically — expected to work with little/no change; **verify on the
  still-preview**.

### 3. Background music layer (decided: local royalty-free library)
- `engine/video/music/` — cleared tracks tagged by mood, plus `manifest.json` mapping
  `mood → [track files]` and the **attribution string** each license requires.
- Render selects a track matching the script's `mood`, **deterministic**, rotated by idea
  id so consecutive shorts don't repeat (hash of id — no `random`).
- Remotion layers it as a second `<Audio>` at **low constant volume (~0.12–0.15)** under
  the narration, looped/trimmed to the short's length. (Constant low gain is the standard
  faceless approach; sidechain ducking is overkill.)
- **Attribution** appended to the video description in metadata.
- **Self-stub:** empty library / no track for a mood → render proceeds *without* music,
  never crashes (project never-crash rule).
- **Copyright:** literally trending/chart tracks are Content-ID hazards for an automated
  channel (demonetization / strikes / channel takedown). The library captures the
  *trending vibe* with cleared tracks only. This is a hard line.

### 4. QC — `qc.py`
Short-specific checks on the existing QC harness: dimensions are 1080×1920,
**duration ≤ 60s** (YouTube Shorts hard limit), captions present. (Music-present is an
optional soft check — decide at plan time.)

### Out of scope (YAGNI, this cut)
- Background music on **long-form** videos (Shorts only for now).
- End-loop frame matching.
- Derived-from-long-video clipping (standalone only — decided).
- **Wiring Shorts into the 01:00 overnight job.** Prove one short renders well manually
  first, then add it to overnight as a follow-up (gate discipline).

### Build / test rail
Standard `ship-video-change`: `pytest tests/` (hook-enforced) + still-preview (never the
45-min render as a gate) + dual adversarial review (Codex + Claude) → one PR with the
`Adversarial-Reviewed:` trailer.

---

## Project C — Narration voice (softer, content-aware)

### Goal
Replace the single sharp narration voice (`af_sarah` @ 1.0) with a calmer, soft-spoken
delivery that **rotates by story register**. Improves long-form AND Shorts (shared TTS).

### Decided
- Three voices, mapped by the same `mood` field that drives music (one signal, two uses):

  | `mood` | Voice | Rationale |
  |---|---|---|
  | triumphant | `bm_george` | authoritative for the payoff |
  | hype | `bm_george` | drives energy |
  | tense | `bm_lewis` | measured, investigative |
  | somber | `bf_emma` | warm, gentle for loss |

- **Speed 0.9**, **sentence gap 0.5s** for all (calmer pacing).
- Default voice `bm_george` when `mood` is missing (self-stub).

### Change (small, config-level)
- `config.py`: `NARRATION_VOICE_BY_MOOD` map, `NARRATION_SPEED = 0.9`, `NARRATION_GAP_S = 0.5`.
- `tts.py`: thread `speed` through `_synth_kokoro` (currently hardcoded `1.0` at `:124`);
  use the configurable gap (currently hardcoded `0.4` at `:121`); voice resolved from mood.
- Long-form (`UntoldVideo`) gets the same voice/speed; mood for long-form derived from its
  pillar (or default) — decide mapping at plan time.

### Verification
By-ear audition already done (`voice_samples/`); the bm_george/bm_lewis/bf_emma @ 0.9 set
is approved. Regression: existing TTS tests must still pass; add a test that voice/speed
resolve from mood.

---

## Project D — Custom thumbnails

### Goal
A custom 1280×720 thumbnail per video matching the channel reference: dark cinematic
background, **real licensed/archival subject photo** on one side, **gold size-stepped
uppercase headline** on the other, **"THE UNTOLD GAME"** wordmark bottom-centre.

### Decided
- **Subject image = real licensed/archival photo** (Wikimedia/CC, or licensed Getty/AP) —
  authentic, on-gate. **No AI-generated likenesses of real people** (ADR-0005). This makes
  sourcing **human-in-the-loop**.
- **Render = local**, NOT Canva. Canva MCP is interactively authenticated → unavailable in
  the 1am cron. Local render reuses our Chromium/Remotion stack, runs unattended, free.

### Components
1. **Thumbnail headline (model step)** — a short Claude call turns the title into 3–4
   uppercase lines with one emphasised "punch" phrase, e.g.
   `THE / OWN GOAL / THAT COST / HIM HIS LIFE` with `OWN GOAL` largest. Emits
   `[{text, size: small|med|big}]`.
2. **Remotion `Thumbnail` composition** (1280×720) rendered via **`renderStill`** (single
   frame — no video). Layers: background (subject photo if present, else atmospheric dark
   gradient/stadium) → left→right vignette scrim for text legibility → gold headline block
   (condensed uppercase, cream-gold `#E7D7A6`, size-stepped) → wordmark bottom-centre.
3. **Subject-image slot** — `produced/<id>/subject.{jpg,png}` + a sidecar
   `subject.license.json` (`{source_url, license, attribution}`). **Missing → atmospheric
   fallback** (self-stub; the overnight run never blocks on a missing photo).
4. **Output** `produced/<id>/thumbnail.png` → recorded as `thumbnail_path` in metadata.
   Required-attribution licenses append the credit to the video description. At publish,
   the uploader sets the YouTube thumbnail (Data API `thumbnails.set`).

### Flow (human-in-the-loop)
- **Overnight:** render the **atmospheric** thumbnail (no face) so the video is complete.
- **Morning approval:** user drops the sourced photo + license into the idea folder, runs
  `python3 -m engine.run_auto --thumbnail <id>` to regenerate with the real face, then
  approves. (Canva remains available for hand-crafting a hero thumbnail off the same data.)

### Out of scope (this cut)
- Auto-sourcing/auto-licensing real photos (human supplies them).
- A/B thumbnail variants.
- Thumbnails for Shorts (Shorts use the vertical frame itself; revisit later).

---

## Sequencing
1. **A** — overnight automation (small, reuses tested orchestrator). Ship, validate one
   real night.
2. **C** — narration voice (tiny config change, immediate quality win on existing videos).
3. **B** — Shorts pipeline (script mode → vertical composition → music → QC). Ship,
   validate one short manually.
4. **D** — custom thumbnails (after subject-image fork is decided).
5. **Follow-up** — wire Shorts + thumbnails into the overnight job; wall-clock-1am wake.
