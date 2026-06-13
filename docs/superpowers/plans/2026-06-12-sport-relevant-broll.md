# Sport-relevant B-roll Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every chapter's background clip sport-relevant (F1 → racing, soccer → pitch) instead of random symbolic stock, while keeping the ADR-0005 ban on identifiable real people/teams/events.

**Architecture:** A sport-aware VISUAL prompt in `compose._HEADLINE_SYSTEM` generates sport-specific queries; a pure `footage._sport_query` safety net prepends the sport keyword to any query that omits it; `build_props` and `compose.build` pass `idea["sport"]` into `fetch_clips`.

**Tech Stack:** Python 3 stdlib, pytest (main env), Pexels stock-video API (existing).

**Reference spec:** `docs/superpowers/specs/2026-06-12-sport-relevant-broll-design.md`

**Conventions:** `python3` not `python`; absolute `engine.*` imports; `python3 -m pytest tests/ -q`; self-stub on missing data; branch `feat/shorts-mood-music` (current).

---

## File Structure

- **Modify** `engine/video/footage.py` — add `_SPORT_KEYWORD` map + pure `_sport_query` helper; `fetch_clips` gains a `sport` param and maps each query through it.
- **Modify** `engine/video/remotion_build.py` — `build_props` passes `sport=idea.get("sport")` into `fetch_clips`.
- **Modify** `engine/video/compose.py` — legacy `build` passes `sport=idea.get("sport")`; rewrite `_HEADLINE_SYSTEM` VISUAL guidance to be sport-relevant.
- **Create** `tests/test_footage.py` additions — unit-test `_sport_query`.

---

## Task 1: `_sport_query` helper + sport keyword map

**Files:**
- Modify: `engine/video/footage.py`
- Test: `tests/test_footage.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_footage.py
from engine.video import footage


def test_sport_query_prepends_missing_keyword():
    assert footage._sport_query("race track aerial", "F1") == "formula 1 race track aerial"
    assert footage._sport_query("ball net", "Soccer") == "soccer ball net"


def test_sport_query_noop_when_keyword_present():
    assert footage._sport_query("formula 1 pit lane", "F1") == "formula 1 pit lane"
    assert footage._sport_query("Formula 1 grid", "F1") == "Formula 1 grid"  # case-insensitive


def test_sport_query_unknown_sport_uses_raw_lowercased():
    assert footage._sport_query("court", "Pickleball") == "pickleball court"


def test_sport_query_falsy_sport_unchanged():
    assert footage._sport_query("race track", None) == "race track"
    assert footage._sport_query("race track", "") == "race track"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_footage.py -k sport_query -v`
Expected: FAIL — `AttributeError: module 'engine.video.footage' has no attribute '_sport_query'`

- [ ] **Step 3: Write minimal implementation**

Add near the top of `engine/video/footage.py` (after the imports / module constants):

```python
_SPORT_KEYWORD = {
    "F1": "formula 1",
    "Soccer": "soccer",
    "NBA": "basketball",
    "NFL": "american football",
    "Cricket": "cricket",
    "College": "college sports",
}


def _sport_query(query: str, sport: str | None) -> str:
    """Keep a stock-video query on-sport: prepend the sport keyword unless the query
    already mentions it. Falsy sport → query unchanged (self-stub)."""
    if not sport:
        return query
    keyword = _SPORT_KEYWORD.get(sport, sport.lower())
    low = query.lower()
    if keyword in low or sport.lower() in low:
        return query
    return f"{keyword} {query}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_footage.py -k sport_query -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/video/footage.py tests/test_footage.py
git commit -m "feat(footage): _sport_query keeps b-roll queries on-sport"
```

---

## Task 2: Thread `sport` through `fetch_clips`

**Files:**
- Modify: `engine/video/footage.py` (`fetch_clips`)

- [ ] **Step 1: Make the change**

In `engine/video/footage.py`, change `fetch_clips`'s signature and apply `_sport_query`:

```python
def fetch_clips(queries: list[str], out_dir: str, api_key: str | None = None,
                portrait: bool = False, sport: str | None = None) -> list[str | None]:
    """One clip per query (chapter), in order. Each pick is random and de-duplicated
    against everything used before (across videos) AND within this batch. Each query is
    biased toward `sport` so the b-roll stays on-sport. Missing/failed → None."""
    os.makedirs(out_dir, exist_ok=True)
    api_key = api_key or os.environ.get("PEXELS_API_KEY")
    used = _load_used()
    batch = set(used)   # also avoid repeating a clip within this same video
    out = []
    for i, q in enumerate(queries):
        sq = _sport_query(q, sport)
        res = _fetch_one(sq, os.path.join(out_dir, f"bg_{i:02d}.mp4"), api_key, 1280, batch,
                         portrait=portrait) if api_key else None
        if res:
            out.append(res[0])
            if res[1] is not None:
                batch.add(res[1]); used.add(res[1])
        else:
            out.append(None)
    _save_used(used)
    return out
```

