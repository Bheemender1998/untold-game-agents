# Overnight 3-Long-3-Short Companion Automation (Phase 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the nightly `run_auto --count 3` produce 3 longs + 3 cross-linked companion teaser shorts (each short derived from its verified long, on the approved Senna short template), and have one `--approve` upload both.

**Architecture:** A new `derive_short_tease` (same approved short-writer style, seeded from the long) + a deterministic `tease_within_long` containment guard (no web fact-gate) in `pipeline/script.py`; a `produce_companion_short` path in `run_produce.py` writing `short/` artifacts; the short `EndCTA` gains a "Full story" line; `run_auto` spawns the companion short after each long and uploads both at approval.

**Tech Stack:** Python 3 (`python3 -m pytest tests/ -q`), Remotion/TS, Kokoro TTS, faster-whisper, Pexels.

**Spec:** `docs/superpowers/specs/2026-06-12-overnight-companion-shorts-phase2-design.md`

**Conventions:** `python3` not `python`; absolute `engine.*` imports; a PostToolUse hook runs `pytest tests/` after each engine edit (intermediate TDD failures are expected). Self-stub — a companion-short failure must never break the long or the batch. Unlisted only; never `--public` without explicit say-so. Render is never a gate.

---

### Task 1: `derive_short_tease` — companion short from the verified long (`engine/pipeline/script.py`)

Mirrors the approved `ShortScriptWriter` style, but seeds from the long script and forbids new facts.

**Files:**
- Modify: `engine/pipeline/script.py` (add `DERIVE_TEASE_SYSTEM`, `CompanionTeaseWriter`, `derive_short_tease`)
- Test: `tests/test_script.py`

- [ ] **Step 1: Add the failing test** to `tests/test_script.py`:

```python
def test_derive_short_tease_parses_mood_and_includes_long(monkeypatch):
    from engine.pipeline import script
    captured = {}
    def fake_call(self, prompt, use_search=True):
        captured["prompt"] = prompt
        captured["use_search"] = use_search
        return "MOOD: somber\nHe was closing fast. Then the flag fell. The full story is wild."
    monkeypatch.setattr(script.CompanionTeaseWriter, "_call", fake_call, raising=True)
    idea = {"title_variants": ["The Race That Was Stopped"], "hook": "h", "pillar": "what_if",
            "sport": "F1", "target_audience": "a", "why_it_works": "w"}
    out = script.derive_short_tease("LONG SCRIPT: Senna closed a seven-second gap...", idea)
    assert out["mood"] == "somber"
    assert "He was closing fast." in out["script"]
    assert "MOOD:" not in out["script"]
    assert "LONG SCRIPT: Senna closed" in captured["prompt"]   # seeded from the long
    assert captured["use_search"] is False                     # no web search — derived from verified long
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_script.py::test_derive_short_tease_parses_mood_and_includes_long -q`
Expected: FAIL (`CompanionTeaseWriter`/`derive_short_tease` not defined)

- [ ] **Step 3: Implement** in `engine/pipeline/script.py`. Add after `generate_short_script` (after line ~210):

```python
DERIVE_TEASE_SYSTEM = """You write a YouTube SHORT (vertical, 30-50s) that is a condensed,
high-retention cut of a LONGER video whose full narration is given to you. Same craft as our
shorts: write for the ear, present-tense, concrete, scroll-stopping.

In this exact 3-beat shape, as flowing prose (not labelled):
- HOOK: a scroll-stopping first line that lands the stakes in under two seconds.
- FACT: the single most arresting fact of the story, tight and concrete.
- PAYOFF: a closing line that resolves the short while nodding that the full story is bigger.

HARD INTEGRITY RULE: use ONLY facts that appear in the long narration provided. Do NOT introduce
any new name, date, number, quote, or claim that is not already in that text. If something isn't
in the long, leave it out. No web search — the long is already verified.

Your VERY FIRST line must be exactly: MOOD: <one of: tense | triumphant | somber | hype>
(the story's dominant emotional register — drives music and narrator voice). Then the narration
on the following lines, and nothing else."""


class CompanionTeaseWriter(BaseAgent):
    def __init__(self):
        super().__init__()
        self.name = "companion_tease_writer"
        self.system_prompt = DERIVE_TEASE_SYSTEM

    def write(self, long_script: str, idea: dict) -> dict:
        title = idea["title_variants"][0]
        prompt = f"""Write the SHORT companion narration for this long video.

TITLE:  {title}
SPORT:  {idea.get('sport', '')}

LENGTH — HARD constraint: {config.SHORT_SCRIPT_WORDS_MIN}-{config.SHORT_SCRIPT_WORDS_MAX} spoken
words total (~30-50 seconds). Hook + one fact + payoff. Count your words; if long, cut.

Use ONLY facts present in the LONG NARRATION below — introduce nothing new.

LONG NARRATION:
{long_script}

Remember: first line `MOOD: <tense|triumphant|somber|hype>`, then the narration only."""
        return _parse_short(self._call(prompt, use_search=False))


def derive_short_tease(long_script: str, idea: dict) -> dict:
    """Return {'script': str, 'mood': str} for a companion Short derived from the verified
    long. Same approved short style; no web search (the long is already fact-gated)."""
    return CompanionTeaseWriter().write(long_script, idea)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_script.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/script.py tests/test_script.py
git commit -m "feat(script): derive_short_tease — companion short from the verified long (no web search)"
```

