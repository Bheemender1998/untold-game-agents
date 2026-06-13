# Channel Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate the "Editorial Archive" channel banner (Pillow) + lock the channel positioning copy/config, applied manually in YouTube Studio.

**Architecture:** A deterministic Pillow banner generator (`engine/pipeline/banner.py`) reusing the shipped thumbnail engine's bundled Anton font + `RED` and the same grain/vignette primitives, plus a new bundled Playfair Display *Italic* for the subtitle. Textural backdrop (no photo). Positioning copy ("The Archive of Lost Sports History", channel description) lives in `config`/`channel.yaml` as the source of truth; the banner reads it. A CLI emits the banner PNG + description text for manual upload.

**Tech Stack:** Python 3 (main env), Pillow (already a dependency), bundled OFL fonts.

Spec: `docs/superpowers/specs/2026-06-13-channel-positioning-design.md`

---

## File Structure
- `engine/pipeline/assets/fonts/PlayfairDisplay-Italic.ttf` — new bundled OFL font (subtitle).
- `engine/config.py` — `CHANNEL_NAME`, `CHANNEL_SUBTITLE`, `CHANNEL_DESCRIPTION`; edit the `Tagline:` line in `CHANNEL_CONTEXT`.
- `engine/profiles/channel.yaml` — `tagline` + `description`.
- `engine/paths.py` — `CHANNEL_DIR`, `channel_banner_path`, `channel_description_path`.
- `.gitignore` — `channel/`.
- `engine/pipeline/banner.py` — `_gradient`, `_layout_banner`, `compose_banner`.
- `engine/run_banner.py` — CLI.
- Tests: `tests/test_banner.py`, `tests/test_config_positioning.py`, `tests/test_paths.py` (append).

Canonical line (used verbatim everywhere): **The Archive of Lost Sports History**

---

## Task 1: Bundle Playfair Display Italic font

**Files:** Create `engine/pipeline/assets/fonts/PlayfairDisplay-Italic.ttf`; Test `tests/test_banner.py`.

- [ ] **Step 1: Download + commit the italic font**

```bash
cd engine/pipeline/assets/fonts
curl -fsSL -o "PlayfairDisplay-Italic.ttf" "https://raw.githubusercontent.com/google/fonts/main/ofl/playfairdisplay/PlayfairDisplay-Italic%5Bwght%5D.ttf"
cd -
python3 -c "from PIL import ImageFont; ImageFont.truetype('engine/pipeline/assets/fonts/PlayfairDisplay-Italic.ttf', 50); print('italic ok')"
```
Expected: prints `italic ok` and the file is > 20 KB. The existing `OFL-PlayfairDisplay.txt` license already covers it (same family). If the download fails, STOP and report BLOCKED — do not fabricate a font.

- [ ] **Step 2: Write the failing test.** Create `tests/test_banner.py`:
```python
import os
from PIL import ImageFont
from engine.pipeline import banner


def test_subtitle_font_loads():
    assert os.path.exists(banner.SUBTITLE_FONT), f"missing: {banner.SUBTITLE_FONT}"
    ImageFont.truetype(banner.SUBTITLE_FONT, 50)
```

- [ ] **Step 3: Run, verify FAIL:** `python3 -m pytest tests/test_banner.py -v` (expect: no module `engine.pipeline.banner`).

- [ ] **Step 4: Create `engine/pipeline/banner.py` with just the font wiring (rest added in Task 4):**
```python
"""Stage 2 — BANNER: deterministic Pillow generator for the channel's
"Editorial Archive" banner (textural backdrop + wordmark + rule + subtitle)."""
from __future__ import annotations
import os

from engine.pipeline import thumbnail

_FONTS = os.path.dirname(thumbnail.TENSION_FONT)
WORDMARK_FONT = thumbnail.TENSION_FONT                       # Anton (reused)
SUBTITLE_FONT = os.path.join(_FONTS, "PlayfairDisplay-Italic.ttf")
RED = thumbnail.RED
```

- [ ] **Step 5: Run, verify PASS:** `python3 -m pytest tests/test_banner.py -v`

- [ ] **Step 6: Commit.** FIRST `git branch --show-current` MUST be `feat/channel-positioning` (else STOP/BLOCKED). Then:
```bash
git add engine/pipeline/assets/fonts/PlayfairDisplay-Italic.ttf engine/pipeline/banner.py tests/test_banner.py
git commit -m "feat(banner): bundle Playfair Display Italic + banner module font wiring"
```

---

## Task 2: Positioning copy + config/profile sync

