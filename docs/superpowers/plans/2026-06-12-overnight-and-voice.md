# Overnight Automation (A) + Narration Voice (C) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the produce→render→QC pipeline unattended at 01:00 (waking to videos in `awaiting_approval`), and replace the sharp single narration voice with a calmer, content-aware voice rotation.

**Architecture:** C is a small config + `tts.py` change resolving a Kokoro voice from the idea's mood (explicit `mood`, else pillar-derived), at speed 0.9. A is a launchd agent firing `scripts/overnight.sh`, which loads env, tops up the queue (`run_pipeline --no-review`), runs `run_auto --count 3`, logs to a dated file, and fires a macOS notification with a status summary returned by `run_auto.pipeline()`.

**Tech Stack:** Python 3 (main env), Kokoro TTS (in `.venv-video`, shelled by `run_auto`), launchd, `osascript`, pytest.

**Scope:** Projects A + C from `docs/superpowers/specs/2026-06-12-overnight-and-shorts-design.md`. B (Shorts) and D (thumbnails) are separate plans.

**Conventions:** `python3` only. Absolute `engine.*` imports. Run `python3 -m pytest tests/ -q` after each `engine/**.py` edit (the PostToolUse hook also runs it). Work on a feature branch — never `main`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `engine/config.py` | narration voice/speed/gap + mood maps | Modify (append a section) |
| `engine/video/tts.py` | voice resolution helpers + thread speed/gap into Kokoro | Modify |
| `engine/run_video.py:84` | use the resolved voice when synthesizing narration | Modify (1 line region) |
| `engine/run_auto.py` | `pipeline()` returns a status `Counter`; `_summary_message`, `_notify`; `main` notifies | Modify |
| `tests/test_tts.py` | unit tests for voice resolution (pure, no numpy) | Create |
| `tests/test_run_auto.py` | tests for summary/counter/notify | Modify (append) |
| `scripts/overnight.sh` | launchd wrapper: env + ideate + run_auto + log | Create |
| `deploy/launchd/com.untoldgame.overnight.plist` | launchd schedule (01:00 daily) | Create |
| `deploy/launchd/README.md` | install/uninstall instructions | Create |

---

## Project C — Narration voice

### Task C1: Config — voice/speed/gap + mood maps

**Files:**
- Modify: `engine/config.py` (append after the video-length section, ~line 73)
- Test: `tests/test_tts.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_tts.py`:

```python
from engine import config
from engine.taxonomy.pillars import PILLARS


def test_voice_map_covers_the_four_moods():
    for mood in ("triumphant", "hype", "tense", "somber"):
        assert config.NARRATION_VOICE_BY_MOOD[mood]


def test_every_pillar_maps_to_a_known_mood():
    for pillar in PILLARS:
        mood = config.PILLAR_MOOD[pillar]
        assert mood in config.NARRATION_VOICE_BY_MOOD


def test_narration_speed_is_calmer_than_default():
    assert 0.7 <= config.NARRATION_SPEED < 1.0
    assert config.NARRATION_GAP_S >= 0.4
```

- [ ] **Step 2: Run it — expect failure**

Run: `python3 -m pytest tests/test_tts.py -q`
Expected: FAIL — `AttributeError: module 'engine.config' has no attribute 'NARRATION_VOICE_BY_MOOD'`.

- [ ] **Step 3: Add the config**

Append to `engine/config.py`:

