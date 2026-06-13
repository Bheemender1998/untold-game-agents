# Richer Short Descriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`).

**Goal:** Generate a purpose-written 2–3 sentence Short description (hook + intrigue) + tags from the clean script, replacing the broken `first_line + #Shorts` behaviour.

**Architecture:** A monkeypatch-able `_short_desc_llm` does one structured LLM call; `generate_short_metadata` assembles description + hashtags + tags around it with a self-stub fallback. `run_produce` calls it instead of the inline `_short_metadata`. Music credit stays owned by render-time `music.write_credit` (not duplicated here).

**Tech Stack:** Python 3, anthropic SDK (structured output), pytest.

**Reference spec:** `docs/superpowers/specs/2026-06-12-short-description-design.md`

---

## Task 1: `generate_short_metadata` + tests

**Files:**
- Modify: `engine/pipeline/metadata.py`
- Test: `tests/test_metadata.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metadata.py
from engine.pipeline import metadata


def test_generate_short_metadata_assembles_description(monkeypatch):
    monkeypatch.setattr(metadata, "_short_desc_llm",
                        lambda idea, script: ("A wet night in Monaco hid a scandal. One flag changed everything.",
                                              ["Senna", "Prost", "Monaco 1984"]))
    idea = {"title_variants": ["The Race That Was Stolen"], "sport": "F1", "pillar": "verdict_revisited"}
    m = metadata.generate_short_metadata(idea, "In the pouring rain of Monaco, 1984...")
    assert m["title"] == "The Race That Was Stolen"
    assert m["description"].startswith("A wet night in Monaco")
    assert "#Shorts #F1" in m["description"]
    assert "MOOD" not in m["description"] and "---" not in m["description"]
    assert m["tags"][0] == "Shorts" and "F1" in m["tags"] and "Senna" in m["tags"]
    assert len(m["tags"]) <= 30


def test_generate_short_metadata_falls_back_on_llm_error(monkeypatch):
    def boom(idea, script):
        raise RuntimeError("llm down")
    monkeypatch.setattr(metadata, "_short_desc_llm", boom)
    idea = {"title_variants": ["T"], "sport": "NFL", "pillar": "forgotten_figure"}
    m = metadata.generate_short_metadata(idea, "He walked away at his peak.\nMore text.")
    assert m["description"] == "He walked away at his peak.\n\n#Shorts #NFL"  # minimal fallback
    assert m["tags"] == ["Shorts", "NFL", "forgotten_figure"]
```

- [ ] **Step 2: Run — expect fail**

Run: `python3 -m pytest tests/test_metadata.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'generate_short_metadata'`

- [ ] **Step 3: Implement**

Append to `engine/pipeline/metadata.py` (it already imports `json`, `MODEL`; add `import anthropic` at top with the other imports):

```python
_SHORT_DESC_SYSTEM = """You write the description for a YouTube SHORT on a sports-history
channel. In 2-3 short sentences, hook the viewer and tease the intrigue — do NOT spoil the
ending or state the payoff. Plain text only: no markdown, no 'MOOD:' line, no hashtags, no
preamble or labels."""

_SHORT_DESC_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["description", "tags"],
    "additionalProperties": False,
}


def _short_desc_llm(idea: dict, script: str) -> tuple[str, list[str]]:
    """One structured call → (description, tags) for a Short. Raises on failure."""
    client = anthropic.Anthropic(max_retries=5)
    prompt = (f"TITLE: {idea['title_variants'][0]}\n"
              f"SPORT: {idea.get('sport','')}  PILLAR: {idea.get('pillar','')}\n\n"
              f"SCRIPT:\n{script}\n\nWrite the Short description and tags.")
    resp = client.messages.create(
        model=MODEL, max_tokens=512, system=_SHORT_DESC_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _SHORT_DESC_SCHEMA}},
    )
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return data["description"].strip(), list(data.get("tags", []))


def generate_short_metadata(idea: dict, script: str) -> dict:
    """Title + a purpose-written 2-3 sentence description + tags for a Short.
    Self-stubs to a minimal description (first clean line) if the LLM call fails. Music
    credit is added later at render time by engine.video.music.write_credit."""
    title = idea["title_variants"][0]
    sport = idea.get("sport", "")
    pillar = idea.get("pillar", "")
    try:
        body, llm_tags = _short_desc_llm(idea, script)
    except Exception:
        body = next((ln.strip() for ln in script.splitlines() if ln.strip()), title)
        llm_tags = []
    hashtags = "#Shorts" + (f" #{sport.replace(' ', '')}" if sport else "")
    description = f"{body}\n\n{hashtags}"
    tags = list(dict.fromkeys([t for t in ["Shorts", sport, pillar, *llm_tags] if t]))[:30]
    return {"title": title, "description": description, "tags": tags}
```

