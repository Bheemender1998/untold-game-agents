# Channel positioning — "The Editorial Archive"

**Date:** 2026-06-13
**Status:** Approved — ready for implementation plan
**Slice:** Positioning + thumbnails feedback → sub-slice **B (channel positioning)**. Sub-slice A (the thumbnail engine) shipped in PR #24.

## Problem

External feedback flagged a channel "identity crisis": "The Untold Game" + poetic packaging can read as a *gaming/indie* channel rather than premium sports-history documentary, leaking clicks. The fix is channel-level positioning: a banner that screams premium sports history, and channel copy that anchors the category unmistakably — both built on the now-shipped "Prestige Feed Killer" visual language so the channel page and the feed feel like one brand.

The chosen positioning line (canonical everywhere) is **"The Archive of Lost Sports History."**

## Scope

**In scope:** a deterministic Pillow **banner generator**, a CLI, the **positioning copy** (banner subtitle + channel description), and **config/profile sync** so the channel identity (and every idea agent's context) reflects the sharpened positioning. Applied **manually** in YouTube Studio.

**Out of scope (deliberate):** programmatic application via the YouTube API (manual, channel art changes rarely — avoids OAuth-scope expansion + speculative Stage-2 surface); A/B banners; logo/avatar redesign; any per-video work.

## Decisions (settled)

1. **Banner is generated** (Pillow, textural backdrop — no real-person imagery, no sourcing), reusing the thumbnail engine's bundled fonts + brand primitives. Reproducible, brand-consistent with thumbnails.
2. **Applied manually** — the engine outputs the asset + copy; the human uploads/pastes in YouTube Studio.
3. **Positioning copy is hand-authored** (in config/profile), not LLM-at-runtime.
4. **"The Archive of Lost Sports History" is canonical** — banner subtitle, `config.CHANNEL_SUBTITLE`, and the `channel.yaml` tagline.

## Components

### 1. `engine/pipeline/banner.py` — deterministic Pillow banner generator
- `compose_banner(out_path: str) -> None` — renders **`channel/banner.png` (2560×1440)**.
- Reads the channel name + subtitle from `config` (`CHANNEL_NAME`, `CHANNEL_SUBTITLE`).
- **Layout (the locked "Editorial Archive"):** everything centered within the **TV-safe band** (YouTube's all-device-safe region, **1546×423**, centered):
  1. Backdrop: warm archival linear gradient → film grain (`Image.effect_noise`) → vignette (`Image.radial_gradient`). Same brand primitives as `thumbnail.compose` (textural — no photo).
  2. **Wordmark** `CHANNEL_NAME` (`THE UNTOLD GAME`) in **Anton** (`thumbnail.TENSION_FONT`), uppercase, auto-fit so its width ≤ the safe-band width, centered, white + drop shadow.
  3. **Red rule** (`thumbnail.RED`) centered directly beneath the wordmark — continuity with the feed thumbnails' tension marker.
  4. **Subtitle** `CHANNEL_SUBTITLE` ("The Archive of Lost Sports History") in **Playfair Display Italic**, centered beneath the rule, cream.
- **Geometry is testable:** a helper (e.g. `_layout_banner(draw) -> dict` returning the wordmark font + the wordmark/rule/subtitle block boxes) so a test can assert the stack fits inside the safe band.
- Pure-Pillow, deterministic, no inputs → always reproducible; never crashes.

### 2. Fonts (bundled, OFL)
- Wordmark reuses the already-bundled **Anton** (`engine/pipeline/assets/fonts/Anton-Regular.ttf`).
- **Add `PlayfairDisplay-Italic.ttf`** (OFL) to `engine/pipeline/assets/fonts/` for the italic subtitle (the bundled `PlayfairDisplay.ttf` is the roman/upright variable font; the design calls for italic). `banner.py` references it via a `SUBTITLE_FONT` constant.

### 3. `engine/run_banner.py` — CLI
- `python3 -m engine.run_banner` → calls `compose_banner`, writes `channel/banner.png`, and writes `channel/description.txt` from `config.CHANNEL_DESCRIPTION` (for manual paste). Prints both paths + a one-line "upload in YouTube Studio" reminder. Headless-safe.

### 4. Positioning copy + config/profile sync
- **`engine/config.py`** — add:
  - `CHANNEL_NAME = "The Untold Game"`
  - `CHANNEL_SUBTITLE = "The Archive of Lost Sports History"`
  - `CHANNEL_DESCRIPTION` = the approved description (below).
  - Update the `Tagline:` line in `CHANNEL_CONTEXT` to `The Archive of Lost Sports History` (so idea agents' context carries the canonical positioning).
- **`engine/profiles/channel.yaml`** — set `tagline: "The Archive of Lost Sports History"`; add a `description:` field mirroring `CHANNEL_DESCRIPTION` (the file already mirrors `config.CHANNEL_CONTEXT`).

**Approved channel description (`CHANNEL_DESCRIPTION`):**
```
The Untold Game — The Archive of Lost Sports History.
Premium, heavily researched documentaries on the forgotten, buried, and deliberately overlooked stories behind the world's biggest games — F1, football, cricket, the NFL, and beyond. Cinematic, told in a 30-for-30 voice. Every claim verified; nothing sensationalized.
▶ New untold stories regularly. Subscribe → @untoldgamemedia
```
(Leads with the canonical line; "documentaries / sports / leagues" sit in the body for the literal algorithmic category signal.)

### 5. Paths
- `engine/paths.py` — add `CHANNEL_DIR` (`<root>/channel`), `channel_banner_path()`, `channel_description_path()`.
- `channel/` is a generated-output dir → add to `.gitignore` (the banner is deterministically regenerable; the *source of truth* for copy is `config`/`channel.yaml`).

## Application (manual)
`python3 -m engine.run_banner` → upload `channel/banner.png` as channel art and paste `channel/description.txt` into the channel "About" in YouTube Studio. One-time; no API/scope work.

## Testing (`python3 -m pytest tests/`, under `python3`)
1. **Banner output:** `compose_banner(out)` writes a file Pillow reads back as exactly **2560×1440** (PNG).
2. **Safe-area containment (locked):** `_layout_banner` places the wordmark + rule + subtitle block within the TV-safe band — assert block width ≤ safe width and block bbox within the safe box (regression guard for the layout).
3. **Deterministic / no-crash:** `compose_banner` runs with no external inputs and raises nothing.
4. **Subtitle font present:** `PlayfairDisplay-Italic.ttf` exists and loads via `ImageFont.truetype`.
5. **CLI writes copy:** `run_banner` writes `channel/description.txt` equal to `config.CHANNEL_DESCRIPTION`.
6. **Config canonical:** `config.CHANNEL_SUBTITLE == "The Archive of Lost Sports History"` and it appears in `CHANNEL_CONTEXT` (regression guard that the positioning line stays canonical).

## Integrity / risks
- No real-person imagery (textural backdrop) → no ADR-0005 likeness concern. No new publish API surface.
- **Wordmark overflow:** auto-fit shrinks `THE UNTOLD GAME` to the safe-band width; a long name can't run off-canvas.
- **Missing italic font → import/runtime fail:** the plan bundles + tests it (mirrors the thumbnail font handling).
- Changing `CHANNEL_CONTEXT`'s tagline shifts idea-agent context by one line (intended — aligns generation with positioning); low risk, the test in §6 pins the canonical line.

## Open questions
None — design approved.
