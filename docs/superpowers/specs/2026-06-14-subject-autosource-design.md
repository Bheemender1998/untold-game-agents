# Auto-source subject photos (Wikipedia → Pexels) — design

**Date:** 2026-06-14
**Status:** approved (brainstorm) → writing-plans next
**Branch:** `feat/subject-autosource`

## Problem

Thumbnails need a real subject photo at `produced/<id>/<fmt>/subject.png`, currently dropped by
hand — 6+ manual downloads to thumbnail the published shorts. We already call the Wikipedia API
(fact-gate) and have a Pexels key (b-roll), so we can fetch the photo automatically.

## Decisions (locked in brainstorm)

1. **Person photo = Wikipedia lead image** (the curated infobox portrait via `pageimages`) —
   real, freely-licensed, avoids junk. Reuses `engine/ideate/wikipedia.py`.
2. **Fallback = Pexels stock photo** for a generic concept (e.g. "fifa world cup trophy") when
   the story has no single person or Wikipedia has no image. Reuses the Pexels key.
3. **Separate `run_subject` step** + review. A **human-supplied `subject.png` always wins** —
   auto-fetch never overwrites it.
4. **Capture attribution** (CC license + author for Wikimedia; photographer for Pexels) to
   `subject_credit.txt` so it can go in the video description — same as music/footage credits.

## Scope

| Surface | Change |
|---------|--------|
| `engine/ideate/wikipedia.py` | + `lead_image(query)` (+ `_image_credit`) |
| `engine/video/footage.py` | + `fetch_photo(query, out_path)` (Pexels v1 photo search) |
| `engine/pipeline/subject.py` (new) | `source_subject(idea, fmt)` orchestrator + LLM subject extraction |
| `engine/run_subject.py` (new) | CLI `--id --format` |
| `CLAUDE.md`, `README.md` | docs sync: new `run_subject` entrypoint + layout note (REQUIRED — engine change) |
| tests | `test_wikipedia.py`, `test_footage.py`, `test_subject.py` |

Out of scope: changing the thumbnail compositor; auto-running subject sourcing inside
`run_thumbnail` (kept a separate step); historical-accuracy curation of the fetched image.

## Design

### A. `wikipedia.lead_image(query, min_width=600) -> (url, credit) | None`

Resolve the page with the existing `search_title(query)`, then the `pageimages` API
(`piprop=original|name`) for the lead image URL + width. Reject when missing, below `min_width`,
or an **`.svg`** (Pillow can't open SVG). Credit via `_image_credit(pageimage)` →
`imageinfo`/`extmetadata` (`Artist` HTML-stripped + `LicenseShortName`), formatted
`"<artist> / <license> via Wikimedia Commons"` (or just `"via Wikimedia Commons"`). Never raises
(same contract as the rest of the module).

### B. `footage.fetch_photo(query, out_path, api_key=None, min_width=1080) -> credit | None`

Pexels **photo** search (`https://api.pexels.com/v1/search`, `orientation=portrait`,
`size=large`) using the existing browser `_UA` + `Authorization` header. Download the first
result's `src.large2x`/`src.original` via the existing `_download`. Returns
`"Photo by <photographer> on Pexels"` on success; `None` on missing key / no result / fail.
Never raises.

### C. `engine/pipeline/subject.py`

```
source_subject(idea, fmt) -> {"source": "human"|"wikipedia"|"pexels"|None, "path": str, "credit": str}
```
1. If `subject.png`/`.jpg` already present (`os.path.exists(paths.subject_path(...))`) → return
   `source="human"`, untouched.
2. `person, concept = _subject_query(idea, script)` — one structured LLM call (mirrors
   `thumbnail._thumbnail_text_llm`) returning `{person, concept}` from title + script
   (`idea.get("script")` or read `script_path`, long/short fallback). `("","")` on failure.
3. If `person`: `wikipedia.lead_image(person)` → `_download` to `subject.png` → write credit →
   `source="wikipedia"`.
4. Else if `concept`: `footage.fetch_photo(concept, subject.png)` → write credit →
   `source="pexels"`.
5. Else `source=None` (leave for manual). Self-stub on every failure — never raises.

Helpers: `_download(url, out)` (browser UA, never raises), `_write_credit(id, fmt, credit)` →
`produced/<id>/<fmt>/subject_credit.txt`.

### D. `engine/run_subject.py`

`--id <id> --format {long,short}` → `q.get_by_id` (or `{"id":id}`) → `source_subject` →
print `✓ … via wikipedia — <credit>` / `✓ … via pexels — <credit>` / `· already has a subject`
/ `✗ none found — drop one at <path>`.

### E. Docs sync (required by the docs-staleness gate)

`CLAUDE.md` Entrypoints — add `run_subject`; layout table note that subjects can be auto-sourced.
`README.md` — same entrypoint addition. (This is an `engine/**` change, so the new gate requires
a docs change in the PR.)

## Error handling / integrity

- Every network/LLM call self-stubs to `None`; a missing photo never crashes — `generate_thumbnail`
  already self-stubs on no subject.
- **Integrity:** Wikipedia/Commons are real, freely-licensed photos; Pexels is symbolic stock —
  no AI-generated likenesses (ADR-0005). Attribution captured for license compliance.
- Human override is sacrosanct: an existing `subject.png` is never overwritten.

## Testing (`pytest tests/ -q`; mock all network/LLM — no live calls)

- `test_wikipedia.py`: monkeypatch `requests.get` → `lead_image` returns `(url, credit)` for a
  page with an original image; `None` when no image / below min_width / `.svg`. `_image_credit`
  formats Artist+License and HTML-strips.
- `test_footage.py`: monkeypatch `urllib.request.urlopen` + `_download` → `fetch_photo` returns a
  photographer credit; `None` on no key / no photos.
- `test_subject.py`: human photo present → `source="human"`, no fetch (monkeypatch fetchers to
  assert not called); person → wikipedia path + credit file written; no person → pexels; neither →
  `None`; `_subject_query` parses the schema and returns `("","")` on error. Use `tmp_path` +
  monkeypatch `paths.PRODUCED_DIR`; monkeypatch `_download` to create a dummy file.

## Proof

`python3 -m engine.run_subject --id 648d57e6 --format short` → fetches Felipe Massa's Wikipedia
portrait → `subject.png` + `subject_credit.txt`. Run across the 8 published shorts, then
`run_thumbnail --format short` for each → covers.