---

### Task 2: `tease_within_long` — deterministic containment guard (`engine/pipeline/script.py`)

No network. Flags any name/number in the short that isn't in the long.

**Files:**
- Modify: `engine/pipeline/script.py` (add `tease_within_long`)
- Test: `tests/test_script.py`

- [ ] **Step 1: Add the failing test** to `tests/test_script.py`:

```python
def test_tease_within_long_passes_when_subset():
    from engine.pipeline import script
    long = "In 1984 Ayrton Senna chased Alain Prost at Monaco. The gap was seven seconds."
    short = "Senna was closing on Prost at Monaco in 1984. Seven seconds. Then a flag fell."
    ok, extra = script.tease_within_long(short, long)
    assert ok and extra == []


def test_tease_within_long_flags_new_name_and_number():
    from engine.pipeline import script
    long = "In 1984 Ayrton Senna chased Alain Prost at Monaco."
    short = "Senna beat Nigel Mansell by 1992 points."   # Mansell + 1992 not in long
    ok, extra = script.tease_within_long(short, long)
    assert not ok
    assert "Mansell" in extra and "1992" in extra
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_script.py::test_tease_within_long_flags_new_name_and_number -q`
Expected: FAIL (`tease_within_long` not defined)

- [ ] **Step 3: Implement** in `engine/pipeline/script.py`. Add after `derive_short_tease`:

```python
import re as _re

# Capitalized words/names (skip sentence-start common words); and number groups.
_TEASE_NAME_RE = _re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b")
_TEASE_NUM_RE = _re.compile(r"\b\d[\d,]*\b")
_TEASE_STOP = {"the", "this", "that", "then", "they", "he", "she", "it", "and", "but",
               "in", "on", "at", "a", "an", "his", "her", "their", "by", "so", "no",
               "when", "then", "now", "seven"}  # 'seven' etc. are number-words, checked separately


def tease_within_long(short_script: str, long_script: str) -> tuple[bool, list[str]]:
    """Deterministic integrity guard (no network): every factual specific in the short —
    capitalized proper-noun tokens and digit groups — must already appear in the long.
    Returns (ok, sorted_new_tokens). A non-empty list means the short introduced something
    the verified long didn't contain → caller flags the short needs_review."""
    long_low = long_script.lower()
    new: set[str] = set()
    for tok in _TEASE_NAME_RE.findall(short_script):
        if len(tok) < 3 or tok.lower() in _TEASE_STOP:
            continue
        if tok.lower() not in long_low:
            new.add(tok)
    for num in _TEASE_NUM_RE.findall(short_script):
        if num not in long_script:
            new.add(num)
    return (not new, sorted(new))
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_script.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/script.py tests/test_script.py
git commit -m "feat(script): tease_within_long containment guard (no new facts vs the long)"
```

---

### Task 3: `produce_companion_short` — write the short artifacts from the long (`engine/run_produce.py`)

Reads `long/script.md`, derives the tease, runs the guard, writes `short/script.md` + `short/metadata.json`, records `short_status`.

**Files:**
- Modify: `engine/run_produce.py` (add `produce_companion_short`)
- Test: `tests/test_run_produce.py`

- [ ] **Step 1: Add the failing test** to `tests/test_run_produce.py`:

```python
def test_produce_companion_short_writes_short_artifacts(tmp_path, monkeypatch):
    from engine import run_produce, paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    # seed a long script
    import os
    longdir = tmp_path / "produced" / "zz" / "long"
    longdir.mkdir(parents=True)
    (longdir / "script.md").write_text("# T\n\nIn 1984 Senna chased Prost at Monaco. Seven seconds.\n")
    monkeypatch.setattr(run_produce, "derive_short_tease",
                        lambda long_script, idea: {"script": "Senna chased Prost at Monaco in 1984.", "mood": "somber"})
    monkeypatch.setattr(run_produce, "generate_short_metadata",
                        lambda idea, s: {"title": "Senna Short", "description": "d", "tags": []})
    seen = {}
    monkeypatch.setattr(run_produce.q, "update_idea", lambda i, **f: seen.update(f))
    idea = {"id": "zz", "title_variants": ["T"], "sport": "F1"}
    res = run_produce.produce_companion_short(idea)
    assert (tmp_path / "produced" / "zz" / "short" / "script.md").exists()
    assert (tmp_path / "produced" / "zz" / "short" / "metadata.json").exists()
    assert res["within_long"] is True
    assert seen.get("short_status") == "short_ready"
    assert seen.get("mood") == "somber"


def test_produce_companion_short_flags_when_guard_fails(tmp_path, monkeypatch):
    from engine import run_produce, paths
    monkeypatch.setattr(paths, "PRODUCED_DIR", str(tmp_path / "produced"))
    longdir = tmp_path / "produced" / "zz" / "long"
    longdir.mkdir(parents=True)
    (longdir / "script.md").write_text("# T\n\nIn 1984 Senna chased Prost at Monaco.\n")
    monkeypatch.setattr(run_produce, "derive_short_tease",
                        lambda long_script, idea: {"script": "Senna beat Mansell by 1992 points.", "mood": "hype"})
    monkeypatch.setattr(run_produce, "generate_short_metadata",
                        lambda idea, s: {"title": "x", "description": "d", "tags": []})
    seen = {}
    monkeypatch.setattr(run_produce.q, "update_idea", lambda i, **f: seen.update(f))
    res = run_produce.produce_companion_short({"id": "zz", "title_variants": ["T"], "sport": "F1"})
    assert res["within_long"] is False
    assert seen.get("short_status") == "short_needs_review"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_run_produce.py::test_produce_companion_short_writes_short_artifacts -q`
Expected: FAIL (`produce_companion_short` not defined)

- [ ] **Step 3: Implement** in `engine/run_produce.py`. Add the imports to the existing line `from engine.pipeline.script import ...`:

```python
from engine.pipeline.script import (clean_short_body, generate_script, generate_short_script,
                                     derive_short_tease, tease_within_long)
```

Add the function after `produce` (after line ~156):

```python
def produce_companion_short(idea: dict) -> dict:
    """Derive a companion Short from this idea's already-produced LONG, write the short/
    artifacts, and record short_status. No web fact-gate — the long is verified and the
    tease is constrained to it; a containment-guard failure flags short_needs_review.
    Self-stubbing: returns a result dict; never raises out (callers continue the batch)."""
    idea_id = idea["id"]
    title = idea["title_variants"][0]
    long_script_file = paths.script_path(idea_id, "long")
    if not os.path.exists(long_script_file):
        raise FileNotFoundError(f"no long script for [{idea_id}] at "
                                f"{os.path.relpath(long_script_file, _ROOT)}")
    with open(long_script_file) as f:
        long_script = f.read()

    out = derive_short_tease(long_script, idea)
    short_script = out["script"]
    if not short_script.strip():
        raise ValueError(f"companion tease for [{idea_id}] came back empty")
    within, extra = tease_within_long(short_script, long_script)

    out_dir = paths.artifact_dir(idea_id, "short")
    os.makedirs(out_dir, exist_ok=True)
    _atomic_write(paths.script_path(idea_id, "short"), f"# {title}\n\n{short_script}\n")
    meta = generate_short_metadata(idea, short_script)
    _atomic_write(paths.metadata_path(idea_id, "short"),
                  json.dumps(meta, indent=2, ensure_ascii=False))

    short_status = "short_ready" if within else "short_needs_review"
    fields = {"short_status": short_status,
              "short_script_path": os.path.relpath(paths.script_path(idea_id, "short"), _ROOT),
              "short_metadata_path": os.path.relpath(paths.metadata_path(idea_id, "short"), _ROOT)}
    if out.get("mood"):
        fields["mood"] = out["mood"]   # drives the short's music + Kokoro voice
    if not within:
        fields["short_guard_new_tokens"] = extra
    q.update_idea(idea_id, **fields)
    print(f"  {GREEN if within else RED}{'✓' if within else '⚠'} companion short "
          f"({len(short_script.split())} words) — {short_status}"
          f"{'' if within else f' (new: {extra})'}{RESET}")
    return {"metadata": meta, "within_long": within, "new_tokens": extra}
```