- [ ] **Step 4: Run — expect pass**

Run: `python3 -m pytest tests/test_metadata.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add engine/pipeline/metadata.py tests/test_metadata.py
git commit -m "feat(metadata): generate_short_metadata — hook+context+hashtags"
```

---

## Task 2: Wire `run_produce` to the new generator

**Files:**
- Modify: `engine/run_produce.py` (delete `_short_metadata`, call `metadata.generate_short_metadata`)

- [ ] **Step 1: Find the `_short_metadata` call site**

Run: `grep -n "_short_metadata\|generate_metadata\|from engine.pipeline.metadata" engine/run_produce.py`
Expected: the import line and the call inside `produce` (short branch).

- [ ] **Step 2: Make the change**

In `engine/run_produce.py`: change the import to also bring in the new function —
`from engine.pipeline.metadata import generate_metadata, generate_short_metadata` — and in
`produce`, replace the short-path metadata line `meta = _short_metadata(idea, script)` with
`meta = generate_short_metadata(idea, script)`. Delete the now-unused `_short_metadata`
function (lines ~48-55).

- [ ] **Step 3: Run the suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add engine/run_produce.py
git commit -m "feat(metadata): shorts use generate_short_metadata"
```

---

## Task 3: Backfill the 5 shorts + fix Senna live

**Files:** none (data + API).

- [ ] **Step 1: Regenerate metadata for the 5 shorts (cheap, reuses clean scripts)**

```bash
for id in 0eaa1b66 5b98b1fc a31759e2 0c76c4c4 46dbfcda; do
  python3 -m engine.run_produce --id $id --short --metadata-only --no-factcheck
done
```

Verify no scaffolding leaked:
`python3 -c "import json; [print(id, repr(json.load(open(f'produced/{id}/metadata.json'))['description'][:60])) for id in ['0eaa1b66','5b98b1fc','a31759e2','0c76c4c4','46dbfcda']]"`
Expected: each description starts with real sentence text, not `MOOD:`/`---`/`All facts`.

- [ ] **Step 2: Update Senna's already-uploaded video (unlisted) with the new metadata**

```bash
python3 - <<'PY'
import json
from engine.publish import auth
yt = auth.get_service()
vid = "yhClmmEGEHM"  # Senna (0c76c4c4)
m = json.load(open("produced/0c76c4c4/metadata.json"))
yt.videos().update(part="snippet", body={"id": vid, "snippet": {
    "title": m["title"], "description": m["description"],
    "tags": m.get("tags", []), "categoryId": "17"}}).execute()  # 17 = Sports
print("updated", vid)
PY
```

- [ ] **Step 3: Upload the other 4 as unlisted (user-authorized)**

```bash
for id in 46dbfcda 0eaa1b66 5b98b1fc a31759e2; do
  python3 -m engine.run_auto --approve $id
done
```

Expected: 4 `https://youtu.be/...` links; statuses → `published` (unlisted).

---

## Self-Review Notes

- **Spec coverage:** generator → Task 1; wiring → Task 2; backfill + Senna live-update + upload rest → Task 3. Music credit deliberately left to render-time `write_credit` (noted in spec §error-handling / here).
- **Self-stub:** LLM failure → minimal description; no crash.
- **No scaffolding:** description comes from the clean script + LLM (prompt bans MOOD/preamble); tags deduped ≤30.
