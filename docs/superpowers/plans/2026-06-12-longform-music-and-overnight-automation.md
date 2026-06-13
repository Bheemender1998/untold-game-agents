# Phase 1 — Long-form Music + Overnight Automation — Plan

> Execute with superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Music on long-form renders + a 1 AM launchd job that produces/renders 3 long videos nightly.

**Spec:** `docs/superpowers/specs/2026-06-12-longform-music-and-overnight-automation-design.md`

---

## Task 1: Long-form mood fallback in music

**Files:** `engine/video/music.py`; `tests/test_music.py`.

- [ ] **Step 1: Failing test**

```python
def test_short_music_props_derives_pillar_mood_for_longform(tmp_path, monkeypatch):
    root = _seed_tree(tmp_path)           # 'tense' folder has tracks
    monkeypatch.setattr(music, "MUSIC_DIR", root)
    from engine.video import tts
    monkeypatch.setattr(tts, "mood_for_pillar", lambda p: "tense")
    frag, asset, credit = music.short_music_props({"id": "x", "pillar": "verdict_revisited"})  # no 'mood'
    assert asset is not None and frag["musicSrc"]
```

- [ ] **Step 2: run → fail** (no mood → no track).

- [ ] **Step 3: Implement** — in `short_music_props`, derive mood:

```python
    from engine.video import tts
    mood = idea.get("mood") or tts.mood_for_pillar(idea.get("pillar"))
    chosen = pick_track(mood, idea.get("id", ""), music_dir)
```

(replace the `chosen = pick_track(idea.get("mood") or "", ...)` line.)

- [ ] **Step 4: run → pass**; `python3 -m pytest tests/test_music.py -q`.

- [ ] **Step 5: Commit** `git add engine/video/music.py tests/test_music.py && git commit -m "feat(music): derive pillar mood so long-form gets a bed"`

---

## Task 2: build_props music for both formats

**Files:** `engine/video/remotion_build.py`; `tests/test_remotion_build.py`.

- [ ] **Step 1: Failing test (append)**

```python
def test_build_props_adds_music_for_longform(tmp_path, monkeypatch):
    _patch_heavy(monkeypatch)
    monkeypatch.setattr(music, "short_music_props",
                        lambda i, *a, **k: ({"musicSrc": "m.mp3", "musicVolume": 0.12}, "/lib/m.mp3", "Music"))
    idea = {"id": "i", "pillar": "verdict_revisited", "title_variants": ["T"]}
    props, assets, credit = remotion_build.build_props(idea, "# s\nb", str(tmp_path), "n.wav", None, 10.0, portrait=False)
    assert props["musicSrc"] == "m.mp3" and "/lib/m.mp3" in assets and credit == "Music"
```

- [ ] **Step 2: run → fail** (long-form returns no music today).

- [ ] **Step 3: Implement** — drop the `portrait` gate:

```python
    # Mood-matched background bed under the narration (both formats).
    music_credit = ""
    frag, music_asset, music_credit = _music.short_music_props(idea)
    if music_asset:
        props.update(frag)
        assets.append(music_asset)
    return props, assets, music_credit
```

- [ ] **Step 4: run full suite → pass** (the old `test_build_props_no_music_for_longform` asserted long-form had NO music — update it: with a mood-bearing pillar it now CAN; keep it asserting "no music when `short_music_props` returns nothing" by monkeypatching that to `({}, None, "")`).

- [ ] **Step 5: Commit** `git add engine/video/remotion_build.py tests/test_remotion_build.py && git commit -m "feat(music): bed on long-form too (drop portrait gate)"`

---

## Task 3: Music `<Audio>` in UntoldVideo.tsx

**Files:** `engine/video/remotion/src/UntoldVideo.tsx`.

- [ ] **Step 1: Add `interpolate` to the remotion import**, then add the bed inside the Narration Sequence (after the narration `<Audio>`):

```tsx
        {props.musicSrc ? (
          <Audio src={staticFile(props.musicSrc)} loop volume={(f) => {
            const peak = props.musicVolume ?? 0.12;
            const total = ms2f(props.introMs + props.narrationMs + props.outroMs, fps) - introF;
            const fadeIn = Math.round(1.5 * fps);
            const fadeOut = Math.round(2.5 * fps);
            return interpolate(f, [0, fadeIn, Math.max(fadeIn, total - fadeOut), total], [0, peak, peak, 0],
              {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
          }} />
        ) : null}
```

(The narration Sequence starts `from={introF}`, so subtract `introF` to get the bed length.)

- [ ] **Step 2: Type-check** `cd engine/video/remotion && npx --no-install tsc --noEmit` → no errors.

- [ ] **Step 3: Commit** `git add engine/video/remotion/src/UntoldVideo.tsx && git commit -m "feat(music): background bed under long-form narration"`

---

## Task 4: Overnight wrapper + launchd job

**Files:** Create `scripts/overnight.sh`; create the LaunchAgent plist; `.gitignore` the log.

- [ ] **Step 1: Wrapper**

```bash
mkdir -p scripts logs
cat > scripts/overnight.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
exec python3 -m engine.run_auto --count 3
SH
chmod +x scripts/overnight.sh
bash -n scripts/overnight.sh   # syntax check
```

- [ ] **Step 2: .gitignore the log** — append `logs/overnight.log` to `.gitignore`.

- [ ] **Step 3: Plist** (absolute repo path)

```bash
REPO="/Users/bheemendergurram/untold_game_agents"
PLIST="$HOME/Library/LaunchAgents/com.untoldgame.overnight.plist"
cat > "$PLIST" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.untoldgame.overnight</string>
  <key>ProgramArguments</key><array><string>$REPO/scripts/overnight.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>1</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$REPO/logs/overnight.log</string>
  <key>StandardErrorPath</key><string>$REPO/logs/overnight.log</string>
  <key>RunAtLoad</key><false/>
</dict></plist>
XML
plutil -lint "$PLIST"
```

- [ ] **Step 4: Load it** `launchctl unload "$PLIST" 2>/dev/null; launchctl load -w "$PLIST"; launchctl list | grep untoldgame`

- [ ] **Step 5: Dry-validate the wrapper path/env (no render)** `python3 -m engine.run_auto --count 1 --no-render` → produces 1 idea to `cleared`/`in_production` without rendering, proving env + imports resolve.

- [ ] **Step 6: Commit** `git add scripts/overnight.sh .gitignore && git commit -m "feat(auto): 1 AM launchd job — 3 long videos nightly"`

(The plist lives outside the repo in ~/Library/LaunchAgents — not committed; document it in the spec/HANDOFF.)

---

## Self-Review

- Spec coverage: 1a→T1, 1b→T2, 1c→T3, 2a/2b→T4. Music credit (1d) needs no change (write_credit already runs post-render).
- The `--no-render` dry pass (T4 S5) validates the automation path without a 45-min render; the real 3-video run is verified by morning artifacts.