```python
# ── Narration voice (TTS) ─────────────────────────────────────────────────────
# Calmer, content-aware delivery. The voice rotates by story "mood"; long-form has
# no per-script mood, so it derives one from the idea's pillar. Voice names are
# Kokoro voices (see engine/video/tts.py).
NARRATION_SPEED = 0.9            # kokoro speed; <1.0 = slower, calmer
NARRATION_GAP_S = 0.5           # silence between sentences (seconds)
NARRATION_VOICE_DEFAULT = "bm_george"
NARRATION_VOICE_BY_MOOD = {
    "triumphant": "bm_george",  # authoritative for the payoff
    "hype":       "bm_george",  # drives energy
    "tense":      "bm_lewis",   # measured, investigative
    "somber":     "bf_emma",    # warm, gentle for loss
}
# Map the 6 content pillars → a mood, so long-form narration picks a voice too.
PILLAR_MOOD = {
    "hidden_story":                    "tense",
    "moments_that_changed_everything": "triumphant",
    "forgotten_figure":                "somber",
    "verdict_revisited":               "tense",
    "sport_vs_world":                  "tense",
    "what_if":                         "hype",
}
```

- [ ] **Step 4: Run it — expect pass**

Run: `python3 -m pytest tests/test_tts.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/config.py tests/test_tts.py
git commit -m "feat(tts): config for content-aware narration voice/speed/gap"
```

---

### Task C2: `tts.py` — voice resolution helpers + speed/gap threading

**Files:**
- Modify: `engine/video/tts.py`
- Test: `tests/test_tts.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tts.py`:

```python
from engine.video import tts


def test_resolve_voice_maps_mood():
    assert tts.resolve_voice("tense") == "bm_lewis"
    assert tts.resolve_voice("somber") == "bf_emma"


def test_resolve_voice_defaults_on_unknown_or_empty():
    assert tts.resolve_voice("") == config.NARRATION_VOICE_DEFAULT
    assert tts.resolve_voice(None) == config.NARRATION_VOICE_DEFAULT
    assert tts.resolve_voice("nonsense") == config.NARRATION_VOICE_DEFAULT


def test_mood_for_pillar():
    assert tts.mood_for_pillar("verdict_revisited") == "tense"
    assert tts.mood_for_pillar("what_if") == "hype"
    assert tts.mood_for_pillar(None) == ""


def test_narration_voice_prefers_explicit_mood_then_pillar():
    assert tts.narration_voice({"mood": "somber"}) == "bf_emma"
    assert tts.narration_voice({"pillar": "what_if"}) == "bm_george"
    assert tts.narration_voice({"mood": "tense", "pillar": "what_if"}) == "bm_lewis"


def test_narration_voice_override_wins():
    assert tts.narration_voice({"mood": "somber"}, override="af_sky") == "af_sky"


def test_narration_voice_none_for_non_kokoro_provider():
    # `say` has its own voice (Daniel) — don't hand it a Kokoro voice name.
    assert tts.narration_voice({"mood": "somber"}, provider="say") is None


def test_narration_voice_default_when_no_signal():
    assert tts.narration_voice({}) == config.NARRATION_VOICE_DEFAULT
```

- [ ] **Step 2: Run it — expect failure**

Run: `python3 -m pytest tests/test_tts.py -q`
Expected: FAIL — `AttributeError: module 'engine.video.tts' has no attribute 'resolve_voice'`.

- [ ] **Step 3: Add the helpers to `tts.py`**

At the top of `engine/video/tts.py`, after the existing imports (after `import tempfile`), add:

```python
from engine import config
```

Then add these functions just below the `script_to_narration_text` function (before the `# ── Provider selection ──` comment):

```python
# ── Voice selection (content-aware) ──────────────────────────────────────────

def resolve_voice(mood: str | None) -> str:
    """Kokoro voice for a story mood; falls back to the default voice."""
    return config.NARRATION_VOICE_BY_MOOD.get(mood or "", config.NARRATION_VOICE_DEFAULT)


def mood_for_pillar(pillar: str | None) -> str:
    """Mood for a content pillar (long-form has no per-script mood). '' if unknown."""
    return config.PILLAR_MOOD.get(pillar or "", "")


def narration_voice(idea: dict, override: str | None = None,
                    provider: str = "kokoro") -> str | None:
    """Pick the narration voice for an idea. An explicit `override` always wins.
    Non-kokoro providers keep their own default voice (return None). Otherwise the
    voice comes from the idea's explicit `mood`, else its pillar-derived mood."""
    if override:
        return override
    if provider != "kokoro":
        return None
    mood = idea.get("mood") or mood_for_pillar(idea.get("pillar"))
    return resolve_voice(mood)
```

