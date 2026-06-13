# Front-loaded Hooks + Withholding Titles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Front-load the mystery in every hook and open titles by withholding (not editorializing), add a dedicated Short-title pass, and guard generated Short titles against fabricated numbers — all as prompt + small-code changes, no render.

**Architecture:** Pure edits to the text-generation layer. One integrity rule ("mystery-first hook; exact-or-no specifics") is stated in three script system prompts and the title prompts. A new `_short_title_llm` pass replaces the verbatim long-title reuse for Shorts, guarded by a deterministic digit-containment backstop (`title_numbers_within`) that self-stubs to `title_variants[0]`. Regression tests assert the rule text physically survives in each prompt. No orchestration changes — existing `run_produce --metadata-only` retitles the queue.

**Tech Stack:** Python 3 (main env, `python3 -m pytest`), Anthropic SDK structured outputs (raw `output_config.format` on `messages.create`), existing `BaseAgent`.

Spec: `docs/superpowers/specs/2026-06-13-frontloaded-hooks-withholding-titles-design.md`

---

## File Structure

- `engine/pipeline/script.py` — add the hook rule to `SHORT_SYSTEM`, `DERIVE_TEASE_SYSTEM`, `SCRIPT_SYSTEM`; add `_norm_num` + `title_numbers_within` (next to `tease_within_long`).
- `engine/pipeline/metadata.py` — add the title rule to `METADATA_SYSTEM`; add `_SHORT_TITLE_SYSTEM`, `_SHORT_TITLE_SCHEMA`, `_short_title_llm`, `_short_title`; wire `_short_title` into `generate_short_metadata`.
- `tests/test_script.py` — regression tests for the hook rule; unit tests for `title_numbers_within`.
- `tests/test_metadata.py` — regression test for the title rule; tests for the Short-title pass + backstop; patch existing tests so the new title pass is deterministic and network-free.

Stable regression anchors (assert these exact substrings survive):
- Hook rule → `"front-load the mystery"` (in all three script prompts).
- Title rule → `"Open the gap by withholding"` (in `METADATA_SYSTEM` and `_SHORT_TITLE_SYSTEM`).

---

## Task 1: Hook rule into the three script system prompts

**Files:**
- Modify: `engine/pipeline/script.py` (`SHORT_SYSTEM`, `DERIVE_TEASE_SYSTEM`, `SCRIPT_SYSTEM`)
- Test: `tests/test_script.py`

- [ ] **Step 1: Write the failing regression test**

Add to `tests/test_script.py`:

```python
def test_hook_rule_present_in_all_hook_prompts():
    # Regression firewall: the mystery-first hook rule must survive future prompt edits.
    from engine.pipeline import script
    for prompt in (script.SHORT_SYSTEM, script.DERIVE_TEASE_SYSTEM, script.SCRIPT_SYSTEM):
        assert "front-load the mystery" in prompt
        assert "exact verified value" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_script.py::test_hook_rule_present_in_all_hook_prompts -v`
Expected: FAIL with `AssertionError` (text not yet in the prompts).

- [ ] **Step 3: Edit `SHORT_SYSTEM` HOOK beat**

In `engine/pipeline/script.py`, replace the HOOK bullet inside `SHORT_SYSTEM`:

Find:
```python
- HOOK: the very first sentence is a scroll-stopping line that lands the stakes in under two
  seconds. No throat-clearing, no "in this video".
```
Replace with:
```python
- HOOK: front-load the mystery, not the data. The strongest hook carries NO specific number,
  name, or date — open on the emotional stakes and the unanswered question ("He was one season
  from immortality. Then he walked away."), and let specifics land in the FACT beat. This
  mystery-first hook is the GOAL, not a safe fallback — it is the scroll-stopper. If a specific
  DOES survive into the hook it must be the exact verified value: never round (1,457, never
  ~1,500), never assert a superlative as fact ("the greatest ... in history"). No throat-clearing,
  no "in this video".
```

- [ ] **Step 4: Edit `DERIVE_TEASE_SYSTEM` HOOK beat**

Find:
```python
- HOOK: a scroll-stopping first line that lands the stakes in under two seconds.
```
Replace with:
```python
- HOOK: front-load the mystery, not the data — a scroll-stopping first line that carries NO
  specific number, name, or date, opening on the stakes and the unanswered question; specifics
  land in the FACT beat. This mystery-first hook is the GOAL, not a fallback. If a specific does
  survive into the hook it must be the exact verified value: never round, never assert a
  superlative as fact.
```

