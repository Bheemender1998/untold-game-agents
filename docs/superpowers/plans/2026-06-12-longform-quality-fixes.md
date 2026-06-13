# Long-form Render Quality Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five long-form render quality issues (b-roll looping, year pronunciation/caption display, name pronunciation, chapter-title caption desync, music level) so the other four longs render cleanly.

**Architecture:** Targeted fixes in the existing video pipeline — `tts.py` (year normalization + pronunciation map for the narration text), `captions.py` (number-word→digit collapser on the whisper word list), `run_video.py` (wire both in), `footage.py` (b-roll variety), `music.py` + Remotion TSX (music level + caption-during-title-card layout). No architectural rewrite (full script-aligned captions deferred).

**Tech Stack:** Python 3 (`python3 -m pytest tests/ -q`), Remotion/TypeScript (`engine/video/remotion`), faster-whisper, kokoro TTS, Pexels API.

**Spec:** `docs/superpowers/specs/2026-06-12-longform-quality-fixes-design.md`

**Conventions:** `python3` not `python`; absolute `engine.*` imports; a PostToolUse hook runs `pytest tests/` after each engine edit (intermediate TDD failures are expected). Render is never a gate.

---

### Task 1: Lower music volume (`engine/video/music.py` + TSX fallback)

**Files:**
- Modify: `engine/video/music.py:19`
- Modify: `engine/video/remotion/src/UntoldVideo.tsx:44`
- Test: `tests/test_music.py`

- [ ] **Step 1: Add the failing test** to `tests/test_music.py`:

```python
def test_music_volume_lowered_to_0_08():
    from engine.video import music
    assert music.MUSIC_VOLUME == 0.08
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_music.py::test_music_volume_lowered_to_0_08 -q`
Expected: FAIL (asserts 0.08, value is 0.12)

- [ ] **Step 3: Change the constant** in `engine/video/music.py:19`:

```python
MUSIC_VOLUME = 0.08
```

- [ ] **Step 4: Change the TSX fallback** in `engine/video/remotion/src/UntoldVideo.tsx:44` — replace:

```tsx
              const peak = props.musicVolume ?? 0.12;
```
with:
```tsx
              const peak = props.musicVolume ?? 0.08;
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_music.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add engine/video/music.py engine/video/remotion/src/UntoldVideo.tsx tests/test_music.py
git commit -m "fix(music): lower background music level 0.12 -> 0.08"
```

---

### Task 2: Year/number pronunciation in TTS (`engine/video/tts.py`)

Bare 4-digit years reach espeak and are spoken "nineteen hundred eighty four". Add a year normalizer so the narration says "nineteen eighty-four". Existing comma-grouped handling (`_spell_grouped_numbers`) is kept.

**Files:**
- Modify: `engine/video/tts.py` (add `_year_to_words` + `_spell_years`, call from `script_to_narration_text`)
- Test: `tests/test_tts.py`

- [ ] **Step 1: Add failing tests** to `tests/test_tts.py`:

```python
def test_year_to_words_paired_decades():
    from engine.video import tts
    assert tts._year_to_words(1984) == "nineteen eighty-four"
    assert tts._year_to_words(1973) == "nineteen seventy-three"
    assert tts._year_to_words(1900) == "nineteen hundred"
    assert tts._year_to_words(1905) == "nineteen oh five"
    assert tts._year_to_words(2003) == "two thousand three"
    assert tts._year_to_words(2000) == "two thousand"
    assert tts._year_to_words(2026) == "twenty twenty-six"
    assert tts._year_to_words(2010) == "twenty ten"


def test_script_to_narration_spells_years():
    from engine.video import tts
    out = tts.script_to_narration_text("In 1984 at Monaco, then 2003 and 2026.")
    assert "nineteen eighty-four" in out
    assert "two thousand three" in out
    assert "twenty twenty-six" in out
    assert "1984" not in out


def test_script_to_narration_leaves_non_years_alone():
    from engine.video import tts
    # a 3-digit count and a comma-grouped number are not year-normalized
    out = tts.script_to_narration_text("He ran 400 meters; the crowd was 2,003 strong.")
    assert "400" in out                       # small count untouched by the year pass
    assert "two thousand three" in out        # comma-grouped still spelled (existing behavior)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_tts.py::test_year_to_words_paired_decades -q`
Expected: FAIL (`_year_to_words` not defined)

- [ ] **Step 3: Implement** in `engine/video/tts.py`. Add after `_spell_grouped_numbers` (after line 49):

