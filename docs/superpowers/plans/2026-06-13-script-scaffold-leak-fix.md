# Kill the script-scaffold leak — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The spoken narration is the only thing that survives extraction — no leaked reasoning preamble, word-count tallies, or duplicate drafts reach `script.md` or TTS.

**Architecture:** One shared, conservative `tts.is_scaffold_line(line)` detector. `script._parse_short` keeps the text after the LAST `MOOD:` line (the final draft) and drops scaffold lines; `tts.script_to_narration_text` drops scaffold lines as a render-time safety net. A prompt nudge reduces leakage at the source.

**Tech Stack:** Python 3 (`python3 -m pytest tests/ -q`).

**Spec:** `docs/superpowers/specs/2026-06-13-script-scaffold-leak-fix-design.md`
**Branch:** `feat/shortform-pacing-broll` (already checked out; kept with the short-form work).

**Conventions:** `python3` only. Absolute `engine.*` imports. PostToolUse hook runs `pytest tests/ -q` after each `engine/**.py` edit; intermediate TDD-red is expected — make the FINAL state green. Render is never a test gate.

---

## Task 1: `tts.is_scaffold_line` + render-time safety net

**Files:**
- Modify: `engine/video/tts.py` (add `is_scaffold_line` near the other text helpers, ~line 113; use it inside `script_to_narration_text`, ~line 114-130)
- Test: `tests/test_tts.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tts.py`:

```python
def test_is_scaffold_line_flags_leaked_scaffolding():
    from engine.video import tts
    assert tts.is_scaffold_line("**Word count:** Let me count carefully.")
    assert tts.is_scaffold_line("A(1) kung-fu(2) kick(3) into(4) the(5) stands(6)")
    assert tts.is_scaffold_line("154 words — within range. ✅")
    assert tts.is_scaffold_line("137 words — slightly under.")
    assert tts.is_scaffold_line("Good — I now have solid verified facts. Let me compile:")
    assert tts.is_scaffold_line("Let me compile what I know:")
    assert tts.is_scaffold_line("Now let me write the narration and count words carefully.")


def test_is_scaffold_line_keeps_real_narration():
    from engine.video import tts
    for ln in [
        "A kung-fu kick into the stands shook English football to its core.",
        "Eight-month ban. Criminal charges.",
        "October 1995 — Cantona walks back out at Old Trafford.",
        "The ban didn't break Manchester United. It built them.",
        "He was one season from immortality.",
    ]:
        assert not tts.is_scaffold_line(ln), f"false positive on: {ln}"


def test_script_to_narration_text_strips_leaked_scaffold():
    from engine.video import tts
    md = (
        "# Title\n\n"
        "Good — I now have solid verified facts. Let me compile:\n"
        "- January 25, 1995: the kick\n\n"
        "MOOD: triumphant\n\n"
        "A kung-fu kick into the stands shook English football.\n"
        "The ban built them.\n\n"
        "**Word count:** Let me count carefully.\n"
        "A(1) kung-fu(2) kick(3) into(4) the(5) stands(6)\n"
        "154 words — within range. ✅\n"
    )
    out = tts.script_to_narration_text(md)
    assert "kung-fu kick into the stands shook english football" in out.lower()
    assert "word count" not in out.lower()
    assert "(1)" not in out and "(2)" not in out
    assert "let me compile" not in out.lower()
    assert "✅" not in out


def test_script_to_narration_text_leaves_clean_script_unchanged():
    from engine.video import tts
    md = "# Title\n\nMOOD: triumphant\n\nA kung-fu kick shook football. The ban built them.\n"
    out = tts.script_to_narration_text(md)
    assert out.strip() == "A kung-fu kick shook football. The ban built them."
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_tts.py::test_is_scaffold_line_flags_leaked_scaffolding -v`
Expected: FAIL — `AttributeError: module 'engine.video.tts' has no attribute 'is_scaffold_line'`.

- [ ] **Step 3: Implement `is_scaffold_line`**

In `engine/video/tts.py`, just above `def script_to_narration_text` (~line 113):