- [ ] **Step 5: Edit `SCRIPT_SYSTEM` cold-open bullet**

Find:
```python
- Open with a COLD OPEN — the hook, in-scene, no throat-clearing. Earn the click in 15 seconds.
```
Replace with (note the lowercase `front-load the mystery` — the regression test in Step 1 matches that exact substring):
```python
- Open with a COLD OPEN — the hook, in-scene, no throat-clearing. Earn the click in 15 seconds —
  front-load the mystery, not the data: the strongest cold open carries no specific number, name,
  or date — lead with the stakes and the unanswered question, and let specifics land after. If a
  specific does survive into the opening line it must be the exact verified value: never round,
  never assert a superlative as fact.
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_script.py::test_hook_rule_present_in_all_hook_prompts -v`
Expected: PASS.

- [ ] **Step 7: Run the full script test file (no regressions)**

Run: `python3 -m pytest tests/test_script.py -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add engine/pipeline/script.py tests/test_script.py
git commit -m "feat(packaging): front-load the mystery in hook prompts (short, tease, long)"
```

---

## Task 2: Title rule into `METADATA_SYSTEM`

**Files:**
- Modify: `engine/pipeline/metadata.py` (`METADATA_SYSTEM`)
- Test: `tests/test_metadata.py`

- [ ] **Step 1: Write the failing regression test**

Add to `tests/test_metadata.py`:

```python
def test_title_rule_present_in_metadata_system():
    from engine.pipeline import metadata
    assert "Open the gap by withholding" in metadata.METADATA_SYSTEM
    assert "exact verified values or none" in metadata.METADATA_SYSTEM
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_metadata.py::test_title_rule_present_in_metadata_system -v`
Expected: FAIL with `AssertionError`.

- [ ] **Step 3: Edit the TITLE bullet in `METADATA_SYSTEM`**

In `engine/pipeline/metadata.py`, find:
```python
- TITLE: <= 100 chars, curiosity-driven, front-load the hook, no ALL CAPS spam.
```
Replace with:
```python
- TITLE: <= 100 chars, no ALL CAPS spam. Open the gap by withholding the resolution, never by
  editorializing — make the unanswered question irresistible ("Ten days after this own goal, he
  was dead.") without giving away the payoff and without asserting framing not literally supported
  by the script ("The Lie America Believed" is spin, not withholding — banned). Same specifics
  rule as the script: exact verified values or none, no invented superlatives.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_metadata.py::test_title_rule_present_in_metadata_system -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/metadata.py tests/test_metadata.py
git commit -m "feat(packaging): titles open the curiosity gap by withholding, not editorializing"
```

---

## Task 3: `title_numbers_within` digit-containment backstop

**Files:**
- Modify: `engine/pipeline/script.py` (add `_norm_num` + `title_numbers_within` next to `tease_within_long`)
- Test: `tests/test_script.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_script.py`:

```python
def test_title_numbers_within_passes_when_numbers_in_script():
    from engine.pipeline import script
    ok, new = script.title_numbers_within(
        "The Record He Quit 1457 Yards Short", "He retired 1457 yards from the record in 1999.")
    assert ok and new == []


def test_title_numbers_within_flags_fabricated_number():
    from engine.pipeline import script
    ok, new = script.title_numbers_within(
        "The 1500-Yard Record He Walked Away From", "He retired 1457 yards short in 1999.")
    assert not ok and new == ["1500"]


def test_title_numbers_within_normalizes_thousands_separators():
    from engine.pipeline import script
    # script writes the value grouped, title writes it plain — must NOT false-flag.
    ok, new = script.title_numbers_within("The 2003 Final That Was Stolen",
                                          "It happened in the 2,003rd minute... in 2,003 of them.")
    assert ok and new == []
    # multi-grouped value normalizes fully (global comma strip).
    ok2, _ = script.title_numbers_within("1234567 Reasons", "There were 1,234,567 of them.")
    assert ok2


def test_title_numbers_within_passes_when_title_has_no_numbers():
    from engine.pipeline import script
    ok, new = script.title_numbers_within("The Goal That Cost Him His Life", "Andres Escobar.")
    assert ok and new == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_script.py -k title_numbers_within -v`
Expected: FAIL with `AttributeError: module 'engine.pipeline.script' has no attribute 'title_numbers_within'`.

