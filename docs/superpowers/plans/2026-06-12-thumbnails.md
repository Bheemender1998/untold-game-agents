# Custom Thumbnails (Project D) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A custom 1280×720 thumbnail per long-form video matching the channel reference — dark cinematic background, a **real licensed/archival subject photo** on one side, a **gold size-stepped uppercase headline**, and the **"THE UNTOLD GAME"** wordmark bottom-centre — rendered locally (not Canva), with an **atmospheric fallback** when no photo is supplied yet.

**Architecture:** Four pieces. D1 turns the title into a size-stepped headline (model step). D2 adds a Remotion `Thumbnail` composition rendered via `renderStill`. D3 adds the human-in-the-loop subject-photo slot + license + atmospheric fallback + a regenerate CLI. D4 wires the thumbnail into metadata and the YouTube upload. Each piece ships via `ship-video-change`.

**Tech Stack:** Python 3 (orchestration/QC), Remotion `renderStill` (Chromium), Claude (headline), YouTube Data API v3 (`thumbnails.set`), pytest.

**Spec:** Project D in `docs/superpowers/specs/2026-06-12-overnight-and-shorts-design.md`.

**Decisions (locked by the spec):** real licensed/archival photo only — **NO AI likenesses of real people** (ADR-0005); **local render**, not Canva (Canva MCP is interactively-authed → unavailable in the 1am cron); atmospheric fallback when no photo; sourcing is human-in-the-loop at morning approval.

**Conventions:** `python3` only; absolute `engine.*` imports; pytest after each `engine/**.py` edit; feature branch per piece, never `main`; the still-render is the visual gate, never the 45-min video render.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `engine/pipeline/thumbnail.py` | headline model step + orchestration (currently a stub) | Rewrite |
| `engine/video/remotion/src/Thumbnail.tsx` | the 1280×720 thumbnail composition | Create |
| `engine/video/remotion/src/Root.tsx` | register `Thumbnail` | Modify |
| `engine/video/remotion/src/types.ts` | `ThumbnailProps` | Modify |
| `engine/video/render_thumbnail.py` | build props + `npx remotion still` → PNG | Create |
| `engine/run_auto.py` | `--thumbnail <id>` regenerate command | Modify |
| `engine/publish/uploader.py` | set the YouTube thumbnail on upload | Modify |
| `tests/test_thumbnail.py` | headline parse, license read, atmospheric fallback | Create |

---

# Piece D1 — Thumbnail headline (model step)

**Branch:** `feat/thumb-headline`

### Task D1.1: `thumbnail_headline(title) -> list[dict]`
**Files:** Rewrite `engine/pipeline/thumbnail.py`; Test: `tests/test_thumbnail.py`.