```python
# Lines a chatty model leaks around the real narration — reasoning preamble, word-count
# tallies, draft markers. Conservative + line-start anchored so real narration never matches.
_SCAFFOLD_RE = [
    re.compile(r"^word count\b", re.I),
    re.compile(r"^let me\b", re.I),
    re.compile(r"^now let me\b", re.I),
    re.compile(r"^here'?s\b", re.I),
    re.compile(r"^here is\b", re.I),
    re.compile(r"^good[\s,—-]", re.I),
    re.compile(r"^i'?ll write\b", re.I),
    re.compile(r"^i (now )?have\b", re.I),
    re.compile(r"^\d+\s+words\b", re.I),
    re.compile(r"\bwords\b\s*[—-].*(within range|slightly under|over)", re.I),
]
_TOKEN_TALLY_RE = re.compile(r"\(\d+\)")


def is_scaffold_line(line: str) -> bool:
    """True when a line is leaked model scaffolding (reasoning preamble, word-count tally,
    draft marker) rather than spoken narration. Strips markdown emphasis first."""
    s = re.sub(r"[*_`]", "", line).strip()
    if not s:
        return False
    if "✅" in s and len(s.split()) <= 6:
        return True
    if len(_TOKEN_TALLY_RE.findall(s)) >= 3:   # "A(1) kung-fu(2) kick(3)…"
        return True
    return any(p.search(s) for p in _SCAFFOLD_RE)
```

- [ ] **Step 4: Use it in `script_to_narration_text`**

In the per-line loop of `script_to_narration_text`, add a skip right after the `MOOD:` skip:

```python
        if re.match(r"(?i)^MOOD:\s*\w+\s*$", s):  # leaked short-script MOOD header
            continue
        if is_scaffold_line(s):                    # leaked reasoning / word-count / drafts
            continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tts.py -q`
Expected: PASS (all tts tests, including the existing ones).

- [ ] **Step 6: Commit**

```bash
git add engine/video/tts.py tests/test_tts.py
git commit -m "feat(script): is_scaffold_line + strip leaked scaffold at render-time"
```

---

## Task 2: `script._parse_short` keeps the final draft, drops scaffold

**Files:**
- Modify: `engine/pipeline/script.py` (add the tts import near the top imports; rewrite `_parse_short`, ~line 165)
- Test: `tests/test_script.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_script.py`:

```python
def test_parse_short_keeps_final_draft_and_strips_scaffold():
    from engine.pipeline import script
    raw = (
        "Good — I now have solid verified facts. Let me compile:\n"
        "- January 25, 1995: the kick\n\n"
        "MOOD: triumphant\n\n"
        "First draft narration that is wrong length.\n\n"
        "**Word count:** Let me count carefully.\n"
        "First(1) draft(2) narration(3)\n"
        "137 words — slightly under.\n\n"
        "MOOD: triumphant\n\n"
        "A kung-fu kick into the stands shook English football. The ban built them.\n\n"
        "154 words — within range. ✅\n"
    )
    out = script._parse_short(raw)
    assert out["mood"] == "triumphant"
    assert out["script"] == (
        "A kung-fu kick into the stands shook English football. The ban built them."
    )
    assert "First draft" not in out["script"]
    assert "word count" not in out["script"].lower()
    assert "(1)" not in out["script"]


def test_parse_short_clean_single_draft_unchanged():
    from engine.pipeline import script
    raw = "MOOD: somber\n\nThe own goal cost him everything. He never played again."
    out = script._parse_short(raw)
    assert out["mood"] == "somber"
    assert out["script"] == "The own goal cost him everything. He never played again."
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_script.py::test_parse_short_keeps_final_draft_and_strips_scaffold -v`
Expected: FAIL — the current parser keeps the first draft + scaffold.

- [ ] **Step 3: Add the tts import**

At the top of `engine/pipeline/script.py`, with the other imports, add:

```python
from engine.video import tts as _tts
```

(`engine.video.tts` imports kokoro/numpy lazily inside functions, so this top-level import is
cheap and introduces no cycle — `tts` does not import `engine.pipeline`.)

- [ ] **Step 4: Rewrite `_parse_short`**

Replace the body of `_parse_short` (keep its docstring intent) with:

```python
def _parse_short(raw: str) -> dict:
    """Return {'script', 'mood'} — the spoken narration only.

    Robust to a chatty model: the narration is the block after the LAST valid `MOOD:`
    header (each leaked draft carries its own MOOD line, so the final draft follows the
    last one). Leading preamble, earlier drafts, stray MOOD lines, noise, and scaffold
    (word-count tallies, 'let me…', token counts) are dropped. No MOOD header → narration
    starts at the top, still scaffold-filtered."""
    lines = raw.splitlines()

    mood = ""
    start = 0
    for i, ln in enumerate(lines):
        mv = _mood_value(ln.strip())
        if mv in _SHORT_MOODS:
            mood = mv
            start = i + 1

    body = [ln for ln in lines[start:]
            if not _is_noise(ln.strip())
            and _mood_value(ln.strip()) not in _SHORT_MOODS
            and not _tts.is_scaffold_line(ln)]
    return {"script": "\n".join(body).strip(), "mood": mood}
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS. The existing short-parse tests (`test_generate_short_script_defaults_mood_when_absent`, `test_short_mood_only_accepts_known_values`, and any `startswith("The own goal")` test) must stay green — verify them specifically:
`python3 -m pytest tests/test_script.py -q`