> Note: `generate_short_metadata` is already imported at the top of `run_produce.py`. The companion short's `mood` is written to the idea so `run_video --format short` picks the mood-matched music + Kokoro voice (per-story depiction).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_run_produce.py -q`
Expected: PASS (both new tests + existing)

- [ ] **Step 5: Commit**

```bash
git add engine/run_produce.py tests/test_run_produce.py
git commit -m "feat(produce): produce_companion_short — derive+guard+write short/ from the long"
```

---

### Task 4: Short "Full story" CTA + short music fallback (Remotion)

All forward shorts are companions, so the vertical `EndCTA` always shows the pointer.

**Files:**
- Modify: `engine/video/remotion/src/components/EndCTA.tsx`
- Modify: `engine/video/remotion/src/UntoldShort.tsx` (music fallback 0.12 → 0.08)

- [ ] **Step 1: Add the "Full story" line to the vertical EndCTA.** In `EndCTA.tsx`, after the `SUBSCRIBE` block (just before the closing `</AbsoluteFill>` of the component), add a `vertical`-only line. Insert this block right after the closing `</div>` of the `LIKE · COMMENT / SUBSCRIBE` text div:

```tsx
      {vertical ? (
        <div
          style={{
            fontFamily: oswald,
            fontSize: 38,
            color: GOLD,
            textTransform: 'uppercase',
            textAlign: 'center',
            letterSpacing: '0.04em',
            marginTop: 28,
            transform: `translateY(${y}px)`,
            textShadow: '0 4px 24px rgba(0,0,0,0.85)',
          }}
        >
          Full story on our channel
          <br />
          link in description
        </div>
      ) : null}
```
(`oswald`, `GOLD`, `y` are already imported/defined in EndCTA.tsx.)

- [ ] **Step 2: Fix the short music fallback** in `UntoldShort.tsx` — replace `const peak = props.musicVolume ?? 0.12;` with:

```tsx
              const peak = props.musicVolume ?? 0.08;
```

- [ ] **Step 3: Type-check**

Run: `cd engine/video/remotion && npx tsc --noEmit` (run `npm install` first if deps missing)
Expected: clean compile.

- [ ] **Step 4: Commit**

```bash
git add engine/video/remotion/src/components/EndCTA.tsx engine/video/remotion/src/UntoldShort.tsx
git commit -m "feat(short): EndCTA 'Full story on our channel' pointer + 0.08 music fallback"
```

---

### Task 5: Spawn the companion short in the overnight pipeline (`engine/run_auto.py`)

After a long reaches `awaiting_approval`, produce + render + QC its companion short.

**Files:**
- Modify: `engine/run_auto.py`
- Test: `tests/test_run_auto.py`

- [ ] **Step 1: Add the failing test** to `tests/test_run_auto.py`:

```python
def test_render_companion_short_renders_and_qcs(monkeypatch):
    idea = {"id": "x"}
    monkeypatch.setattr(run_auto, "_produce_companion", lambda i: {"within_long": True})
    calls = {}
    # _run is the subprocess runner; capture the render command
    monkeypatch.setattr(run_auto, "_run", lambda cmd, timeout=None: calls.setdefault("cmd", cmd) or 0)
    monkeypatch.setattr(run_auto.qc, "qc_video", lambda i, fmt="long": {"passed": True, "checks": []})
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto._companion_short("x")
    assert "--format" in calls["cmd"] and "short" in calls["cmd"]   # rendered as a short
    assert seen.get("short_status") == "short_awaiting_approval"


def test_companion_short_failure_does_not_raise(monkeypatch):
    idea = {"id": "x"}
    monkeypatch.setattr(run_auto, "_produce_companion",
                        lambda i: (_ for _ in ()).throw(RuntimeError("derive blew up")))
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto._companion_short("x")   # must not raise
    assert seen.get("short_status") == "short_failed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_run_auto.py::test_render_companion_short_renders_and_qcs -q`
Expected: FAIL (`_companion_short`/`_produce_companion` not defined)

- [ ] **Step 3: Implement** in `engine/run_auto.py`. Add helpers after `_render_and_qc` (after line ~80):