- [ ] **TDD.** `thumbnail_headline(title: str) -> list[{"text": str, "size": "small"|"med"|"big"}]` — a Claude call (reuse the project's Anthropic client / `BaseAgent` pattern) that breaks the title into 3–4 UPPERCASE lines with **exactly one** `big` "punch" line, e.g. `THE / OWN GOAL(big) / THAT COST / HIM HIS LIFE`. Add a `_parse_headline(raw)` that tolerates the model returning JSON or `SIZE|TEXT` lines, validates exactly-one-big (if zero/many, promote the longest/first to big deterministically), uppercases, and caps at 4 lines. Tests mock the model and assert: parse of a well-formed response; exactly-one-big invariant enforced on a malformed response; ≤4 lines. Commit: `feat(thumbnail): size-stepped headline from title (model)`.

---

# Piece D2 — Remotion `Thumbnail` composition + still render

**Branch:** `feat/thumb-render`

### Task D2.1: `ThumbnailProps` + `Thumbnail.tsx` + Root registration
**Files:** Create `engine/video/remotion/src/Thumbnail.tsx`; modify `types.ts`, `Root.tsx`.
- [ ] Add `ThumbnailProps` to `types.ts`: `{width, height, lines: {text,size}[], subjectSrc?: string, wordmark: string}`.
- [ ] `Thumbnail.tsx` (1280×720, single frame): `<AbsoluteFill bg #0a0a0a>` → background layer (`subjectSrc` via `<Img staticFile>` `objectFit: cover` anchored left, OR an atmospheric dark gradient + subtle vignette when absent) → a **left→right scrim** (`linear-gradient` to near-black on the headline side) for legibility → the **gold (`#E7D7A6`) size-stepped headline** block (condensed uppercase — reuse the `anton` font; sizes ~ big 132 / med 92 / small 56 px) right-of-centre → the wordmark (`oswald`, letter-spaced, white) bottom-centre. Mirror the existing components' style vocabulary.
- [ ] Register `<Composition id="Thumbnail" component={Thumbnail} calculateMetadata={() => ({width:1280, height:720, fps:1, durationInFrames:1})} />` in `Root.tsx` (single still frame).

### Task D2.2: `render_thumbnail.py` — props → PNG
**Files:** Create `engine/video/render_thumbnail.py`.
- [ ] `render_thumbnail(idea_id, subject_path=None) -> str`: load the produced idea, build `ThumbnailProps` (call `thumbnail.thumbnail_headline(title)`, set `subjectSrc` if a staged photo exists), write a props json, run `npx remotion still src/index.ts Thumbnail <out> --props=<props>` (mirror `render_remotion.py`'s subprocess + asset-staging pattern), return `produced/<id>/thumbnail.png`. **Visual gate:** render one with a photo and one atmospheric; open both PNGs; confirm headline legibility + safe composition. Commit: `feat(thumbnail): Thumbnail composition + renderStill pipeline`.

---

# Piece D3 — Subject-photo slot + atmospheric fallback + regenerate CLI

**Branch:** `feat/thumb-subject`

### Task D3.1: subject slot + license + fallback selection
**Files:** Modify `engine/video/render_thumbnail.py`; Test: `tests/test_thumbnail.py`.
- [ ] **TDD.** `subject_for(idea_id) -> dict | None`: looks for `produced/<id>/subject.{jpg,jpeg,png}` + a sidecar `subject.license.json` (`{source_url, license, attribution}`). Returns `{"path","attribution"}` if present, else `None` (→ atmospheric). `render_thumbnail` uses it: photo present → `subjectSrc`; absent → atmospheric. Tests (tmp produced dir): photo present → returned with attribution; absent → `None`; license sidecar missing → `attribution=""`. Commit: `feat(thumbnail): human-supplied subject photo slot + license; atmospheric fallback`.

### Task D3.2: `run_auto --thumbnail <id>`
**Files:** Modify `engine/run_auto.py`.
- [ ] Add a `--thumbnail <id>` command that calls `render_thumbnail(id)` and prints the output path (the morning regenerate-with-photo step). Add a test mirroring the existing `cmd_*` tests. Commit: `feat(run_auto): --thumbnail regenerate command`.

---

# Piece D4 — Wire into metadata + publish

**Branch:** `feat/thumb-publish`

### Task D4.1: record path + attribution; set on upload
**Files:** Modify `engine/pipeline/thumbnail.py` (or `run_produce.py`) to record `thumbnail_path` on the idea + append required-license attribution to the metadata `description`; modify `engine/publish/uploader.py` to set the thumbnail.
- [ ] Record `thumbnail_path` (relpath) on the idea and, when the subject license requires credit, append the attribution string to `metadata.description`. In `uploader.upload(...)`, after the video insert, call the YouTube Data API `thumbnails().set(videoId=..., media_body=thumbnail_path)` when a thumbnail exists (verify the authed `service` is reachable — reuse `auth.get_credentials()`). Test: mock the YouTube client; assert `thumbnails.set` is called with the right path when present and skipped when absent. Commit: `feat(publish): set custom YouTube thumbnail + license attribution`.

---

## Flow (human-in-the-loop)
- **Overnight:** thumbnails render **atmospheric** (no face) so the video is complete.
- **Morning approval:** drop `subject.jpg` + `subject.license.json` into `produced/<id>/`, run `python3 -m engine.run_auto --thumbnail <id>` to regenerate with the real face, then approve. (Canva stays available for a hand-crafted hero thumbnail off the same headline data.)

## Out of scope (this project)
- Auto-sourcing/auto-licensing real photos (human supplies them).
- A/B thumbnail variants.
- Thumbnails for Shorts (Shorts use the vertical frame itself).
- AI-generated likenesses of real people (ADR-0005 — hard no).

## Sequencing
D1 (headline) → D2 (composition + still) → D3 (subject slot + fallback + CLI) → D4 (publish wiring). D1–D3 deliver a usable local thumbnail; D4 connects it to YouTube upload.
