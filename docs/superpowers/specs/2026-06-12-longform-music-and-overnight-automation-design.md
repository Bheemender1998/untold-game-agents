# Phase 1 — Long-form music + overnight automation — design

**Date:** 2026-06-12
**Status:** approved, pending spec review
**Scope:** (1) extend the mood-matched music bed to long-form renders; (2) schedule a nightly
1 AM local job that produces + renders **3 long-form videos** for morning review. Companion
shorts and long-versions-of-the-5-published are **Phase 2** (need per-format artifact
separation) and are out of scope here.

## Part 1 — Music on long-form

Today music is shorts-only: `remotion_build.build_props` only calls `music.short_music_props`
under `if portrait:`, and `UntoldVideo.tsx` has no music `<Audio>`. Two changes:

### 1a. Mood for long-form — `engine/video/music.py`

Long-form ideas have no per-script `mood`; derive it from the pillar (same mapping the voice
uses). Rename the intent by adding a fallback inside `short_music_props` (keep the name; it now
serves both formats):

```python
def short_music_props(idea, music_dir=None):
    ...
    from engine.video import tts
    mood = idea.get("mood") or tts.mood_for_pillar(idea.get("pillar"))
    chosen = pick_track(mood, idea.get("id", ""), music_dir)
    ...
```

### 1b. build_props wires music for both formats — `engine/video/remotion_build.py`

Drop the `if portrait:` gate — always attempt the bed (mood fallback handles long-form). The
empty-mood / empty-folder cases already self-stub to no music.

### 1c. Music `<Audio>` in `UntoldVideo.tsx`

Add the same looped, faded background `<Audio>` the Short uses, inside the narration Sequence,
gated on `props.musicSrc`. Fade spans the full composition (intro+narration+outro) so it carries
under the intro card and the end CTA. Volume `props.musicVolume ?? 0.12`. The existing impact
SFX layer is untouched.

### 1d. Credit — unchanged

`run_video` already calls `music.write_credit` after any successful render (short or long), so
long-form descriptions get the `Music: …` line automatically once 1a–1c land.

## Part 2 — Overnight automation (3 long videos, 1 AM nightly)

Use the **existing, proven** Stage-B orchestrator — no new pipeline. `run_auto pipeline`
already does, per idea: produce (long-form) → render via `.venv-video` → QC →
`awaiting_approval`, never aborting the batch on one failure, and fires a macOS notification at
the end (`_notify`). `_select(count)` takes the top-`count` pending ideas (the queue is score-
ordered), which satisfies "top 3 pending by score."

### 2a. launchd job (local, M2)

A `LaunchAgent` plist at `~/Library/LaunchAgents/com.untoldgame.overnight.plist` runs nightly at
**01:00**:

- `ProgramArguments`: a small committed wrapper `scripts/overnight.sh` that `cd`s to the repo,
  sources the env (`.env` for the Anthropic key, `PEXELS_API_KEY`), and runs
  `python3 -m engine.run_auto --count 3`.
- `StartCalendarInterval`: `{Hour: 1, Minute: 0}`.
- `StandardOutPath` / `StandardErrorPath`: `logs/overnight.log` (committed `.gitignore` for the
  log) so a failed night is debuggable in the morning.
- Loaded with `launchctl load -w <plist>`.

`run_auto` already shells produce under `python3` and render under `.venv-video` (the two venvs
can't coexist in one process), so the wrapper only needs the main `python3`.

### 2b. Wrapper script `scripts/overnight.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
exec python3 -m engine.run_auto --count 3
```

Committed + `chmod +x`. The plist references its absolute path.

### 2c. Morning artifacts

By ~morning: 3 ideas at `awaiting_approval` with `produced/<id>/video/video.mp4` + metadata, a
macOS notification ("3 produced: 3 awaiting_approval"), and `logs/overnight.log`. The user
reviews via `run_auto --list`, watches the mp4s, then `run_auto --approve <id>` (unlisted) per
their existing flow.

## Error handling

- A produce/render failure marks that idea `render_failed`/`qc_failed` and the batch continues
  (existing behavior) — a bad night never blocks the others.
- Missing env/key → `run_auto` self-stubs per stage; the log captures it.
- Music: empty mood/folder → silent render (unchanged self-stub).

## Testing

- **Python:** `short_music_props` derives the pillar mood when `idea["mood"]` is empty
  (monkeypatch `tts.mood_for_pillar`); `build_props` returns `musicSrc` for a **long-form**
  (`portrait=False`) idea with a mood-bearing pillar, and still none when no track.
- **Remotion:** `tsc --noEmit`; render one long-form (or a short still) to confirm the bundle
  compiles with the new `<Audio>`.
- **Automation:** `bash -n scripts/overnight.sh` (syntax); `plutil -lint` the plist; a manual
  `python3 -m engine.run_auto --count 1 --no-render` dry pass to confirm the wrapper path/env
  resolve. The real 3-video run is verified by the morning artifacts, not in-session.

## Out of scope (YAGNI — Phase 2)

Companion shorts referencing longs, long versions of the 5 published shorts, per-format artifact
separation (`produced/<id>/long|short/`), idea-generation-before-batch, and Railway scheduling
(render must be local).