```python
def _year_to_words(n: int) -> str:
    """Spoken form of a 4-digit year. 1100-1999 → paired decades ('nineteen eighty-four',
    'nineteen hundred', 'nineteen oh five'); 2000-2009 → 'two thousand [n]'; 2010-2099 →
    'twenty [nn]'. Anything else falls back to the cardinal form."""
    if not (1100 <= n <= 2099):
        return _int_to_words(n)
    hi, lo = n // 100, n % 100
    if 2000 <= n <= 2009:
        return "two thousand" + (f" {_ONES[lo]}" if lo else "")
    if lo == 0:
        return _int_to_words(hi) + " hundred"
    if lo < 10:
        return _int_to_words(hi) + f" oh {_ONES[lo]}"
    return _int_to_words(hi) + f" {_int_to_words(lo)}"


def _spell_years(text: str) -> str:
    """Spell standalone 4-digit years (1100-2099) the way people say them, so espeak
    doesn't read '1984' as 'nineteen hundred eighty four'. Skips currency/decimals and
    digits glued to other digits (e.g. '$1,984', '19840')."""
    return re.sub(r"(?<![\d.$,])(1[1-9]\d{2}|20\d{2})(?![\d.])",
                  lambda m: _year_to_words(int(m.group())), text)
```

Then in `script_to_narration_text`, add the year pass right after the grouped-numbers line (line 65):

```python
        s = _spell_grouped_numbers(s)        # '2,003' → 'two thousand three' for clean TTS
        s = _spell_years(s)                  # '1984' → 'nineteen eighty-four' (year form)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_tts.py -q`
Expected: PASS (all, including existing)

- [ ] **Step 5: Commit**

```bash
git add engine/video/tts.py tests/test_tts.py
git commit -m "fix(tts): speak 4-digit years naturally (1984 -> nineteen eighty-four)"
```

---

### Task 3: Pronunciation map for names (`engine/video/tts.py`)

espeak guesses foreign names. Add a seedable map applied to the **narration text only** (NOT the glossary path — `proper_nouns` keeps canonical spellings so captions stay correct).

**Files:**
- Modify: `engine/video/tts.py` (add `_PRONUNCIATION` + `apply_pronunciation`)
- Test: `tests/test_tts.py`

- [ ] **Step 1: Add failing tests** to `tests/test_tts.py`:

```python
def test_apply_pronunciation_respells_known_names():
    from engine.video import tts
    out = tts.apply_pronunciation("Jacky Ickx and Jean-Marie Balestre argued.")
    assert "Ickx" not in out                 # respelled for espeak
    assert tts._PRONUNCIATION["Ickx"] in out


def test_apply_pronunciation_leaves_unmapped_text_untouched():
    from engine.video import tts
    assert tts.apply_pronunciation("Senna led the race.") == "Senna led the race."


def test_apply_pronunciation_is_word_boundary_safe():
    from engine.video import tts
    # a substring match must NOT trigger (e.g. don't rewrite inside another word)
    tts._PRONUNCIATION.setdefault("Lauda", "Lowda")
    out = tts.apply_pronunciation("Laudable Lauda")
    assert "Laudable" in out                  # 'Lauda' inside 'Laudable' untouched
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_tts.py::test_apply_pronunciation_respells_known_names -q`
Expected: FAIL (`_PRONUNCIATION`/`apply_pronunciation` not defined)

- [ ] **Step 3: Implement** in `engine/video/tts.py`. Add near the top after the `_TENS` definitions (after line 26):

```python
# Seedable phonetic respellings applied to the NARRATION TEXT ONLY (not the caption
# glossary), so espeak says tricky names right. Approximate — tune by ear over time.
# Captions keep the canonical spelling (proper_nouns feeds whisper the real names).
_PRONUNCIATION = {
    "Ickx": "Eex",
    "Balestre": "Balestra",
    "Bellof": "Bell-off",
    "Tendulkar": "Ten-dull-car",
    "Sachin": "Suh-chin",
    "Médellín": "Meda-yeen",
    "Medellín": "Meda-yeen",
}
```

And add this function after `_spell_years` (defined in Task 2):

