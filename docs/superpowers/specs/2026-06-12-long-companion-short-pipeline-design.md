# Long + Companion-Short Pipeline — Design

**Date:** 2026-06-12
**Status:** Approved (pending spec review)
**Author:** session 11

## Problem

The 5 YouTube Shorts published 2026-06-12 (Senna, World Cup, O.J., Barry Sanders,
Sachin) have no long-form counterpart. We want each topic to exist as a full long
video, and — going forward — every long to automatically spawn a companion tease
short that points viewers back to the long.

Two facts about the current engine make this non-trivial:

1. **One idea = one `produced/<id>/` dir.** Long and short artifacts
   (`script.md`, `metadata.json`, `factcheck.json`, `qc.json`, `video/`) share the
   same paths, so producing a long over an existing short *clobbers* it. You cannot
   hold both formats for one idea on disk.
2. **The overnight automation produces LONGS ONLY.** `run_auto --count 3` runs
   long-form produce + landscape render → `awaiting_approval`. There is no
   companion-short half, and nothing cross-links a short to a long. The "3 long +
   3 short" idea was a backlog plan, never built.

The produced `script.md` for the 5 is the *short* script (~120–170 words). A long
is not a re-render of the same asset — it needs a freshly produced ~1,200-word
long-form script, its own fact-gate pass, its own metadata, and its own ~45-min
render.

## Goal

- Make full long-form videos for the 5 already-published short topics, end-to-end
  (produce → fact-gate → render → upload unlisted), and back-link each existing
  published short to its new long.
- Generalize the engine so every long can spawn a companion tease short that points
  to it, and extend the overnight automation to 3 long + 3 short.

## Non-goals

- Re-rendering or changing the 5 already-published shorts' video pixels. They stay
  as-is; only their YouTube *description* is patched with the long's URL.
- Making anything public. All uploads are unlisted; the user reserves making videos
  public (never pass `--public` without explicit say-so).
- Migrating the 8 legacy flat `produced/<id>/` dirs. New runs use the split; the 5
  get fresh `long/` subdirs.

## Decisions (locked during brainstorming)

- **Full companion automation**, applied to the 5 and built into the overnight job.
- **Companion short = tease derived from the long script** (~130 words) that hooks
  hard and *withholds the payoff*. On-screen EndCTA: **"Full story on our channel —
  link in description."** The long URL never appears in the rendered pixels — it is
  injected into the short's YouTube *description* at upload time.
- **The 5 reuse their already-published shorts** (back-link via description patch);
  no new shorts are rendered for them. Future longs get fresh auto companion shorts.
- **Long uploaded first** → its URL is captured → the short's description is
  cross-linked.
- **Templates unchanged** except the short EndCTA copy. The long template (branding,
  music, sport b-roll) already exists and is untouched.

## Architecture

### Component 1 — Artifact split (`engine/paths.py`, new)

Namespace artifacts by format:

```
produced/<id>/
  long/   script.md  metadata.json  factcheck.json  qc.json  video/video.mp4
  short/  script.md  metadata.json  factcheck.json  qc.json  video/video.mp4
```

A single new module centralizes path construction so the refactor is contained and
testable:

```python
# engine/paths.py
def artifact_dir(idea_id: str, fmt: str) -> str   # produced/<id>/<fmt>/
def script_path(idea_id, fmt) -> str
def metadata_path(idea_id, fmt) -> str
def factcheck_path(idea_id, fmt) -> str
def qc_path(idea_id, fmt) -> str
def video_dir(idea_id, fmt) -> str                # .../<fmt>/video/
```

`fmt` ∈ `{"long", "short"}`. Callers updated: `run_produce.py`, `run_video.py`,
`run_factcheck.py`, `run_auto.py`. `run_video`'s existing `--format
landscape|short` (which sets dimensions) is reconciled so `long`→landscape dims +
`long/` subdir, `short`→vertical dims + `short/` subdir.

No legacy fallback: the new flow always writes/reads under `<fmt>/`. The 5's
pre-existing flat short files are irrelevant to back-linking (we need only the long
URL + the short's YouTube id from the queue).

### Component 2 — Queue model (`engine/queue_manager.py`)

Replace the single `youtube_url` with two explicit fields:

- `long_youtube_url`
- `short_youtube_url`

Migration: for any idea with the legacy `youtube_url`, move it to
`short_youtube_url` (the 5 published uploads are all shorts). Keep reading
`youtube_url` as a fallback alias during transition.

### Component 3 — `update_description` (`engine/publish/uploader.py`)

New capability to patch a live video's description for back-linking:

```python
def update_description(video_id: str, new_description: str) -> None
```

Gotcha: `youtube.videos().update(part="snippet", ...)` requires the **full
snippet** — sending only `description` clears `title`/`categoryId`. So the impl
does `videos().list(part="snippet", id=...)` → mutate `description` → send the whole
snippet back. The existing OAuth token already carries the full
`https://www.googleapis.com/auth/youtube` scope, so no re-auth is needed.

