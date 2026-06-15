# Auto-chain thumbnail generation into the render pipeline

**Date:** 2026-06-15
**Status:** Design — approved for planning
**Branch (planned):** `feat/auto-thumbnail-render`

## Problem

Thumbnail generation is a manual, separate workflow (`run_subject` → `run_thumbnail`,
wrapped by the `thumbnail-assets` skill). It is **not** chained into the
produce → render → QC pipeline. The only place a thumbnail is touched is at upload
time (`run_auto.py`), where the approve path does:

```python
thumb = paths.thumbnail_path(idea_id, "long")
thumb = thumb if os.path.exists(thumb) else None   # silently None if missing
uploader.upload(..., thumbnail_path=thumb)
```

If no `thumbnail.jpg` exists, the video uploads with YouTube's default auto-grabbed
frame — silently. This has already shipped several published videos with default
thumbnails.

## Goal

Every idea that completes a render reaches `awaiting_approval` with a composited
`thumbnail.jpg` already present (when a subject photo can be sourced), without a
manual step — and if a thumbnail is still missing at approve time, the upload warns
loudly instead of shipping a default frame silently.

## Constraints

- **Two-venv split is load-bearing.** `run_subject`/`run_thumbnail` run under main
  `python3` (PIL + network). `run_video --render` runs under `.venv-video`. The
  chaining must therefore live in the **orchestration layer** (`run_auto`, main env),
  never inside `run_video`. `run_auto` already imports main-env pipeline modules
  in-process (e.g. `_produce_companion` imports `run_produce`; `_render_and_qc`
  imports `engine.pipeline.chapters`), so calling `engine.pipeline.subject` and
  `engine.pipeline.thumbnail` in-process is the established pattern — no subprocess
  shell-out needed.
- **A stage must never crash the run** (self-stub convention).
- **Smallest sufficient change** — touch only `run_auto.py` (+ a test). Do not
  refactor the thumbnail/subject pipeline modules or fix the unrelated
  script-content-loading behavior; the chain inherits `generate_thumbnail`'s
  existing text logic verbatim, exactly as the `run_thumbnail` entrypoint does.

## Design

### New helper: `_ensure_thumbnail(idea_id, fmt)` in `run_auto.py`

A self-stubbing helper that guarantees a thumbnail exists for a rendered format,
mirroring the `run_thumbnail` entrypoint's call shape but never raising:

```python
def _ensure_thumbnail(idea_id: str, fmt: str) -> None:
    """Best-effort: ensure produced/<id>/<fmt>/thumbnail.jpg exists after a render.
    Skips if a thumbnail already exists (never clobbers hand-work). Self-stubs on
    any failure — a missing thumbnail must never break the render/QC pipeline."""
    try:
        thumb = paths.thumbnail_path(idea_id, fmt)
        if os.path.exists(thumb):
            print(f"· {idea_id}/{fmt}: thumbnail exists — skipping auto-generation")
            return
        idea = q.get_by_id(idea_id) or {"id": idea_id}
        res = subject.source_subject(idea, fmt)        # Wikipedia → Pexels; human subject wins
        if not res.get("source"):
            print(f"⚠ {idea_id}/{fmt}: no subject photo found — thumbnail skipped "
                  f"(hand-source before approving)")
            return
        thumbnail.generate_thumbnail(idea, fmt)
        print(f"✓ {idea_id}/{fmt}: thumbnail composited via {res['source']}")
    except Exception as e:                              # never break the render/batch
        print(f"⚠ {idea_id}/{fmt}: thumbnail auto-generation failed — {e}")
```

Imports added at module top: `from engine.pipeline import subject, thumbnail`.

### Behavior decisions (locked)

- **Trigger point (Q1=A):** fires inside the orchestration layer after a *successful*
  render — one chokepoint per format. The long fires from `_render_and_qc`; the short
  fires from `_companion_short`. This covers the overnight `pipeline()`, the manual
  `cmd_render` override path (both route through `_render_and_qc`), and the companion
  short.
- **No-photo handling (Q2=A):** self-stub + warn. The render still succeeds and the
  idea still reaches `awaiting_approval`; it simply lands without a thumbnail. No new
  status, no hard gate.
- **Existing thumbnail (Q3=A):** skip generation entirely if a thumbnail file already
  exists — never clobber a hand-composited thumbnail. To force a regen, delete the
  file or run `run_thumbnail` by hand. Subject sourcing stays "human subject wins" as
  today (unchanged `source_subject` semantics).

### Wiring

**`_render_and_qc`** (long) — call after a successful render, before QC (order is
independent of QC):

```python
if not _render_one(idea_id):
    print(f"· {idea_id}: render_failed")
    return
_ensure_thumbnail(idea_id, _OVERNIGHT_FMT)   # NEW
# ... chapter sync, qc, awaiting_approval (unchanged) ...
```

**`_companion_short`** (short) — call after the short render+QC pass, before/around
setting `short_awaiting_approval`:

```python
report = qc.qc_video(idea_id, "short")
if report["passed"]:
    _ensure_thumbnail(idea_id, "short")      # NEW
    q.update_idea(idea_id, short_status="short_awaiting_approval", ...)
```

### Upload-time soft guard (backstop)

In the approve/upload path, when the resolved thumbnail is `None`, print a loud
non-blocking warning before uploading — for both the long and the companion short:

```python
thumb = paths.thumbnail_path(idea_id, "long")
if not os.path.exists(thumb):
    print(f"⚠ {idea_id}: no custom thumbnail — uploading with YouTube's default frame")
    thumb = None
```

(Same shape for the `sthumb` short path.) This is a **warning, not a block** — it never
prevents an approved upload; it just ensures a missing thumbnail is never silent.

## Out of scope (YAGNI)

- No hard gate / `needs_review` on missing thumbnails (rejected Q2=B).
- No regeneration of existing thumbnails (rejected Q3=B).
- No change to `subject.py` / `thumbnail.py` internals, and no fix to the known
  script-content-loading behavior in `generate_thumbnail` (separate issue; the chain
  inherits whatever the manual entrypoint produces today).
- No change to `run_video`, the QC gate, or the preflight lint.

## Testing

Unit tests in `tests/` against `_ensure_thumbnail`, mocking
`engine.pipeline.subject.source_subject` and `engine.pipeline.thumbnail.generate_thumbnail`:

1. **Skip-when-exists:** thumbnail file already present → neither `source_subject` nor
   `generate_thumbnail` is called.
2. **Happy path:** no thumbnail, `source_subject` returns a source → `generate_thumbnail`
   called once.
3. **No-photo self-stub:** `source_subject` returns `{"source": None, ...}` →
   `generate_thumbnail` NOT called, no exception, function returns normally.
4. **Exception self-stub:** `generate_thumbnail` raises → `_ensure_thumbnail` swallows
   it and returns (does not propagate).

Plus the existing `run_auto` orchestration tests must still pass (the hook runs
`python3 -m pytest tests/ -q`).

## Docs to update (same PR)

- `CLAUDE.md` pipeline-layout line: note thumbnails are now auto-chained on render
  (no longer a purely manual step).
- `thumbnail-assets` skill: note it's now a manual override / force-regen path, since
  the render auto-generates by default.

## Rollout

Engine change → ships via the `ship-video-change` rail (branch, pytest, dual
adversarial review, PR with `Adversarial-Reviewed:` trailer, squash-merge).