```python
import functools


@functools.lru_cache(maxsize=1)
def _pronunciation_re():
    import re as _re
    if not _PRONUNCIATION:
        return None
    alt = "|".join(_re.escape(k) for k in sorted(_PRONUNCIATION, key=len, reverse=True))
    return _re.compile(rf"\b(?:{alt})\b")


def apply_pronunciation(text: str) -> str:
    """Respell mapped names phonetically for TTS (word-boundary, longest-match-first).
    Applied to the narration text only — the caption glossary keeps canonical names."""
    pat = _pronunciation_re()
    if pat is None:
        return text
    return pat.sub(lambda m: _PRONUNCIATION[m.group(0)], text)
```

> Note: `_pronunciation_re` is `lru_cache`d; the boundary-safe test mutates `_PRONUNCIATION` then calls `apply_pronunciation`. To keep that test honest, clear the cache when seeding in the test — add `tts._pronunciation_re.cache_clear()` after the `setdefault` line in `test_apply_pronunciation_is_word_boundary_safe`.

- [ ] **Step 4: Fix the boundary test to clear the cache** — update `test_apply_pronunciation_is_word_boundary_safe` so it reads:

```python
def test_apply_pronunciation_is_word_boundary_safe():
    from engine.video import tts
    tts._PRONUNCIATION.setdefault("Lauda", "Lowda")
    tts._pronunciation_re.cache_clear()       # map changed → rebuild the regex
    out = tts.apply_pronunciation("Laudable Lauda")
    assert "Laudable" in out
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_tts.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add engine/video/tts.py tests/test_tts.py
git commit -m "fix(tts): seedable pronunciation map for foreign names (narration only)"
```

---

### Task 4: Digit captions — number-word → digit collapser (`engine/video/captions.py`)

Whisper transcribes spoken numbers as words ("nineteen eighty-four"). Collapse recognized runs back to a single digit token (merged timing) so captions show "1984".

**Files:**
- Modify: `engine/video/captions.py` (add `digitize_number_words`)
- Test: `tests/test_captions.py` (create if absent)

- [ ] **Step 1: Add failing tests** in `tests/test_captions.py`:

```python
from engine.video import captions


def _w(word, start, end):
    return {"word": word, "start": start, "end": end}


def test_digitize_collapses_year_words():
    words = [_w("In", 0.0, 0.2), _w("nineteen", 0.2, 0.6), _w("eighty-four", 0.6, 1.1),
             _w("Monaco", 1.1, 1.6)]
    out = captions.digitize_number_words(words)
    assert [w["word"] for w in out] == ["In", "1984", "Monaco"]
    # merged timing spans the whole run
    assert out[1]["start"] == 0.2 and out[1]["end"] == 1.1


def test_digitize_collapses_two_thousand_form():
    words = [_w("by", 0.0, 0.2), _w("two", 0.2, 0.4), _w("thousand", 0.4, 0.8),
             _w("three", 0.8, 1.0)]
    out = captions.digitize_number_words(words)
    assert [w["word"] for w in out] == ["by", "2003"]


def test_digitize_leaves_non_numbers_untouched():
    words = [_w("Senna", 0.0, 0.4), _w("led", 0.4, 0.6)]
    out = captions.digitize_number_words(words)
    assert [w["word"] for w in out] == ["Senna", "led"]


def test_digitize_preserves_trailing_punctuation():
    words = [_w("in", 0.0, 0.2), _w("nineteen", 0.2, 0.6), _w("eighty-four.", 0.6, 1.1)]
    out = captions.digitize_number_words(words)
    assert out[1]["word"] == "1984."
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_captions.py -q`
Expected: FAIL (`digitize_number_words` not defined)

- [ ] **Step 3: Implement** in `engine/video/captions.py`. Add after `chunk_words_to_captions` (after line 92):