- [ ] **Step 4: Thread speed/gap into Kokoro synthesis**

In `engine/video/tts.py`, change `synthesize` to accept and forward `speed`/`gap_s`:

```python
def synthesize(text: str, out_path: str, provider: str | None = None,
               voice: str | None = None, speed: float | None = None,
               gap_s: float | None = None) -> str:
    """Render narration `text` to a wav at out_path. Returns out_path.

    provider: 'kokoro' | 'say' | None (auto). Raises if the chosen provider can't run.
    speed/gap_s: kokoro only (None → config defaults).
    """
    provider = provider or available_provider()
    if provider == "kokoro":
        return _synth_kokoro(text, out_path, voice, speed, gap_s)
    if provider == "say":
        return _synth_say(text, out_path, voice)
    raise RuntimeError(
        "No TTS provider available. Install kokoro-onnx (`pip install kokoro-onnx`) "
        "or run on macOS (built-in `say` + ffmpeg)."
    )
```

Then update `_synth_kokoro`'s signature and body to use them (replace the current
`voice = voice or "af_sarah"`, the hardcoded `0.4` gap, and the `speed=1.0` call):

```python
def _synth_kokoro(text: str, out_path: str, voice: str | None,
                  speed: float | None = None, gap_s: float | None = None) -> str:
    """kokoro-onnx narration. Splits long text into sentences and concatenates so we
    don't blow the per-call length limit; writes a 24kHz wav."""
    import numpy as np
    import soundfile as sf
    from kokoro_onnx import Kokoro

    if not (os.path.exists(_KOKORO_MODEL) and os.path.exists(_KOKORO_VOICES)):
        raise RuntimeError(
            "Kokoro model files missing. Download kokoro-v0_19.onnx + voices.bin "
            f"into {_MODELS_DIR}/ (or set KOKORO_MODEL / KOKORO_VOICES). "
            "See https://github.com/thewh1teagle/kokoro-onnx."
        )
    voice = voice or config.NARRATION_VOICE_DEFAULT
    speed = config.NARRATION_SPEED if speed is None else speed
    gap_s = config.NARRATION_GAP_S if gap_s is None else gap_s
    kokoro = Kokoro(_KOKORO_MODEL, _KOKORO_VOICES)

    sample_rate = 24000
    gap = np.zeros(int(gap_s * sample_rate), dtype=np.float32)   # pause between sentences
    chunks: list = []
    for sent in _split_sentences(text):
        samples, sr = kokoro.create(sent, voice=voice, speed=speed, lang="en-us")
        sample_rate = sr
        chunks.append(np.asarray(samples, dtype=np.float32))
        chunks.append(gap)
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    sf.write(out_path, audio, sample_rate)
    return out_path
```

> Note: `_synth_kokoro` imports numpy/soundfile/kokoro_onnx, which live only in
> `.venv-video`, so it is NOT unit-tested under `python3`. The pure helpers in Step 3
> are the tested contract; the speed/gap wiring is verified by the manual smoke in Step 6.

- [ ] **Step 5: Run the tests — expect pass**

Run: `python3 -m pytest tests/test_tts.py -q`
Expected: PASS (all voice-resolution tests).

- [ ] **Step 6: Manual Kokoro smoke (in `.venv-video`)**

Run:
```bash
.venv-video/bin/python -c "
from engine.video import tts
tts.synthesize('On the first day of May, 1994, the world held its breath.',
               'voice_samples/smoke.wav', provider='kokoro',
               voice=tts.narration_voice({'pillar':'forgotten_figure'}))
print('voice:', tts.narration_voice({'pillar':'forgotten_figure'}))
"
```
Expected: prints `voice: bf_emma`, writes `voice_samples/smoke.wav` (a calm bf_emma clip).