**Files:** Modify `engine/config.py`, `engine/profiles/channel.yaml`; Test `tests/test_config_positioning.py`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_config_positioning.py`:
```python
from engine import config


def test_channel_constants():
    assert config.CHANNEL_NAME == "The Untold Game"
    assert config.CHANNEL_SUBTITLE == "The Archive of Lost Sports History"


def test_description_leads_with_canonical_line():
    assert config.CHANNEL_DESCRIPTION.strip().startswith(
        "The Untold Game — The Archive of Lost Sports History.")
    assert "30-for-30" in config.CHANNEL_DESCRIPTION
    assert "@untoldgamemedia" in config.CHANNEL_DESCRIPTION


def test_canonical_tagline_in_agent_context():
    # the positioning line is canonical in the agent-facing channel context
    assert "The Archive of Lost Sports History" in config.CHANNEL_CONTEXT


def test_channel_yaml_carries_canonical_tagline():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(config.__file__)))
    text = open(os.path.join(root, "engine", "profiles", "channel.yaml")).read()
    assert "The Archive of Lost Sports History" in text
```

- [ ] **Step 2: Run, verify FAIL:** `python3 -m pytest tests/test_config_positioning.py -v`

- [ ] **Step 3: Edit `engine/config.py`.** Change the tagline line inside `CHANNEL_CONTEXT`. Find:
```python
Tagline: "The stories they forgot to tell you"
```
Replace with:
```python
Tagline: "The Archive of Lost Sports History"
```
Then, immediately after the `CHANNEL_HANDLE = "@untoldgamemedia"` line, add:
```python
# Channel positioning (banner + public "About"; source of truth for engine.pipeline.banner).
CHANNEL_NAME = "The Untold Game"
CHANNEL_SUBTITLE = "The Archive of Lost Sports History"
CHANNEL_DESCRIPTION = """The Untold Game — The Archive of Lost Sports History.
Premium, heavily researched documentaries on the forgotten, buried, and deliberately overlooked stories behind the world's biggest games — F1, football, cricket, the NFL, and beyond. Cinematic, told in a 30-for-30 voice. Every claim verified; nothing sensationalized.
▶ New untold stories regularly. Subscribe → @untoldgamemedia"""
```

- [ ] **Step 4: Edit `engine/profiles/channel.yaml`.** Find:
```yaml
  tagline: "The stories they forgot to tell you"
```
Replace with:
```yaml
  tagline: "The Archive of Lost Sports History"
  description: >
    The Untold Game — The Archive of Lost Sports History. Premium, heavily
    researched documentaries on the forgotten, buried, and deliberately
    overlooked stories behind the world's biggest games — F1, football, cricket,
    the NFL, and beyond. Cinematic, told in a 30-for-30 voice. Every claim
    verified; nothing sensationalized.
```

- [ ] **Step 5: Run, verify PASS:** `python3 -m pytest tests/test_config_positioning.py -v`

- [ ] **Step 6: Commit.** FIRST verify branch is `feat/channel-positioning`. Then:
```bash
git add engine/config.py engine/profiles/channel.yaml tests/test_config_positioning.py
git commit -m "feat(positioning): canonical 'Archive of Lost Sports History' line in config + profile"
```

---

## Task 3: Channel asset paths + gitignore

**Files:** Modify `engine/paths.py`, `.gitignore`; Test `tests/test_paths.py` (append).

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_paths.py`:
```python
def test_channel_paths():
    import os
    from engine import paths
    assert paths.channel_banner_path() == os.path.join(paths.CHANNEL_DIR, "banner.png")
    assert paths.channel_description_path() == os.path.join(paths.CHANNEL_DIR, "description.txt")
```

- [ ] **Step 2: Run, verify FAIL:** `python3 -m pytest tests/test_paths.py -k channel_paths -v`

- [ ] **Step 3: Append to `engine/paths.py`:**
```python
# Channel-level (not per-idea) assets: the generated banner + description for manual upload.
CHANNEL_DIR = os.path.join(_ROOT, "channel")


def channel_banner_path() -> str:
    return os.path.join(CHANNEL_DIR, "banner.png")


def channel_description_path() -> str:
    return os.path.join(CHANNEL_DIR, "description.txt")
```

- [ ] **Step 4: Add `channel/` to `.gitignore`** (it's a regenerable build output; the copy's source of truth is `config`/`channel.yaml`). Append under the OS section:
```
# generated channel assets (regenerable via run_banner; source of truth is config/channel.yaml)
channel/
```