```python
def _produce_companion(idea_id: str) -> dict:
    """Derive + write the companion short artifacts (in-process; no web fact-gate)."""
    from engine import run_produce
    idea = q.get_by_id(idea_id) or {}
    return run_produce.produce_companion_short(idea)


def _companion_short(idea_id: str) -> None:
    """Produce → render → QC the companion short for a long that's awaiting approval.
    Self-stubbing: any failure flags short_failed and returns (never breaks the long)."""
    try:
        res = _produce_companion(idea_id)
        if not res.get("within_long", True):
            q.update_idea(idea_id, short_status="short_needs_review")
            print(f"· {idea_id}: companion short needs_review (containment guard)")
            return
        rc = _run([_VENV_PY, "-m", "engine.run_video", "--id", idea_id,
                   "--render", "--mode", "narrated", "--format", "short"],
                  timeout=config.RENDER_TIMEOUT_S)
        if rc != 0:
            q.update_idea(idea_id, short_status="short_render_failed",
                          short_render_note=("timed out" if rc == 124 else f"exit {rc}"))
            print(f"· {idea_id}: companion short render_failed")
            return
        report = qc.qc_video(idea_id, "short")
        status = "short_awaiting_approval" if report["passed"] else "short_qc_failed"
        q.update_idea(idea_id, short_status=status)
        print(f"· {idea_id}: companion short {status}")
    except Exception as e:                       # never break the long / batch
        q.update_idea(idea_id, short_status="short_failed", short_render_note=str(e))
        print(f"· {idea_id}: companion short failed — {e}")
```

In `_render_and_qc`, after the long is set to `awaiting_approval`, spawn the companion short. Change the end of `_render_and_qc` (the lines that set status + print) to:

```python
    report = qc.qc_video(idea_id, _OVERNIGHT_FMT)
    status = "awaiting_approval" if report["passed"] else "qc_failed"
    q.update_idea(idea_id, status=status)
    print(f"· {idea_id}: {status}")
    if status == "awaiting_approval":
        _companion_short(idea_id)   # 3 long + 3 short: each cleared long spawns its short
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_run_auto.py -q`
Expected: PASS (all, including 2 new)