- [ ] **Step 7: Commit**

```bash
git add engine/video/tts.py tests/test_tts.py
git commit -m "feat(tts): resolve narration voice by mood; thread speed/gap"
```

---

### Task C3: Wire the resolved voice into `run_video`

**Files:**
- Modify: `engine/run_video.py` (the narrated-mode synth call, ~line 84)

- [ ] **Step 1: Make the edit**

In `engine/run_video.py`, find (~line 84):

```python
                tts.synthesize(narration_text, audio_path, provider=args.tts, voice=args.voice)
```

Replace with:

```python
                voice = tts.narration_voice(idea, override=args.voice, provider=provider)
                tts.synthesize(narration_text, audio_path, provider=args.tts, voice=voice)
```

(`provider` is already computed two lines above at `provider = args.tts or tts.available_provider()`; `idea` is already in scope.)

- [ ] **Step 2: Run the suite — nothing should break**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (the hook runs this automatically too).

- [ ] **Step 3: Commit**

```bash
git add engine/run_video.py
git commit -m "feat(video): narration voice follows the idea's mood/pillar"
```

---

## Project A — Overnight automation

### Task A1: `run_auto.pipeline()` returns a status summary

**Files:**
- Modify: `engine/run_auto.py`
- Test: `tests/test_run_auto.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_auto.py`:

```python
from collections import Counter


def test_pipeline_returns_status_counter(monkeypatch):
    idea = {"id": "x", "status": "in_production", "human_reviewed": False}
    _stub_pipeline(monkeypatch, idea, qc_pass=True)
    result = run_auto.pipeline(count=1, no_render=False)
    assert isinstance(result, Counter)
    assert result["awaiting_approval"] == 1


def test_summary_message_lists_counts():
    msg = run_auto._summary_message(Counter({"awaiting_approval": 2, "qc_failed": 1}))
    assert "2 awaiting_approval" in msg
    assert "1 qc_failed" in msg


def test_summary_message_handles_empty():
    assert run_auto._summary_message(Counter()) == "No ideas produced."
```

> `_stub_pipeline` already stubs `q.get_by_id` to return `idea`. For the counter,
> `pipeline` reads the idea's final status after processing; since the stub leaves
> `idea["status"]` as `"in_production"` but QC sets `awaiting_approval` via
> `update_idea` (captured in `seen`, not written back to `idea`), update the helper:
> in `_stub_pipeline`, change the `update_idea` stub to also mutate `idea`:
> `monkeypatch.setattr(run_auto.q, "update_idea", lambda i, **f: (seen.update(f), idea.update(f)))`.
> Make that one-line change to the existing `_stub_pipeline` helper.

- [ ] **Step 2: Run it — expect failure**

Run: `python3 -m pytest tests/test_run_auto.py -q`
Expected: FAIL — `AttributeError: module 'engine.run_auto' has no attribute '_summary_message'` (and the counter assertion).

- [ ] **Step 3: Implement**

In `engine/run_auto.py`, add `from collections import Counter` at the top with the other imports. Change `pipeline` to accumulate and return a `Counter`:

```python
def pipeline(count: int, no_render: bool) -> Counter:
    """Produce → (render → QC) for the top-`count` pending ideas. One failure never
    aborts the batch. Returns a Counter of each idea's final status."""
    results: Counter = Counter()
    for idea in _select(count):
        idea_id = idea["id"]
        try:
            _produce_one(idea_id)
            current = q.get_by_id(idea_id) or {}
            if not _cleared_to_render(current):
                print(f"· {idea_id}: not cleared ({current.get('status')}) — skipping")
                continue
            if no_render:
                print(f"· {idea_id}: cleared (--no-render, stopping before render)")
                continue
            _render_and_qc(idea_id)
        except Exception as e:  # never abort the batch
            print(f"! {idea_id}: error {e}")
        results[(q.get_by_id(idea_id) or {}).get("status", "unknown")] += 1
    return results


def _summary_message(counter: Counter) -> str:
    """Human one-liner for the overnight notification."""
    if not counter:
        return "No ideas produced."
    total = sum(counter.values())
    parts = ", ".join(f"{n} {status}" for status, n in counter.most_common())
    return f"{total} produced: {parts}"
```