- [ ] **Step 5: Run, verify PASS:** `python3 -m pytest tests/test_paths.py -k channel_paths -v`

- [ ] **Step 6: Commit.** FIRST verify branch is `feat/channel-positioning`. Then:
```bash
git add engine/paths.py .gitignore tests/test_paths.py
git commit -m "feat(banner): channel asset paths + gitignore generated channel/"
```

---

## Task 4: Banner generator (`compose_banner` + `_layout_banner`)

**Files:** Modify `engine/pipeline/banner.py`; Test `tests/test_banner.py`.

Layout fits the wordmark to BOTH a width target and a height budget (the safe band minus the subtitle/rule/gaps), and fits the subtitle to width — so the stack is contained in the TV-safe band by construction.

- [ ] **Step 1: Write the failing tests.** Add to `tests/test_banner.py`:
```python
from PIL import Image, ImageDraw
from engine.pipeline import banner as bn


def test_compose_banner_writes_2560x1440_png(tmp_path):
    out = tmp_path / "banner.png"
    bn.compose_banner(str(out))
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (2560, 1440)
        assert im.format == "PNG"


def test_banner_block_within_tv_safe_area():
    d = ImageDraw.Draw(Image.new("RGB", (bn.W, bn.H)))
    L = bn._layout_banner(d)
    bx = L["block_box"]
    assert bx[0] >= bn.SAFE_LEFT and bx[2] <= bn.SAFE_LEFT + bn.SAFE_W
    assert bx[1] >= bn.SAFE_TOP and bx[3] <= bn.SAFE_TOP + bn.SAFE_H
```

- [ ] **Step 2: Run, verify FAIL:** `python3 -m pytest tests/test_banner.py -k "compose_banner or safe_area" -v` (expect: `compose_banner` / `W` not defined).

- [ ] **Step 3: Implement the generator in `engine/pipeline/banner.py`.** Add the imports + constants + functions (after the font wiring from Task 1):
```python
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from engine import config

W, H = 2560, 1440
SAFE_W, SAFE_H = 1546, 423                      # YouTube all-device-safe area
SAFE_LEFT, SAFE_TOP = (W - SAFE_W) // 2, (H - SAFE_H) // 2
WORDMARK_MAX = 220
SUB_SIZE = 52
RULE_H = 8
GAP = 24


def _gradient():
    """Warm archival horizontal gradient: lit warm at the left, dark at the right."""
    g = Image.linear_gradient("L").resize((W, H))           # 0 (left) -> 255 (right)
    return ImageOps.colorize(g, black=(74, 56, 38), white=(18, 12, 6))


def _layout_banner(draw):
    """Place the wordmark + red rule + subtitle, centred in the TV-safe band. The wordmark
    fits both the safe width and a height budget (safe band minus subtitle/rule/gaps), and the
    subtitle fits the safe width — so the whole block is contained in the safe area by
    construction. Returns the fonts, the per-element boxes, and the union block_box."""
    target_w = int(SAFE_W * 0.96)
    name = config.CHANNEL_NAME.upper()
    sub = config.CHANNEL_SUBTITLE

    # subtitle: fit to width
    sub_size = SUB_SIZE
    sf = ImageFont.truetype(SUBTITLE_FONT, sub_size)
    while sub_size > 20 and draw.textlength(sub, font=sf) > target_w:
        sub_size -= 2
        sf = ImageFont.truetype(SUBTITLE_FONT, sub_size)
    slh = sum(sf.getmetrics())

    # wordmark: fit to width AND to the remaining height budget
    wm_budget_h = SAFE_H - (slh + GAP + RULE_H + GAP) - 20
    wf = ImageFont.truetype(WORDMARK_FONT, 60)
    for size in range(WORDMARK_MAX, 58, -2):
        f = ImageFont.truetype(WORDMARK_FONT, size)
        if draw.textlength(name, font=f) <= target_w and sum(f.getmetrics()) <= wm_budget_h:
            wf = f
            break
    wlh = sum(wf.getmetrics())
    ww = draw.textlength(name, font=wf)
    sw = draw.textlength(sub, font=sf)
    rule_w = int(SAFE_W * 0.42)

    stack_h = wlh + GAP + RULE_H + GAP + slh
    top = SAFE_TOP + (SAFE_H - stack_h) // 2
    cx = W // 2
    wm_box = (cx - ww / 2, top, cx + ww / 2, top + wlh)
    rule_y = top + wlh + GAP
    rule_box = (cx - rule_w / 2, rule_y, cx + rule_w / 2, rule_y + RULE_H)
    sub_y = rule_y + RULE_H + GAP
    sub_box = (cx - sw / 2, sub_y, cx + sw / 2, sub_y + slh)
    block_box = (min(wm_box[0], rule_box[0], sub_box[0]), top,
                 max(wm_box[2], rule_box[2], sub_box[2]), sub_y + slh)
    return {"wf": wf, "sf": sf, "name": name, "sub": sub,
            "wm_box": wm_box, "rule_box": rule_box, "sub_box": sub_box, "block_box": block_box}


def compose_banner(out_path: str) -> None:
    """Render the 2560x1440 'Editorial Archive' channel banner to out_path (PNG)."""
    base = _gradient()
    noise = Image.effect_noise((W, H), 28).convert("RGB")
    img = Image.blend(base, noise, 0.06)
    vig = ImageOps.invert(Image.radial_gradient("L")).resize((W, H)).point(lambda v: int(70 + v * 0.72))
    img = ImageChops.multiply(img, Image.merge("RGB", (vig, vig, vig)))
    draw = ImageDraw.Draw(img)
    L = _layout_banner(draw)
    wm = L["wm_box"]
    draw.text((wm[0] + 3, wm[1] + 3), L["name"], font=L["wf"], fill=(0, 0, 0))      # shadow
    draw.text((wm[0], wm[1]), L["name"], font=L["wf"], fill=(255, 255, 255))
    draw.rectangle([int(v) for v in L["rule_box"]], fill=RED)
    sb = L["sub_box"]
    draw.text((sb[0], sb[1]), L["sub"], font=L["sf"], fill=(231, 220, 194))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG")
```

