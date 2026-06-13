# Sport-relevant b-roll — design

**Date:** 2026-06-12
**Status:** approved approach (A), pending spec review
**Scope:** the atmospheric b-roll behind every narrated video (shorts + long-form share the
same footage path). No change to narration, captions, music, or the integrity gate.

## Problem

Chapter background clips feel disconnected from the story — an F1 short shows a random urban
clip, a World Cup short shows something unrelated ("a guy picking trash"). Root cause:
`compose.py:_HEADLINE_SYSTEM` deliberately generates **sport-agnostic, symbolic** VISUAL
queries — its own examples are `"rain on window"`, `"wet street night"`, `"fog over field"`,
`"storm clouds"` — and explicitly bans anything sport-named. Those queries go straight to the
Pexels search (`footage.fetch_clips`), so the footage is atmospheric but never about the sport.

## Goal

Each chapter's b-roll is **anonymous, sport-specific stock footage** tied to the chapter's
moment (F1 → race cars / track / pit lane; soccer → ball, pitch, floodlit stadium; cricket →
pitch, stumps, bat swing), while **never** showing an identifiable real person, team, logo, or
news/archival clip of the actual event (ADR-0005 integrity gate stays intact).

## Architecture (Approach A — sport-aware prompt + search safety net)

Two small, independent changes plus caller wiring.

### 1. `compose.py:_HEADLINE_SYSTEM` (prompt)

Rewrite the VISUAL instruction so the query is **generic-but-sport-specific**, keyed to the
`SPORT` already passed in the prompt *and* the chapter's moment. Replace the "EMPTY PLACE /
never a person / symbolic texture" framing with:

> VISUAL: a 2–4 word stock-video search query showing **anonymous {SPORT} action, equipment,
> venue, or atmosphere** that fits this chapter's moment. Examples — F1: "formula 1 car
> racing", "race track aerial", "pit lane", "rain race spray", "checkered flag"; soccer:
> "soccer ball net", "empty football stadium", "stadium floodlights"; cricket: "cricket pitch",
> "cricket stumps", "cricket bat swing"; basketball: "basketball hoop", "empty basketball
> court". Keep it generic stock — **NEVER** an identifiable real person, named team, logo,
> jersey number, or any news/archival footage of the actual event/people in this story.

The ban on identifiable real people/teams/events is **kept** (just reworded); what changes is
that anonymous sport action and sport venues are now encouraged instead of forbidden.

### 2. `footage.py` (search safety net)

Even with a better prompt, the model can drift to a bare query ("rain spray"). A safety net
keeps Pexels on-sport:

- `_SPORT_KEYWORD: dict[str, str]` — `{"F1": "formula 1", "Soccer": "soccer",
  "NBA": "basketball", "NFL": "american football", "Cricket": "cricket",
  "College": "college sports"}`. Unknown/missing sport → the raw sport string lowercased.
- `_sport_query(query: str, sport: str | None) -> str` — if `sport` is falsy, return `query`
  unchanged. Otherwise resolve the keyword; if it (or the raw sport) is **not already present**
  in the query (case-insensitive substring), prepend it: `"race track aerial"` +
  `F1` → `"formula 1 race track aerial"`. If already present, return unchanged (no
  double-prefixing).
- `fetch_clips(queries, out_dir, api_key=None, portrait=False, sport=None)` — gains a `sport`
  param; maps each query through `_sport_query(q, sport)` before searching. `fetch_clip`
  (singular) is left as-is (only `fetch_clips` is used by the render path).

### 3. Callers pass the sport

- `remotion_build.build_props` (line ~46): `_footage.fetch_clips([...visuals...], video_dir,
  portrait=portrait, sport=idea.get("sport"))`.
- `compose.build` (line ~206, legacy HyperFrames path): same `sport=idea.get("sport")` so both
  render paths benefit.

## Data flow

idea.sport + narration → `build_section_headlines` (sport-aware prompt) → per-chapter
`visual` query → `fetch_clips(..., sport)` → `_sport_query` guarantees the sport keyword →
Pexels search → anonymous sport clip per chapter.

## Error handling

Unchanged self-stub behavior: no `PEXELS_API_KEY`, no eligible clip, or a failed download →
that chapter falls back to the animated gradient (`None`), never crashes. `_sport_query` with
an empty/None sport is a pass-through, so nothing breaks for ideas missing a `sport` field.

## Testing (`python3 -m pytest tests/`, main env)

Unit-test the pure helper `_sport_query` (no network):
- prepends the mapped keyword when absent: `("race track", "F1") → "formula 1 race track"`.
- no-op when the keyword is already present: `("formula 1 pit lane", "F1")` unchanged.
- unknown sport → raw lowercased prefix: `("court", "Pickleball") → "pickleball court"`.
- falsy sport → unchanged: `("race track", None) == "race track"`, `("x", "") == "x"`.
- case-insensitive presence check: `("Formula 1 grid", "F1")` unchanged.

The prompt change is verified by re-rendering Senna (F1) + World Cup (soccer) and eyeballing
that the b-roll is sport-relevant. The 45-min/long render is never a CI gate.

## Out of scope (YAGNI)

Per-chapter clip curation UI, a hand-maintained query bank per sport, multi-clip-per-chapter
montages, real archival footage (ADR-0005 forbids it), and changing the de-dup / portrait
logic. None are needed to make b-roll sport-relevant.