### Component 4 — Cross-link orchestration (`run_auto.py`)

- Upload step sets `long_youtube_url` from the long upload's returned id.
- A back-link op composes the short's description as
  `<short description>\n\n▶ Full story on our channel: <long_youtube_url>` and:
  - **pre-existing short (the 5):** `update_description(short_video_id, ...)`.
  - **new companion short (Phase 2):** sets the description at upload time.

### Component 5 — `derive_short_tease` (`engine/pipeline/script.py`, Phase 2)

```python
def derive_short_tease(long_script: str, idea: dict) -> str
```

Feeds the full long script to the model; returns a ~130-word vertical tease that
hooks hard and withholds the payoff. Short metadata via the existing
`generate_short_metadata`. The short render uses the existing short template with
the EndCTA copy changed to "Full story on our channel — link in description."

## Data flow

**Phase 1 — one long, then the other four (per topic):**
```
run_produce --id <id>            # long script + long metadata -> long/
  -> fact-gate (auto-chained)    # in_production or needs_review
run_video --id <id> --format long --mode narrated --render   # long/video/video.mp4
run_auto --approve <id>          # upload long unlisted -> long_youtube_url
back-link op                     # patch existing short description -> long URL
```

**Phase 2 — overnight 3 long + 3 short:**
```
run_auto --count 3
  per idea: produce long -> fact-gate -> render long
            derive_short_tease(long) -> short metadata -> render short
  -> awaiting_approval
run_auto --approve <id>
  upload long (unlisted) -> long_youtube_url
  upload short (unlisted, description cross-linked to long) -> short_youtube_url
```

## Error handling

- Self-stub / never crash the run (existing convention). A failed companion-short
  derivation must not fail the long.
- Fact-gate stays the hard gate: a `needs_review` long is not uploaded without human
  review.
- `update_description` failure is surfaced (non-zero / logged), never silent — a
  short that fails to back-link is reported so it can be retried.
- Render is never a gate (per CLAUDE.md); proven via still-preview + QC.

## Testing (`pytest tests/`, python3 main env)

- `engine/paths.py` helpers return the expected `<fmt>`-namespaced paths.
- `derive_short_tease` (mocked model): asserts tease length bound and that the
  payoff-withholding prompt shape is sent.
- `update_description` builds a **full-snippet** update body (title + categoryId
  preserved, description replaced) — guards the clobber gotcha.
- Queue migration: legacy `youtube_url` → `short_youtube_url`; both fields readable.
- `run_auto` cross-link composes `▶ Full story...<long_url>` correctly for both the
  patch path and the new-upload path.

## Phasing

- **Phase 1 — the 5 longs.**
  - 1a. Plumbing: split (`paths.py` + refactor), queue fields, `update_description`
    + back-link op.
  - 1b. Produce → fact-gate → render → upload **one** long (start with Senna
    `0c76c4c4`, the approved quality bar) → **user review gate**.
  - 1c. On approval, produce/render/upload the other 4 + back-link all 5 shorts.
- **Phase 2 — overnight companion automation.**
  - `derive_short_tease`, short EndCTA copy, extend `run_auto --count` to make 3
    long + 3 cross-linked companion shorts.

## The 5 topics

| id | topic | existing short URL |
|----|-------|--------------------|
| `0c76c4c4` | Senna / Prost 1984 Monaco | youtu.be/yhClmmEGEHM |
| `46dbfcda` | How America got the World Cup | youtu.be/y0nw8wBn6ok |
| `0eaa1b66` | O.J. Simpson trial | youtu.be/1vrjioS4sls |
| `5b98b1fc` | Barry Sanders retirement | youtu.be/k6dGc65jTJA |
| `a31759e2` | Sachin 2003 World Cup | youtu.be/mB1Gaz5QAGY |
