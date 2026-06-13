# Thumbnail generation engine — "Prestige Feed Killer"

**Date:** 2026-06-13
**Status:** Approved — ready for implementation plan
**Slice:** Positioning + thumbnails feedback → sub-slice **A (thumbnail engine)**. Sub-slice B (channel banner + description positioning) is a separate, lighter follow-up.

## Problem

External feedback: the channel's text-heavy/poetic packaging risks reading as a gaming or pop-culture channel rather than premium sports-history documentary, and leaks clicks. `engine/pipeline/thumbnail.py` is a 7-line stub. The approved visual direction is **"The Prestige Feed Killer"** — a two-layer template:

- **Asset layer (constant):** warm archival color grade, film grain, heavy vignette, a serif **UNTOLD** stamp. Establishes prestige-sports-documentary identity on sight (kills the gaming read).
- **Tension layer (variable):** a side-lit subject, a 2–4 word **withholding** line (no premise spoiler), and a single red marker. Stops the scroll, front-loads the mystery — mirrors the shipped text-layer rules.

## Scope

**In scope:** a deterministic Pillow compositor that turns a human-supplied subject photo + a (generated or overridden) withholding line into a 1280×720 thumbnail; a tension-line generator; a CLI; and the minimal publish-path wiring so the thumbnail actually reaches YouTube.

