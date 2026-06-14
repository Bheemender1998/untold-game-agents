# Vertical 9:16 thumbnail (bold look, real photos) — design

**Date:** 2026-06-13
**Status:** approved (brainstorm) → writing-plans next
**Branch:** `feat/vertical-thumbnail`

## Problem

We need a bold, scroll-stopping **9:16 (1080×1920)** cover for shorts — for the YouTube Shorts
channel grid and especially TikTok / Instagram Reels covers. The existing thumbnail engine
(`engine/pipeline/thumbnail.py`) only renders the 16:9 (1280×720) "Prestige Feed Killer"
template; `run_thumbnail --format short` reads the short subject path but still outputs 16:9.

## Decisions (locked in brainstorm)

1. **Bold look, REAL photos** — replicate the giant-text dramatic style of the reference grid
   using the human-supplied subject photo. **No AI-fabricated likenesses** (ADR-0005 integrity gate).
2. **Layout: bottom-stacked** — subject fills the frame; giant text stacked in the lower third
   over a dark gradient (clears the TikTok/Reels top UI and the YT Shorts title).
3. **Text colour: white + one accent line** — all lines white except the accent (payoff) line in
   channel **red** (`RED = (224,48,30)`, the same red as the 16:9 marker). Punchy but on-brand
   (not loud multicolor).

## Scope

| Surface | Change |
|---------|--------|
| `engine/pipeline/thumbnail.py` | new `compose_vertical(subject_path, tension_text, out_path)` (1080×1920); `generate_thumbnail` routes `fmt=="short"` to it |
| `tests/test_thumbnail.py` | vertical dims, text fit, accent colouring, fmt routing, self-stub |

Out of scope: a new LLM text call (reuse the existing `_thumbnail_text`); changing the 16:9
template; sourcing photos (human-supplied); TikTok/IG upload (separate multi-platform slice).

## Design

### `compose_vertical(subject_path, tension_text, out_path)` — new

Renders a 1080×1920 JPEG, reusing the existing `compose`'s treatment building blocks:

- `VW, VH = 1080, 1920`. Subject cropped to fill via `ImageOps.fit(..., (VW, VH))`.
- Reuse the existing cinematic grade + warm side-light (factor the shared steps so both
  `compose` and `compose_vertical` use them; if cleanly factoring is awkward, duplicating the
  ~6 grade lines is acceptable — keep it readable).
- A bottom-weighted dark gradient scrim (so text in the lower third stays legible on bright photos).
- **Text** (Anton, uppercase): wrap `tension_text` to fit `MAX_TEXT_W_V = int(VW*0.88)` at the
  largest font in `[V_MAX_FONT, V_MIN_FONT]` (e.g. 170..56) that fits in ≤4 lines and within the
  lower-third text box — same fit approach as `_layout_tension`. Stack the lines bottom-aligned
  with a bottom margin.
- **Accent**: the LAST wrapped line is drawn in `RED`; all other lines white. (The payoff word
  is the natural accent; this needs no LLM and is deterministic.) Each line gets the existing
  drop shadow.
- **Stamp**: the existing "THE UNTOLD GAME" stamp (Playfair) in a top or bottom corner.
- Save as JPEG to `out_path` (same as `compose`).

A new `_layout_tension_vertical(text, draw)` (mirroring `_layout_tension`) does the
width/line-count fit for the vertical text box; or generalise `_layout_tension` to take
(max_w, max_h, max_font, min_font, max_lines) and call it from both. Prefer the generalised
helper if it stays clear.

### `generate_thumbnail(idea, fmt)` — route by format

```python
    text = _thumbnail_text(idea, idea.get("script", ""))
    out = paths.thumbnail_path(idea_id, fmt)
    if fmt == "short":
        compose_vertical(subject, text, out)
    else:
        compose(subject, text, out)
```

Everything else (subject lookup, self-stub on missing subject, stale-thumbnail removal,
return value) is unchanged.

## Error handling / self-stub

- No subject photo → existing self-stub (logs, returns idea, writes nothing). Unchanged.
- Empty `tension_text` → render the cover with no text band (subject + stamp only), never crash
  (mirror `compose`, which guards `if text:`).
- A single very long word that can't fit even at `V_MIN_FONT` → the fit loop falls back to the
  min font (same behaviour as `_layout_tension`); never raises.

## Testing

`python3 -m pytest tests/ -q` is the contract. New/updated in `tests/test_thumbnail.py`:

- `compose_vertical` writes a JPEG of size exactly **1080×1920** given a small synthetic subject
  image (`Image.new`) + a sample phrase (open the output with PIL, assert `.size`).
- Text fit: a long phrase wraps to ≤4 lines and the chosen font is within
  `[V_MIN_FONT, V_MAX_FONT]` (assert via the layout helper's return).
- Accent: the last line is rendered (smoke — assert the function completes and the output is
  non-empty / has expected dimensions; pixel-colour assertions are brittle, so assert the
  helper marks the last line index as accent rather than sampling pixels).
- `generate_thumbnail(idea, "short")` produces a 1080×1920 file; `(..., "long")` stays 1280×720
  (monkeypatch the subject path to a synthetic image; reuse existing test patterns).
- Self-stub: no subject photo → returns idea unchanged, writes nothing (existing pattern).

Render/LLM are not test gates — tests use synthetic images and the deterministic layout, no
network. `_thumbnail_text` is already covered; the LLM text call is monkeypatched/skipped.

## Proof

Drop a real Cantona photo at `produced/25051da8/short/subject.png`, run
`python3 -m engine.run_thumbnail --id 25051da8 --format short`, open the 1080×1920 cover and
confirm the bold bottom-stacked text with a red accent line over the real photo.