- [ ] **Step 3: Add the helper**

In `engine/pipeline/script.py`, immediately after `tease_within_long` (end of file), add:

```python
def _norm_num(tok: str) -> str:
    """Normalise a digit token for value comparison: drop thousands-separator commas (global),
    keep everything else. '2,003' -> '2003'; '1,234,567' -> '1234567'. Decimal points are NOT
    stripped ('1.5' would corrupt to '15'); note _TEASE_NUM_RE already splits on '.', matching
    the existing tease-guard behaviour."""
    return tok.replace(",", "")


def title_numbers_within(title: str, script: str) -> tuple[bool, list[str]]:
    """Backstop for a generated SHORT title: every digit group in `title` must already appear
    (comma-normalised) as a digit group in the verified `script`. Returns (ok, sorted novel
    numbers); a non-empty list means the title introduced a number the fact-gated script doesn't
    contain → caller self-stubs to title_variants[0].

    Digit groups ONLY — the proper-noun half of tease_within_long is intentionally NOT used here:
    titles are Title Case, so every word looks like a proper noun and inflected title words would
    false-flag. Numbers don't inflect or get title-cased, so digit containment is surgical and
    targets the real risk (a fabricated stat reaching live metadata). Known conservative
    limitation: a number the title writes as a digit ('6') that the script only spells out ('six')
    is flagged and falls back — rare, and a safe false positive (we never ship a fabricated stat)."""
    script_nums = {_norm_num(n) for n in _TEASE_NUM_RE.findall(script)}
    new = {_norm_num(n) for n in _TEASE_NUM_RE.findall(title)} - script_nums
    return (not new, sorted(new))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_script.py -k title_numbers_within -v`
Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/script.py tests/test_script.py
git commit -m "feat(packaging): digit-containment backstop for short titles (comma-normalised)"
```

---

## Task 4: Dedicated Short-title pass, wired into `generate_short_metadata`

**Files:**
- Modify: `engine/pipeline/metadata.py` (imports, new `_SHORT_TITLE_SYSTEM`/`_SHORT_TITLE_SCHEMA`/`_short_title_llm`/`_short_title`, wire into `generate_short_metadata`)
- Test: `tests/test_metadata.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_metadata.py`:

```python
def test_short_title_pass_used_when_clean(monkeypatch):
    from engine.pipeline import metadata
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: "10 Days After This Own Goal, He Was Dead")
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda i, s: ("Hook.", ["t"]))
    idea = {"title_variants": ["The Andres Escobar Story"], "sport": "Soccer", "pillar": "p"}
    m = metadata.generate_short_metadata(idea, "Ten days after the own goal, in 10 minutes...")
    assert m["title"] == "10 Days After This Own Goal, He Was Dead"


def test_short_title_falls_back_when_llm_errors(monkeypatch):
    from engine.pipeline import metadata
    def boom(idea, script):
        raise RuntimeError("llm down")
    monkeypatch.setattr(metadata, "_short_title_llm", boom)
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda i, s: ("Hook.", ["t"]))
    idea = {"title_variants": ["The Long Poetic Title"], "sport": "F1", "pillar": "p"}
    m = metadata.generate_short_metadata(idea, "Some verified script.")
    assert m["title"] == "The Long Poetic Title"   # self-stub to title_variants[0]


def test_short_title_falls_back_when_backstop_rejects_fabricated_number(monkeypatch):
    from engine.pipeline import metadata
    # generated title invents '1500'; script only has '1457' → backstop rejects → fall back.
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: "1500 Yards From Immortality")
    monkeypatch.setattr(metadata, "_short_desc_llm", lambda i, s: ("Hook.", ["t"]))
    idea = {"title_variants": ["The Barry Sanders Story"], "sport": "NFL", "pillar": "p"}
    m = metadata.generate_short_metadata(idea, "He retired 1457 yards short of the record.")
    assert m["title"] == "The Barry Sanders Story"