**Out of scope (deliberate):**
- Channel banner + description positioning → separate follow-up.
- A/B thumbnail variants (the old stub's TODO) → YAGNI; one thumbnail per video.
- Subject-photo *sourcing* — the human supplies it (see Inputs); AI-generating a real likeness is forbidden (ADR-0005).

**Gate discipline:** thumbnails are a Stage-2/publishing feature, but justified now (not speculative) — 5 unlisted shorts + longs are awaiting publish and need thumbnails.

## Decisions (settled)

1. **Pillow in the `python3` env.** The compositor is lightweight, deterministic (no Remotion, no ML) and must be unit-testable under `python3 -m pytest` (the project contract), so it lives in the produce/orchestration env — not `.venv-video`. **Adds `Pillow` as a `python3` dependency** (requirements + install); the PostToolUse test hook fails at import until Pillow is installed, so installing it is the first implementation step.
2. **Subject photo is human-supplied** at a known path; the engine never sources or generates it.
3. **Tension line: auto-generated, human-overridable**, reusing the shipped withholding rule + the `title_numbers_within` digit backstop.
4. **`cmd_approve` publish-wiring is in scope** — minimal, present-only-if-exists, cannot break existing publish.

## Components

### 1. `engine/pipeline/thumbnail.py` (replaces the stub) — deterministic Pillow compositor
- `compose(subject_path: str, tension_text: str, out_path: str) -> None` — renders the 1280×720 JPG (quality tuned to stay < 2 MB, YouTube's limit).
- `generate_thumbnail(idea: dict, fmt: str) -> dict` — resolves the subject photo path and the tension text, calls `compose`, records the output path on the returned idea dict. **Self-stubs** (logs "no subject photo — skipped", returns the idea unchanged, writes no file, never raises) when the subject photo is absent.

### Compositing recipe (encodes the locked look)
**Asset layer (constant):**
1. Open subject → resize/crop to cover 1280×720.
2. Archival grade: desaturate (`ImageEnhance.Color`) + warm duotone/sepia tint.
3. Side-light: composite a radial highlight from the subject side.
4. Film grain: `Image.effect_noise((1280,720), sigma)` overlaid at low opacity.
5. Vignette: multiply by a radial alpha mask.
6. Paste the serif **UNTOLD** stamp (bordered box) top-right.

**Tension layer (variable):**
7. Render the withholding line in the condensed display font, right-aligned, **auto-fit**: shrink font size and **word-wrap** so the block fits a max width/height; supports 1–3 lines.
8. White fill + drop shadow for contrast over the graded asset.
9. **Red marker bar anchored to the text block's bounding box** — its position is computed from the rendered text bbox (gap below the last line), NOT the frame bottom. A 1-line vs 3-line title moves the marker with the text; the text+marker stay one unit and never drift into the subject. **(Locked layout rule — regression-tested.)**

### 2. Tension-line generator
- `_thumbnail_text_llm(idea: dict, script: str) -> str` — one structured-output call (`{"line": str}`), system prompt carries the withholding rule (front-load mystery; 2–4 words; exact-or-no specifics; script-only). Raises on failure.
- `_thumbnail_text(idea, script) -> str` — returns `idea["thumbnail_text"]` verbatim if set (human override); else the LLM line, guarded by `title_numbers_within(line, script)` (reused from `engine/pipeline/script.py`); on LLM failure / empty / backstop rejection, falls back to the override or, if none, to an empty string (caller then composites with no tension text rather than crashing).

### 3. Assets / fonts (bundled, OFL-licensed)
- Tension text: **Anton** (heavy condensed). UNTOLD stamp: **Playfair Display** (serif).
- Committed under `engine/pipeline/assets/fonts/Anton-Regular.ttf` and `PlayfairDisplay-Regular.ttf`. Grade/grain/vignette are pure Pillow (no numpy).

### 4. Inputs & paths (extend `engine/paths.py`, reuse `artifact_dir`)
- Subject (human-dropped): `produced/<id>/<fmt>/subject.png` (accept `.png` or `.jpg`).
- Output: `produced/<id>/<fmt>/thumbnail.jpg`.
- New `paths.thumbnail_path(idea_id, fmt)` and `paths.subject_path(idea_id, fmt)` (the latter resolves `.png`/`.jpg`).

### 5. CLI — `engine/run_thumbnail.py`
- `python3 -m engine.run_thumbnail --id <id> [--format long|short]` → `generate_thumbnail`; if no subject photo, print the exact path to drop it at and exit non-zero. Headless-safe.

### 6. Publish wiring (minimal)
- In `engine/run_auto.py` `cmd_approve`: if `paths.thumbnail_path(id, fmt)` exists, pass it as `thumbnail_path=` to `uploader.upload(...)` (long and companion short). The uploader already calls `youtube.thumbnails().set()` when given a path — no uploader change. Present-only-if-exists: when absent, behaviour is exactly as today.

## Testing (`python3 -m pytest tests/`, under `python3`)
1. **Compositor output:** `compose(synthetic_subject_png, "10 DAYS LATER", out)` writes a file Pillow reads back as exactly `1280×720`.
2. **Marker-anchored-to-text (locked rule):** for a 1-line vs a 3-line tension string, assert the red marker's top-y sits a fixed gap below the rendered text block's bbox bottom (tracks the text, not the frame) — guards the rule against future edits.
3. **Self-stub:** `generate_thumbnail(idea_without_subject, fmt)` returns the idea, writes no file, raises nothing.
4. **Tension generator:** `idea["thumbnail_text"]` override is used verbatim; mocked-LLM happy path returns the line; a line with a fabricated number (not in script) → `title_numbers_within` rejects → falls back (to override, else empty).
5. **Assets present:** the two bundled `.ttf` files exist and load via `ImageFont.truetype`.

## Integrity (ADR-0005)
Subject photo is human-curated (no fabricated likeness). Tension line is script-only + digit-backstopped + self-stubbing. The compositor cannot introduce an unverified specific. The UNTOLD stamp is fixed brand text.

## Risks & mitigations
- **Pillow missing → all tests error at import** → first plan task installs Pillow + adds it to requirements before any thumbnail code is imported by tests.
- **Font files absent at runtime** → bundle them in-repo; a test asserts they load.
- **Subject photo missing at publish** → `generate_thumbnail` self-stubs; `cmd_approve` passes no `thumbnail_path`; publish proceeds as today (no thumbnail set).
- **Overlong tension text** → auto-fit shrink + wrap (1–3 lines); no overflow off-canvas.

## Open questions
None — design approved.