```python
# Spoken-number word → value, for collapsing whisper tokens back to digits in captions.
_NUM_UNIT = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_NUM_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
             "seventy": 70, "eighty": 80, "ninety": 90}


def _number_token_value(tok: str):
    """Value of a single lowercased number token, or None. Handles hyphenated tens
    like 'eighty-four' (84) and bare units/tens. 'hundred'/'thousand'/'oh' handled by
    the run parser, not here."""
    tok = tok.strip().lower()
    if tok in _NUM_UNIT:
        return _NUM_UNIT[tok]
    if tok in _NUM_TENS:
        return _NUM_TENS[tok]
    if "-" in tok:
        a, _, b = tok.partition("-")
        if a in _NUM_TENS and b in _NUM_UNIT and 1 <= _NUM_UNIT[b] <= 9:
            return _NUM_TENS[a] + _NUM_UNIT[b]
    return None


def _parse_number_run(toks: list[str]):
    """Parse a run of number tokens into an int, conservatively. Recognizes:
    year pairs ('nineteen eighty-four'→1984, 'nineteen hundred'→1900,
    'nineteen oh five'→1905), 'twenty NN' (→20NN), and 'two thousand [n]' (→200n).
    Returns the int or None if the run isn't a confident match."""
    low = [t.strip().lower() for t in toks]
    # two thousand [unit]
    if len(low) >= 2 and low[0] == "two" and low[1] == "thousand":
        if len(low) == 2:
            return 2000
        if len(low) == 3 and (u := _number_token_value(low[2])) is not None and u < 10:
            return 2000 + u
        return None
    # century pair: <unit/teen> ['hundred' | 'oh' <unit> | <tens-or-tens-unit>]
    head = _number_token_value(low[0])
    if head is not None and 10 <= head <= 20:
        if len(low) == 2 and low[1] == "hundred":
            return head * 100
        if len(low) == 3 and low[1] == "oh" and (u := _number_token_value(low[2])) is not None and u < 10:
            return head * 100 + u
        if len(low) == 2 and (lo := _number_token_value(low[1])) is not None and 10 <= lo <= 99:
            return head * 100 + lo
    return None


def digitize_number_words(words: list[dict]) -> list[dict]:
    """Collapse runs of spoken-number tokens in a whisper word list back into a single
    digit token, merging the run's start/end timing. Conservative — only collapses
    confident year-ish patterns (see _parse_number_run); leaves everything else as-is.
    Input/return shape: [{'word','start','end'}]. Trailing punctuation on the run's last
    token is preserved on the digit token."""
    out: list[dict] = []
    i, n = 0, len(words)
    while i < n:
        # try the longest run (up to 3 tokens) that parses to a number
        matched = False
        for run_len in (3, 2):
            if i + run_len > n:
                continue
            chunk = words[i:i + run_len]
            core = [w["word"].rstrip(".,!?;:") for w in chunk]
            val = _parse_number_run(core)
            if val is not None:
                trail = w_last = chunk[-1]["word"]
                punct = w_last[len(w_last.rstrip(".,!?;:")):]
                out.append({"word": f"{val}{punct}",
                            "start": chunk[0]["start"], "end": chunk[-1]["end"]})
                i += run_len
                matched = True
                break
        if not matched:
            out.append(words[i])
            i += 1
    return out
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_captions.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/video/captions.py tests/test_captions.py
git commit -m "fix(captions): collapse spoken-number words back to digits (1984)"
```

---

### Task 5: Wire pronunciation + digitization into `run_video.py`

**Files:**
- Modify: `engine/run_video.py` (apply `tts.apply_pronunciation` to narration text; `captions.digitize_number_words` to whisper words)

- [ ] **Step 1: Apply pronunciation to the narration text.** In `engine/run_video.py`, find the narration-text construction (around line 83):

```python
            narration_text = tts.script_to_narration_text(script_md)
```
Replace with:
```python
            narration_text = tts.apply_pronunciation(tts.script_to_narration_text(script_md))
```

> The glossary line (`glossary = captions.proper_nouns(tts.script_to_narration_text(script_md))`, ~line 95) is left UNCHANGED — it re-derives from `script_to_narration_text` without pronunciation respelling, so whisper still gets the canonical names.

- [ ] **Step 2: Digitize the whisper words.** In `engine/run_video.py`, right after the line that sets `words` from the transcript (~line 96):

```python
        words = tx["words"] if tx else None           # downstream wants the word list
```
add immediately below:
```python
        if words:
            words = captions.digitize_number_words(words)  # captions show "1984", not words
```

- [ ] **Step 3: Verify the module imports and the suite still passes**

Run: `python3 -c "import engine.run_video"` (expect no error)
Run: `python3 -m pytest tests/ -q` (expect all pass)

- [ ] **Step 4: Commit**

```bash
git add engine/run_video.py
git commit -m "fix(video): apply name pronunciation to narration + digitize caption numbers"
```

---

### Task 6: B-roll variety (`engine/video/footage.py`)

Each chapter should get a distinct clip. Raise the Pexels result pool and stop the dedup fallback from repeating a clip already used **in this video** while distinct candidates remain.

**Files:**
- Modify: `engine/video/footage.py:91` (per_page), `:114-129` (`_fetch_one` fallback)
- Test: `tests/test_footage.py`

- [ ] **Step 1: Add failing test** to `tests/test_footage.py`:

```python
def test_fetch_one_prefers_unused_within_video(monkeypatch):
    from engine.video import footage
    # 3 distinct eligible videos available; first two already used in THIS video
    fake = [{"id": 1, "video_files": [{"file_type": "video/mp4", "link": "a", "width": 1920, "height": 1080}]},
            {"id": 2, "video_files": [{"file_type": "video/mp4", "link": "b", "width": 1920, "height": 1080}]},
            {"id": 3, "video_files": [{"file_type": "video/mp4", "link": "c", "width": 1920, "height": 1080}]}]
    monkeypatch.setattr(footage, "_search", lambda *a, **k: fake)
    monkeypatch.setattr(footage, "_download", lambda link, out: True)
    res = footage._fetch_one("q", "/tmp/x.mp4", "key", 1280, exclude_ids={1, 2})
    assert res is not None and res[1] == 3      # picked the only unused clip, not a repeat


def test_fetch_one_repeats_only_when_no_unused_left(monkeypatch):
    from engine.video import footage
    fake = [{"id": 1, "video_files": [{"file_type": "video/mp4", "link": "a", "width": 1920, "height": 1080}]}]
    monkeypatch.setattr(footage, "_search", lambda *a, **k: fake)
    monkeypatch.setattr(footage, "_download", lambda link, out: True)
    res = footage._fetch_one("q", "/tmp/x.mp4", "key", 1280, exclude_ids={1})
    assert res is not None and res[1] == 1      # nothing unused → allowed to repeat (no blank chapter)
```

- [ ] **Step 2: Run to verify the first fails**

Run: `python3 -m pytest tests/test_footage.py::test_fetch_one_prefers_unused_within_video -q`
Expected: the current code already prefers unused (it filters `exclude_ids`), so this test likely PASSES already. The real defect is pool size + that the fallback is reached too often. Confirm by running; if it passes, keep it as a regression guard. The behavioral fix is Step 3 (bigger pool).

- [ ] **Step 3: Raise the Pexels result pool.** In `engine/video/footage.py:91`, change:

```python
    params = urllib.parse.urlencode({"query": query, "per_page": 12,
                                     "orientation": orientation, "size": "medium"})
```
to:
```python
    params = urllib.parse.urlencode({"query": query, "per_page": 40,
                                     "orientation": orientation, "size": "medium"})
```

- [ ] **Step 4: Make the fallback try a broader query before repeating.** In `_fetch_one` (lines 114-129), replace the body so that, when every search result is already excluded, it retries once with the bare (non-sport-prefixed words dropped is not possible here, so) — instead, only repeat as a LAST resort and prefer any not-yet-excluded clip. Replace lines 118-124:

```python
    videos = _search(query, api_key, portrait=portrait)
    eligible = [v for v in videos if v.get("id") not in exclude_ids
                and _best_file(v, min_width, portrait=portrait)]
    if not eligible:   # everything seen already → allow a repeat rather than a blank chapter
        eligible = [v for v in videos if _best_file(v, min_width, portrait=portrait)]
    if not eligible:
        return None
```
with:
```python
    videos = _search(query, api_key, portrait=portrait)
    eligible = [v for v in videos if v.get("id") not in exclude_ids
                and _best_file(v, min_width, portrait=portrait)]
    if not eligible:
        # No unused clip for this query. Try a broader query (drop the first word, which is
        # usually the sport keyword or an adjective) to widen the pool before repeating.
        broader = query.split(" ", 1)[1] if " " in query else query
        if broader != query:
            videos = _search(broader, api_key, portrait=portrait)
            eligible = [v for v in videos if v.get("id") not in exclude_ids
                        and _best_file(v, min_width, portrait=portrait)]
    if not eligible:   # genuinely nothing unused → allow a repeat rather than a blank chapter
        eligible = [v for v in videos if _best_file(v, min_width, portrait=portrait)]
    if not eligible:
        return None
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_footage.py -q`
Expected: PASS (both new tests + existing)

- [ ] **Step 6: Commit**

```bash
git add engine/video/footage.py tests/test_footage.py
git commit -m "fix(footage): larger Pexels pool + broaden-before-repeat so chapters get distinct b-roll"
```

---

### Task 7: Captions visible during title cards (Remotion)

Stop suppressing captions during the 3.6 s title-card window and anchor captions to the lower area so the upper title card never collides with them.

**Files:**
- Modify: `engine/video/remotion/src/components/Captions.tsx`
- Modify: `engine/video/remotion/src/UntoldVideo.tsx` (drop the now-unused `chapterStartsMs` prop pass)