def test_short_title_rule_present_in_short_title_system():
    from engine.pipeline import metadata
    assert "Open the gap by withholding" in metadata._SHORT_TITLE_SYSTEM
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_metadata.py -k short_title -v`
Expected: FAIL with `AttributeError` (`_short_title_llm` / `_SHORT_TITLE_SYSTEM` not defined).

- [ ] **Step 3: Add the title-pass module code**

In `engine/pipeline/metadata.py`, add the import near the top (after the existing imports):

```python
from engine.pipeline.script import title_numbers_within
```

Then, in the Shorts metadata section (just before `_short_desc_llm`), add:

```python
_SHORT_TITLE_SYSTEM = """You write the TITLE for a YouTube SHORT on a sports-history channel.
One line, <= ~70 characters so it stays legible on a phone. Punchy and front-loaded.

Open the gap by withholding the resolution, never by editorializing: make the unanswered question
irresistible without giving away the payoff, and assert no framing not literally supported by the
script. Use ONLY facts in the script — introduce no name, number, or date that isn't there. Any
specific you include must be the EXACT value from the script: never round, never invent a
superlative. Plain text only: no surrounding quotes, no hashtags, no emoji, no preamble or labels."""

_SHORT_TITLE_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}


def _short_title_llm(idea: dict, script: str) -> str:
    """One structured call → a punchy, front-loaded, gap-opening SHORT title. Raises on failure.
    Length (~70 chars) is a prompt-level soft target only — structured outputs do NOT enforce
    maxLength on this raw output_config.format path, so do not add it to the schema."""
    client = anthropic.Anthropic(max_retries=5)
    prompt = (f"SPORT: {idea.get('sport', '')}  PILLAR: {idea.get('pillar', '')}\n\n"
              f"SCRIPT:\n{script}\n\nWrite the Short title.")
    resp = client.messages.create(
        model=MODEL, max_tokens=64, system=_SHORT_TITLE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _SHORT_TITLE_SCHEMA}},
    )
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return data["title"].strip()


def _short_title(idea: dict, script: str) -> str:
    """The Short's title: a dedicated front-loaded, gap-opening LLM title, guarded by the
    digit-containment backstop. Self-stubs to title_variants[0] if the LLM call fails, returns
    empty, or the backstop rejects the title (a number absent from the fact-gated script)."""
    fallback = idea["title_variants"][0]
    try:
        title = _short_title_llm(idea, script)
    except Exception:
        return fallback
    if not title:
        return fallback
    ok, _ = title_numbers_within(title, script)
    return title if ok else fallback
```

- [ ] **Step 4: Wire it into `generate_short_metadata`**

In `generate_short_metadata`, find:
```python
    title = idea["title_variants"][0]
    sport = idea.get("sport", "")
```
Replace with:
```python
    title = _short_title(idea, script)
    sport = idea.get("sport", "")
```

- [ ] **Step 5: Patch the existing description-focused tests to be deterministic**

The three existing tests assert `m["title"]` equals `title_variants[0]`; with the new pass they would otherwise call the network. Add a `_short_title_llm` monkeypatch to each so the title is deterministic and network-free.

In `tests/test_metadata.py`, in `test_generate_short_metadata_assembles_description`, after the existing `monkeypatch.setattr(metadata, "_short_desc_llm", ...)` line add:
```python
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: idea["title_variants"][0])
```
In `test_generate_short_metadata_falls_back_on_llm_error`, after `monkeypatch.setattr(metadata, "_short_desc_llm", boom)` add:
```python
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: idea["title_variants"][0])
```
In `test_short_description_has_subscribe_cta`, after the `_short_desc_llm` monkeypatch add:
```python
    monkeypatch.setattr(metadata, "_short_title_llm",
                        lambda idea, script: idea["title_variants"][0])
```

- [ ] **Step 6: Run the metadata tests to verify they pass**

Run: `python3 -m pytest tests/test_metadata.py -v`
Expected: all pass (the 4 new `short_title` tests + the title-rule regression + the 3 patched existing tests).

- [ ] **Step 7: Run the full suite (the contract)**

Run: `python3 -m pytest tests/ -q`
Expected: all pass, no regressions.

- [ ] **Step 8: Commit**

```bash
git add engine/pipeline/metadata.py tests/test_metadata.py
git commit -m "feat(packaging): dedicated front-loaded short-title pass with digit backstop"
```

---

## Manual rollout (after merge — not a coding task)

Retitle the existing queue with the new prompts; metadata-only, no re-render:

```bash
# Long-form (per idea id):
python3 -m engine.run_produce --id <id> --metadata-only
# Short (per idea id) — picks up the new _short_title pass:
python3 -m engine.run_produce --id <id> --format short --metadata-only
```

The 5 unlisted Shorts get the new front-loaded titles; their baked-in hooks are left untouched (changing a hook is a re-render, out of scope per the spec).
