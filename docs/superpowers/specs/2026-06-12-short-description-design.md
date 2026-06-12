# Richer Short descriptions — design

**Date:** 2026-06-12
**Status:** approved approach, pending spec review
**Scope:** YouTube **Shorts** metadata (`description` + `tags`). Title unchanged (idea title).
Thumbnails out of scope — YouTube auto-frame (user decision). Long-form metadata unchanged.

## Problem

Short descriptions are minimal **and** currently broken. `run_produce._short_metadata`
sets `description = first_non_blank_script_line + "#Shorts #<Sport>"`. Because metadata was
built from the pre-clean scripts, the first line was scaffolding, so live/staged descriptions
read `"MOOD: tense\n\n#Shorts #F1"` — no real description. Even when fixed, one raw script line
+ two hashtags is thin.

## Goal

Each Short gets a **purpose-written 2–3 sentence description** that hooks the viewer without
spoiling the payoff, followed by `#Shorts` + sport/topic hashtags, plus a music-credit line
when a CC-BY track was used. Generated from the **clean** script, so no scaffolding ever leaks.

## Architecture

### 1. `engine/pipeline/metadata.py` — `generate_short_metadata(idea, script) -> dict`

A small, single LLM call (same `MODEL`) that returns `{description, tags}` for a Short:

- **System prompt:** "Write a 2–3 sentence YouTube Shorts description for a sports-history
  channel. Hook the viewer and tease the intrigue; do NOT spoil the ending. Plain text only —
  no markdown, no 'MOOD:' line, no hashtags, no preamble." Structured output
  (`{"description": str, "tags": [str]}`) so no fragile parsing; tags are 5–10 specific
  search terms/entities from the script.
- The function then **assembles** the final description deterministically:
  `description = llm.description + "\n\n#Shorts #<Sport>" + extra topic hashtags` and appends
  `"\n\nMusic: <credit>"` when `produced/<id>/video/music_credit.txt` exists (CC-BY tracks).
- Final `tags = ["Shorts", sport, pillar] + llm.tags` (deduped, ≤30).
- Title is **not** generated here — caller keeps `idea["title_variants"][0]`.

Returns `{"title", "description", "tags"}` to match the shape `_short_metadata` returns today.

### 2. `engine/run_produce.py` — use the new generator

Replace the inline `_short_metadata(idea, script)` call with
`metadata.generate_short_metadata(idea, script)`. `_short_metadata` is deleted (its job moves
into the pipeline module where the long-form `MetadataWriter` already lives). The script passed
in is already the **clean** body (post `clean_short_body`), so no scaffolding reaches the
description.

### 3. Backfill + republish (one-off, after the code lands)

- Regenerate `metadata.json` for the 5 existing shorts via
  `run_produce --id <id> --short --metadata-only` (cheap — skips script gen, reuses the clean
  on-disk script).
- **Update Senna's live description** (already uploaded, unlisted) via
  `youtube.videos().update(part="snippet", ...)` with the new title/description/tags/category.
- Upload the other 4 as unlisted with the good metadata (user-triggered / authorized).

## Data flow

clean script.md → `generate_short_metadata` (LLM description + tags) → assemble hashtags +
music credit → `metadata.json` → `run_auto --approve` → YouTube `snippet.description`.

## Error handling

If the LLM call fails, fall back to the existing minimal behavior (first clean line +
`#Shorts #<Sport>`) so a produce run never crashes (self-stub). Missing `music_credit.txt` →
no music line. Missing sport → no sport hashtag.

## Testing (`python3 -m pytest tests/`)

- `generate_short_metadata` with the LLM call **monkeypatched** to a fixed
  `{"description": "...", "tags": [...]}`:
  - final description contains the LLM text, `#Shorts`, and `#<Sport>`, and **no** `MOOD:` /
    `---` / preamble;
  - music credit line appended only when a `music_credit.txt` is present (use `tmp_path`);
  - tags include `Shorts` + sport + the LLM tags, deduped, ≤30;
  - title is the idea title.
- LLM-failure path falls back to the minimal description (monkeypatch the call to raise).

## Out of scope (YAGNI)

Custom thumbnails (auto-frame chosen), long-form metadata changes, per-video CTA links,
A/B title generation, and hashtag research. None needed to make Short descriptions good.