- [ ] **Step 1: Remove the suppression + anchor captions lower** in `Captions.tsx`.

(a) Delete the suppression constant + logic. Remove these lines:
```tsx
const CHAPTER_HEADLINE_MS = 3600;
```
and (inside the component):
```tsx
  // Hold for the chapter headline: don't draw captions while a title card is on screen.
  const inHeadline = chapterStartsMs.some(
    (s) => nowMs >= s && nowMs < s + CHAPTER_HEADLINE_MS,
  );
```

(b) Change the component signature to drop `chapterStartsMs` — replace:
```tsx
export const Captions: React.FC<{captions: CaptionWord[]; chapterStartsMs?: number[]}> = ({
  captions,
  chapterStartsMs = [],
}) => {
```
with:
```tsx
export const Captions: React.FC<{captions: CaptionWord[]}> = ({captions}) => {
```

(c) Change the page guard — replace:
```tsx
  const page = pages.find((p) => nowMs >= p.startMs && nowMs < p.startMs + p.durationMs);
  if (!page || inHeadline) return null;
```
with:
```tsx
  const page = pages.find((p) => nowMs >= p.startMs && nowMs < p.startMs + p.durationMs);
  if (!page) return null;
```

(d) Anchor the caption block to the lower third so it never overlaps the top title card — change the outer `AbsoluteFill` style:
```tsx
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: '0 120px'}}>
```
to:
```tsx
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', padding: '0 120px 160px'}}>
```

- [ ] **Step 2: Drop the unused prop in `UntoldVideo.tsx`** — replace:
```tsx
        <Captions
          captions={props.captions}
          chapterStartsMs={props.chapters.map((c) => c.startMs)}
        />
```
with:
```tsx
        <Captions captions={props.captions} />
```

- [ ] **Step 3: Type-check the Remotion project**

Run: `cd engine/video/remotion && npx tsc --noEmit` (expect no type errors; if deps missing, run `npm install` first)
Expected: clean compile (the `chapterStartsMs` removal is consistent across both files).

- [ ] **Step 4: (Best-effort) eyeball the layout with a still**

If the Remotion deps are installed and a props file exists, render one still at a chapter-start frame to confirm the title card (upper) and captions (lower) don't overlap:

```bash
cd engine/video/remotion && npx remotion still src/index.ts UntoldVideo /tmp/chk.png \
  --props=../../../produced/0c76c4c4/long/video/props.json --frame=900 || true
```
Open `/tmp/chk.png`. This is a verification aid, not a gate — skip if deps aren't set up.

- [ ] **Step 5: Commit**

```bash
git add engine/video/remotion/src/components/Captions.tsx engine/video/remotion/src/UntoldVideo.tsx
git commit -m "fix(captions): show captions during title cards; anchor captions to lower third"
```

---

## Self-Review

**Spec coverage:**
- Bug 1 b-roll variety → Task 6. ✅
- Bug 2 years (audio) → Task 2; (caption digits) → Task 4; wired → Task 5. ✅
- Bug 3 names (narration-only pronunciation, glossary canonical) → Task 3; wired → Task 5. ✅
- Bug 4 caption sync (show during card, card upper / captions lower) → Task 7. ✅
- Bug 5 music level → Task 1. ✅
- Deferred items (script-aligned captions, Senna re-render) → not in plan, by design. ✅

**Placeholder scan:** every code step has full code; commands have expected output; no TBD/TODO. ✅

**Type/name consistency:** `_year_to_words`/`_spell_years` (Task 2) referenced consistently; `apply_pronunciation`/`_PRONUNCIATION`/`_pronunciation_re` (Task 3) consistent and cache-cleared in the mutating test; `digitize_number_words` shape `{word,start,end}` matches `chunk_words_to_captions`/`build_props` consumers and the run_video wiring (Task 5); `Captions` prop change (drop `chapterStartsMs`) applied in both Captions.tsx and UntoldVideo.tsx (Task 7). ✅

## After this plan ships (resumes the Phase-1 runbook on the fixed template)
Produce → fact-review → render → upload (unlisted) the four longs, then back-link the five shorts:
World Cup `46dbfcda` · O.J. `0eaa1b66` · Barry `5b98b1fc` · Sachin `a31759e2`.
(Senna `0c76c4c4` long already shipped as-is; its short can be back-linked once its long URL is confirmed.)