- [ ] **Step 4: Run the tests — expect pass**

Run: `python3 -m pytest tests/test_run_auto.py -q`
Expected: PASS (existing tests + 3 new).

- [ ] **Step 5: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto.py
git commit -m "feat(run_auto): pipeline returns a status Counter + summary message"
```

---

### Task A2: macOS notification + `main` wiring

**Files:**
- Modify: `engine/run_auto.py`
- Test: `tests/test_run_auto.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_auto.py`:

```python
def test_notify_invokes_osascript(monkeypatch):
    calls = {}
    monkeypatch.setattr(run_auto.subprocess, "run",
                        lambda cmd, **k: calls.setdefault("cmd", cmd))
    run_auto._notify("3 produced: 2 awaiting_approval")
    assert calls["cmd"][0] == "osascript"
    assert any("3 produced" in str(part) for part in calls["cmd"])


def test_notify_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("no osascript")
    monkeypatch.setattr(run_auto.subprocess, "run", boom)
    run_auto._notify("anything")  # must not raise
```

- [ ] **Step 2: Run it — expect failure**

Run: `python3 -m pytest tests/test_run_auto.py -q`
Expected: FAIL — `AttributeError: ... has no attribute '_notify'`.

- [ ] **Step 3: Implement `_notify` and wire `main`**

In `engine/run_auto.py`, add `_notify` (near `_summary_message`):

```python
def _notify(message: str, title: str = "The Untold Game — overnight") -> None:
    """Best-effort macOS Notification Center banner. Never raises (notification
    failure must not fail an otherwise-good overnight run)."""
    try:
        subprocess.run(
            ["osascript", "-e",
             f"display notification {json.dumps(message)} with title {json.dumps(title)}"],
            check=False,
        )
    except Exception:
        pass
```

In `main()`, replace the final `else` branch:

```python
    else:
        results = pipeline(count=args.count, no_render=args.no_render)
        if not args.no_render:
            _notify(_summary_message(results))
```

(`json` and `subprocess` are already imported at the top of the file.)

- [ ] **Step 4: Run the tests — expect pass**

Run: `python3 -m pytest tests/test_run_auto.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/run_auto.py tests/test_run_auto.py
git commit -m "feat(run_auto): macOS notification with overnight summary"
```

---

### Task A3: The launchd wrapper script

**Files:**
- Create: `scripts/overnight.sh`

- [ ] **Step 1: Create the wrapper**

Create `scripts/overnight.sh`:

```bash
#!/usr/bin/env bash
# Overnight unattended render. Fired by launchd (com.untoldgame.overnight) at 01:00.
# launchd hands us a minimal environment, so set PATH and load .env explicitly —
# this is the #1 thing that breaks unattended macOS jobs.
set -uo pipefail

REPO="/Users/bheemendergurram/untold_game_agents"
cd "$REPO" || exit 1

# node/npx (Remotion render) + homebrew + system tools. Render is shelled by run_auto
# into .venv-video, which inherits this PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
[ -f .env ] && set -a && . ./.env && set +a

mkdir -p logs
LOG="logs/overnight-$(date +%Y-%m-%d).log"