- [ ] **Step 2: Run the suite (no regressions)**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (existing footage tests still green; `fetch_clips` callers without `sport` still work — default None).

- [ ] **Step 3: Commit**

```bash
git add engine/video/footage.py
git commit -m "feat(footage): fetch_clips biases each query toward the sport"
```

---

## Task 3: Callers pass `idea["sport"]`

**Files:**
- Modify: `engine/video/remotion_build.py` (the `_footage.fetch_clips(...)` call, ~line 46)
- Modify: `engine/video/compose.py` (the `_footage.fetch_clips(...)` call, ~line 206)

- [ ] **Step 1: Make the changes**

In `engine/video/remotion_build.py`, the existing call is:

```python
    clips = _footage.fetch_clips([s.get("visual", "") for s in sections], video_dir,
                                 portrait=portrait)
```

Change it to:

```python
    clips = _footage.fetch_clips([s.get("visual", "") for s in sections], video_dir,
                                 portrait=portrait, sport=idea.get("sport"))
```

In `engine/video/compose.py` (~line 206), the existing call is:

```python
    clips = _footage.fetch_clips([s.get("visual", "") for s in sections], out_dir)
```

Change it to:

```python
    clips = _footage.fetch_clips([s.get("visual", "") for s in sections], out_dir,
                                 sport=idea.get("sport"))
```

- [ ] **Step 2: Run the suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add engine/video/remotion_build.py engine/video/compose.py
git commit -m "feat(footage): pass the idea's sport into b-roll selection"
```

---

## Task 4: Sport-aware VISUAL prompt

**Files:**
- Modify: `engine/video/compose.py` (`_HEADLINE_SYSTEM`, ~lines 233-245)

- [ ] **Step 1: Replace the VISUAL guidance**

In `engine/video/compose.py`, replace the VISUAL paragraph of `_HEADLINE_SYSTEM` (the
"EMPTY PLACE / never a person / symbolic" block) with:

```python
- VISUAL: a 2-4 word stock-video search query showing ANONYMOUS {SPORT} action, equipment,
  venue, or atmosphere that fits this chapter's moment. Examples — F1: "formula 1 car racing",
  "race track aerial", "pit lane", "rain race spray", "checkered flag"; soccer: "soccer ball
  net", "empty football stadium", "stadium floodlights"; cricket: "cricket pitch", "cricket
  stumps", "cricket bat swing"; basketball: "basketball hoop", "empty basketball court".
  Keep it GENERIC stock footage — NEVER an identifiable real person, named team, logo, jersey
  number, or any news/archival clip of the actual event or people in this story. When unsure,
  use a generic sport venue or equipment shot.
```

(Leave the HEADLINE and ANCHOR bullets unchanged; keep "Keep chapters in order. 6-12 chapters.")

- [ ] **Step 2: Sanity-check the module imports + prompt string**

Run: `python3 -c "from engine.video import compose; assert 'ANONYMOUS' in compose._HEADLINE_SYSTEM and 'never an identifiable real person'.lower() in compose._HEADLINE_SYSTEM.lower(); print('prompt ok')"`
Expected: `prompt ok`

- [ ] **Step 3: Run the suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add engine/video/compose.py
git commit -m "feat(footage): sport-relevant VISUAL prompt for chapter b-roll"
```

---

## Task 5: Re-render all 5 shorts (sport b-roll + music)

**Files:** none (render).

- [ ] **Step 1: Re-render every short via the render venv**

Run (background, sequential to avoid M2 thrash):

```bash
for id in 0eaa1b66 5b98b1fc a31759e2 0c76c4c4 46dbfcda; do
  .venv-video/bin/python -m engine.run_video --id $id --mode narrated --format short --render
done
```

Expected: each completes; `produced/<id>/video/props.json` chapters' `bClip` are now sport-biased, and every short has `musicSrc` set (library exists now).

- [ ] **Step 2: Verify b-roll queries went sport-aware**

Run: `python3 -c "import json; d=json.load(open('produced/0c76c4c4/video/props.json')); print([c.get('headline') for c in d['chapters']]); print('music:', d.get('musicSrc'))"`
Expected: chapters present; `music` set. (Spot-check the rendered Senna/World Cup by eye for racing/soccer footage.)

- [ ] **Step 3: Full suite green**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

---

## Self-Review Notes

- **Spec coverage:** prompt → Task 4; `_sport_query` + map → Task 1; `fetch_clips` sport param → Task 2; caller wiring → Task 3; tests → Task 1; render verification → Task 5. All spec sections covered.
- **Type consistency:** `_sport_query(query, sport)` and `fetch_clips(..., sport=None)` signatures match across tasks; callers pass `idea.get("sport")`.
- **Self-stub preserved:** falsy sport → query unchanged; no key / no clip → gradient fallback (unchanged).
- **Integrity gate:** prompt keeps the explicit ban on identifiable real people/teams/logos/archival.