- [ ] **Step 5: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto.py
git commit -m "feat(auto): spawn companion short (produce+render+qc) after each cleared long"
```

---

### Task 6: Paired upload at approval (`engine/run_auto.py` `cmd_approve`)

`--approve` uploads the long first, then the companion short with the long URL appended to its description.

**Files:**
- Modify: `engine/run_auto.py` (`cmd_approve`)
- Test: `tests/test_run_auto.py`

- [ ] **Step 1: Add the failing test** to `tests/test_run_auto.py`:

```python
def test_cmd_approve_uploads_long_then_linked_short(monkeypatch):
    idea = {"id": "x", "status": "awaiting_approval",
            "metadata_path": "produced/x/long/metadata.json",
            "video_path": "produced/x/long/video/video.mp4",
            "short_status": "short_awaiting_approval",
            "short_metadata_path": "produced/x/short/metadata.json",
            "short_video_path": "produced/x/short/video/video.mp4"}
    monkeypatch.setattr(run_auto.q, "get_by_id", lambda i: idea)
    metas = {"produced/x/long/metadata.json": {"title": "Long", "description": "L", "tags": []},
             "produced/x/short/metadata.json": {"title": "Short", "description": "S", "tags": []}}
    monkeypatch.setattr(run_auto, "_load_metadata", lambda p: metas[p])
    import os
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    ups = []
    monkeypatch.setattr(run_auto.uploader, "upload", lambda **k: ups.append(k) or ("ytLONG" if "Long" in k["title"] else "ytSHORT"))
    appends = {}
    monkeypatch.setattr(run_auto.uploader, "append_to_description",
                        lambda vid, suffix, **k: appends.update(vid=vid, suffix=suffix) or "newdesc")
    seen = {}
    monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: seen.update(f))
    run_auto.cmd_approve("x", public=False, dry_run=False)
    assert ups[0]["title"] == "Long" and ups[1]["title"] == "Short"     # long first
    assert "youtu.be/ytLONG" in appends["suffix"]                        # short desc links the long
    assert appends["vid"] == "ytSHORT"
    assert "ytLONG" in seen["long_youtube_url"] and "ytSHORT" in seen["short_youtube_url"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_run_auto.py::test_cmd_approve_uploads_long_then_linked_short -q`
Expected: FAIL (current cmd_approve uploads only the long)

- [ ] **Step 3: Implement.** In `engine/run_auto.py` `cmd_approve`, after the long upload + `q.update_idea(..., long_youtube_url=...)` and its print, add the companion-short upload:

```python
    long_url = f"https://youtu.be/{yt_id}"
    # Companion short (if produced + clean): upload unlisted with the long URL in its description.
    if idea.get("short_status") == "short_awaiting_approval" and idea.get("short_video_path"):
        try:
            smeta = _load_metadata(idea["short_metadata_path"])
            svideo = os.path.join(_ROOT, idea["short_video_path"])
            sdesc = f"{smeta.get('description', '')}\n\n▶ Full story on our channel: {long_url}".strip()
            short_id = uploader.upload(video_path=svideo, title=smeta["title"],
                                       description=sdesc, tags=smeta.get("tags"), privacy=privacy)
            q.update_idea(idea_id, short_youtube_url=f"https://youtu.be/{short_id}")
            print(f"✓ companion short {idea_id} → https://youtu.be/{short_id} ({privacy})")
        except Exception as e:                  # short failure must not undo the long
            print(f"⚠ {idea_id}: long published but companion short upload failed — {e}")
```

> The long's existing `q.update_idea(idea_id, status="published", long_youtube_url=...)` stays. `privacy`, `yt_id`, `idea_id`, `_ROOT`, `_load_metadata`, `uploader`, `os` are all already in scope in `cmd_approve`.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_run_auto.py -q`
Expected: PASS (all)

- [ ] **Step 5: Full suite + commit**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (whole suite)

```bash
git add engine/run_auto.py tests/test_run_auto.py
git commit -m "feat(auto): --approve uploads long then companion short (desc cross-linked)"
```

---

## Self-Review

**Spec coverage:**
- `derive_short_tease` (approved style, seeded from long, no web search) → Task 1. ✅
- Containment guard (no new facts) → Task 2; wired in produce → Task 3. ✅
- Companion short artifacts under `short/` + per-story mood recorded → Task 3. ✅
- Short "Full story" CTA + per-story music/voice (mood-driven, already in the short render path) → Task 4 (CTA) + Task 3 (mood). ✅
- Overnight spawns companion short after each long → Task 5. ✅
- One `--approve` uploads long then cross-linked short → Task 6. ✅
- Self-stub (companion failure never breaks the long/batch) → Tasks 3, 5, 6. ✅
- Unlisted only; integrity via long fact-gate + guard → Tasks 3, 6. ✅

**Placeholder scan:** every code step has full code; commands have expected output; no TBD/TODO. ✅

**Type/name consistency:** `derive_short_tease(long_script, idea)→{script,mood}` and `tease_within_long(short, long)→(ok,list)` (Tasks 1-2) match their callers in `produce_companion_short` (Task 3); `produce_companion_short(idea)→{within_long,...}` matches `_produce_companion`/`_companion_short` (Task 5); `short_status` values (`short_ready`/`short_needs_review`/`short_awaiting_approval`/`short_render_failed`/`short_qc_failed`/`short_failed`) and `short_metadata_path`/`short_video_path` are consistent across Tasks 3, 5, 6. `run_video --format short` writes `short/video/video.mp4` (Phase-1 split), which Task 6 reads as `short_video_path` — note Task 5's render must also record `short_video_path`; add that. ✅ (fix applied below)

**Fix from self-review:** Task 5's `_companion_short` must record `short_video_path` after a successful render so Task 6 can find it. Update Task 5 Step 3 — in `_companion_short`, after the QC pass branch, set it:

```python
        report = qc.qc_video(idea_id, "short")
        if report["passed"]:
            q.update_idea(idea_id, short_status="short_awaiting_approval",
                          short_video_path=os.path.relpath(paths.video_dir(idea_id, "short")
                                                           + "/video.mp4", _ROOT))
            print(f"· {idea_id}: companion short short_awaiting_approval")
        else:
            q.update_idea(idea_id, short_status="short_qc_failed")
            print(f"· {idea_id}: companion short short_qc_failed")
```
(and add `from engine import paths` + ensure `os` is imported at the top of run_auto.py — `os` already is; add `paths` if Task 6 of the Phase-1 work didn't already import it — it did: `from engine import paths`.)

## After this plan ships
The overnight `caffeinate` job (`run_auto --count 3`) will produce+render 3 longs + 3 cross-linked companion shorts → `awaiting_approval`; the AM `--approve <id>` uploads each long + its short (unlisted). Generate one sample companion short from an already-produced long (e.g. World Cup `46dbfcda`) to eyeball the output before the first overnight run.