{
  echo "=== overnight run $(date) ==="
  echo "-- ideate: top up the queue (headless) --"
  python3 -m engine.run_pipeline --no-review || echo "(ideate failed — non-fatal, continuing)"
  echo "-- produce + render + QC (count=3) --"
  python3 -m engine.run_auto --count 3
  echo "=== done $(date) ==="
} >>"$LOG" 2>&1
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/overnight.sh
```

- [ ] **Step 3: Dry smoke (no render — proves env + wiring without a 45-min render)**

Run a temporary no-render variant to confirm the env loads and the queue is reachable:
```bash
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" bash -c '
  cd /Users/bheemendergurram/untold_game_agents
  [ -f .env ] && set -a && . ./.env && set +a
  python3 -m engine.run_auto --count 1 --no-render
'
```
Expected: prints a `· <id>: cleared (--no-render, …)` or `not cleared` line and exits 0 — no traceback. (This confirms `.env`/imports work under a minimal PATH.)

- [ ] **Step 4: Commit**

```bash
git add scripts/overnight.sh
git commit -m "feat(overnight): launchd wrapper — env + ideate + run_auto + log"
```

---

### Task A4: launchd plist + install doc

**Files:**
- Create: `deploy/launchd/com.untoldgame.overnight.plist`
- Create: `deploy/launchd/README.md`

- [ ] **Step 1: Create the plist**

Create `deploy/launchd/com.untoldgame.overnight.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.untoldgame.overnight</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/bheemendergurram/untold_game_agents/scripts/overnight.sh</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>1</integer>
    <key>Minute</key><integer>0</integer>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/bheemendergurram/untold_game_agents/logs/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/bheemendergurram/untold_game_agents/logs/launchd.err.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

- [ ] **Step 2: Create the install doc**

Create `deploy/launchd/README.md`:

```markdown
# Overnight render — launchd install

Schedules `scripts/overnight.sh` at **01:00 daily** on this Mac (render is local; Railway
can't run the 45-min Chromium render).

## Install
```bash
cp deploy/launchd/com.untoldgame.overnight.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.untoldgame.overnight.plist
launchctl list | grep untoldgame   # confirm it's registered
```

## Run it now (test, without waiting for 01:00)
```bash
launchctl start com.untoldgame.overnight
tail -f logs/overnight-$(date +%Y-%m-%d).log
```

## Uninstall
```bash
launchctl unload ~/Library/LaunchAgents/com.untoldgame.overnight.plist
rm ~/Library/LaunchAgents/com.untoldgame.overnight.plist
```

## Notes
- If the Mac is **asleep** at 01:00, launchd fires on the next wake, not at 01:00. To
  guarantee a wall-clock run, schedule a wake: `sudo pmset repeat wake MTWRFSU 00:55:00`.
- Logs: per-day `logs/overnight-YYYY-MM-DD.log` (full transcript) + `logs/launchd.{out,err}.log`.
- A macOS notification fires on completion with the produced-status summary.
```

- [ ] **Step 3: Commit**

```bash
git add deploy/launchd/
git commit -m "feat(overnight): launchd plist (01:00 daily) + install doc"
```

---

## Self-Review notes
- **Spec coverage (A):** 01:00 launchd ✓ (A4), ideate top-up ✓ (A3 `--no-review`), produce+render+QC×3 ✓ (A3 reuses `run_auto`), dated log ✓ (A3), macOS notification ✓ (A2), no auto-publish ✓ (nothing calls `cmd_approve`).
- **Spec coverage (C):** softer voice ✓ (speed 0.9), content-aware rotation by mood ✓ (C1 maps), long-form mood from pillar ✓ (`mood_for_pillar`), applies to long + short ✓ (shared `tts.synthesize`), self-stub default voice ✓ (`resolve_voice` fallback).
- **Not unit-tested by design:** `_synth_kokoro` (numpy/kokoro live in `.venv-video`, not the `python3` test env) — covered by the C2 manual smoke. `scripts/overnight.sh` and the plist (bash/launchd) — covered by the A3 dry smoke and A4 `launchctl start`.
- **Out of scope here:** wiring Shorts/thumbnails into the cron, wall-clock wake guarantee (documented in A4 README), `say`-provider speed (kokoro is the quality path).