- [ ] **Step 6: Commit**

```bash
git add engine/pipeline/script.py tests/test_script.py
git commit -m "feat(script): _parse_short keeps the final draft, drops leaked scaffold"
```

---

## Task 3: Prompt nudge (reduce leakage at the source)

**Files:**
- Modify: `engine/pipeline/script.py` (`SHORT_SYSTEM` ~line 119-121, `DERIVE_TEASE_SYSTEM` ~line 246)
- Test: `tests/test_script.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_script.py`:

```python
def test_short_prompts_forbid_shown_work():
    from engine.pipeline import script
    for p in (script.SHORT_SYSTEM, script.DERIVE_TEASE_SYSTEM):
        s = p.lower()
        assert "word count" in s            # explicitly bans the word-count tally
        assert "draft" in s                 # bans multiple drafts
        assert "no preamble" in s or "do not show your work" in s
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_script.py::test_short_prompts_forbid_shown_work -v`
Expected: FAIL — phrases not yet in the prompts.

- [ ] **Step 3: Add the nudge to `SHORT_SYSTEM`**

In `SHORT_SYSTEM`, replace the final paragraph:

```
Your VERY FIRST line must be exactly: MOOD: <one of: tense | triumphant | somber | hype>
(the story's dominant emotional register — drives music and narrator voice). Then the
narration on the following lines, and nothing else."""
```

with:

```
Your VERY FIRST line must be exactly: MOOD: <one of: tense | triumphant | somber | hype>
(the story's dominant emotional register — drives music and narrator voice). Then the
narration on the following lines.

Output ONLY the final narration after the MOOD line. Do NOT show your work — no preamble,
no "let me…", no bullet fact lists, no word counts, no multiple drafts, no commentary."""
```

- [ ] **Step 4: Add the nudge to `DERIVE_TEASE_SYSTEM`**

In `DERIVE_TEASE_SYSTEM`, replace its final paragraph (the `Your VERY FIRST line must be exactly: MOOD:` … `and nothing else."""`) with the same two-paragraph version as in Step 3.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_script.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/pipeline/script.py tests/test_script.py
git commit -m "feat(script): prompt nudge — output only final narration, no shown work"
```

---

## Task 4: Proof — re-produce + re-render Cantona, no hand-editing

**Files:** none (verification).

- [ ] **Step 1: Re-produce**

Run: `python3 -m engine.run_produce --id 25051da8 --format short`
Inspect `produced/25051da8/short/script.md` — it must contain ONLY a `# title`, a `MOOD:` line,
and the single final narration. No preamble, no word-count block, no duplicate drafts. Do NOT
hand-edit it.

- [ ] **Step 2: Fact-review if flagged**

If the gate marks it `needs_review`, run the `fact-review` skill, then
`python3 -m engine.run_auto --review 25051da8 --note "fact-reviewed"`.

- [ ] **Step 3: Render + QC + eyeball**

```bash
.venv-video/bin/python -m engine.run_video --id 25051da8 --render --mode narrated --format short
.venv-video/bin/python -c "from engine.pipeline import qc; import json; print(json.dumps(qc.qc_video('25051da8','short'),indent=2))"
open produced/25051da8/short/video/video.mp4
```
Confirm: narration is clean (no spoken "word count"/tallies), lands ~50-55s, cuts every ~4s.

---

## Ship

Whole `feat/shortform-pacing-broll` branch (pacing + b-roll + tuning + this leak fix) gets one
final dual adversarial review (Codex + Claude) before squash-merge, per `ship-video-change`.

## Self-Review (done at write time)

- **Spec coverage:** shared detector → Task 1; `_parse_short` last-draft + filter → Task 2;
  render-time net → Task 1 Step 4; prompt nudge → Task 3; proof → Task 4. All mapped.
- **Type/name consistency:** `tts.is_scaffold_line(line)->bool` defined in Task 1, imported as
  `_tts.is_scaffold_line` in Task 2. `_parse_short` keeps its `{'script','mood'}` contract.
- **No placeholders:** every step has concrete code + exact command + expected result.
- **False-positive guard:** Task 1's `test_is_scaffold_line_keeps_real_narration` and Task 1's
  clean-script test + Task 2's clean-single-draft test protect normal output from the new filters.