- [ ] **Step 4: Run, verify PASS:** `python3 -m pytest tests/test_banner.py -v` (all banner tests).

- [ ] **Step 5: Commit.** FIRST verify branch is `feat/channel-positioning`. Then:
```bash
git add engine/pipeline/banner.py tests/test_banner.py
git commit -m "feat(banner): Editorial Archive banner generator (2560x1440, safe-area-contained)"
```

---

## Task 5: `run_banner` CLI

**Files:** Create `engine/run_banner.py`; Test `tests/test_banner.py`.

- [ ] **Step 1: Write the failing test.** Add to `tests/test_banner.py`:
```python
def test_run_banner_writes_banner_and_description(tmp_path, monkeypatch):
    from engine import paths, config
    from engine import run_banner
    monkeypatch.setattr(paths, "CHANNEL_DIR", str(tmp_path / "channel"))
    run_banner.main()
    with Image.open(paths.channel_banner_path()) as im:
        assert im.size == (2560, 1440)
    assert open(paths.channel_description_path()).read().strip() == config.CHANNEL_DESCRIPTION.strip()
```

- [ ] **Step 2: Run, verify FAIL:** `python3 -m pytest tests/test_banner.py -k run_banner -v` (expect: no module `engine.run_banner`).

- [ ] **Step 3: Create `engine/run_banner.py`:**
```python
"""The Untold Game — BANNER stage entrypoint.

Generate the channel banner + write the channel description for manual upload.

Usage:
  python3 -m engine.run_banner
Then upload channel/banner.png as channel art and paste channel/description.txt
into the channel "About" in YouTube Studio.
"""
from __future__ import annotations
import os

from engine import config, paths
from engine.pipeline import banner


def main() -> None:
    banner.compose_banner(paths.channel_banner_path())
    desc_path = paths.channel_description_path()
    os.makedirs(os.path.dirname(desc_path) or ".", exist_ok=True)
    with open(desc_path, "w") as f:
        f.write(config.CHANNEL_DESCRIPTION.strip() + "\n")
    print(f"✓ banner      → {paths.channel_banner_path()}")
    print(f"✓ description → {desc_path}")
    print("Upload the banner as channel art and paste the description into 'About' in YouTube Studio.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, verify PASS:** `python3 -m pytest tests/test_banner.py -k run_banner -v`

- [ ] **Step 5: Run the FULL suite (the contract):** `python3 -m pytest tests/ -q` — all must pass, no regressions.

- [ ] **Step 6: Commit.** FIRST verify branch is `feat/channel-positioning`. Then:
```bash
git add engine/run_banner.py tests/test_banner.py
git commit -m "feat(banner): run_banner CLI — emit banner.png + description.txt"
```

---

## Manual application (after merge — not a coding task)
```bash
python3 -m engine.run_banner
```
Then in YouTube Studio: upload `channel/banner.png` as channel art, and paste `channel/description.txt` into the channel "About". One-time; re-run only when the positioning copy changes.
