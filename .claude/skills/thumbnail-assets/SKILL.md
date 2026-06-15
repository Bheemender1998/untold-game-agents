---
name: thumbnail-assets
description: Source the subject photo and composite the thumbnail (and channel banner) for a TUG video. Use when the user says "make the thumbnail", "source a subject for <id>", "thumbnail for <id>", "regenerate the banner", or "/thumbnail-assets".
---

# Thumbnail assets (subject → thumbnail → banner)

> **Auto-generation note:** Thumbnails now **auto-generate on render** — `run_auto` automatically
> chains `run_subject` (Wikipedia → Pexels) + `run_thumbnail` after each successful render. A
> hand-supplied `subject.png` or `thumbnail.jpg` at `produced/<id>/<fmt>/` always wins and is
> never overwritten. This skill is the **manual override / force-regen** path: delete
> `produced/<id>/<fmt>/thumbnail.jpg` to force a regen.

Working dir: `/Users/bheemendergurram/untold_game_agents`. Always `python3`.
Default `--format` is `long`; `short` is the 9:16 vertical variant.

- **Source the subject photo:** `python3 -m engine.run_subject --id <id> [--format short]`
  Wikipedia lead image → Pexels fallback. A hand-dropped
  `produced/<id>/<fmt>/subject.png|jpg` always wins (never overwritten).
- **Composite the thumbnail:** `python3 -m engine.run_thumbnail --id <id> [--format short]`
  Requires a subject photo; builds the "Prestige Feed Killer" cover at
  `produced/<id>/<fmt>/thumbnail.jpg`.
- **Manual override:** drop `subject.png` by hand at `produced/<id>/<fmt>/`, then re-run
  `run_thumbnail`.
- **Channel banner (separate, channel-level):** `python3 -m engine.run_banner`
  → `channel/banner.png` + `channel/description.txt`. Upload the banner as channel art
  and paste the description into "About" in YouTube Studio (manual).

Preconditions / gotchas: `run_thumbnail` exits non-zero if no subject photo exists — run
`run_subject` (or drop one by hand) first. `run_subject` needs `PEXELS_API_KEY` in `.env`
for the stock fallback; without it, only the Wikipedia path works.
