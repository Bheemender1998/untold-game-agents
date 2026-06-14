"""Auto-source a subject photo for a thumbnail: the person's Wikipedia lead image, else a
generic Pexels stock photo for a fallback concept. A human-supplied subject.png always wins.
Self-stubs on any failure — never crashes a run."""
from __future__ import annotations
import json
import os
import shutil
import urllib.request

import anthropic
from engine.config import MODEL
from engine import paths
from engine.ideate import wikipedia
from engine.video import footage

_SUBJECT_SYSTEM = """Identify the single best on-screen SUBJECT for a sports-history video
thumbnail. Return JSON {"person": <the one real person to show, exact full name for a Wikipedia
search, or "" if the story has no single person>, "concept": <ALWAYS a short generic stock-photo
query depicting the topic, e.g. "fifa world cup trophy", "formula 1 car", "cricket stadium" —
this is the fallback used when no person is given OR the person's photo can't be fetched, so
never leave it empty>}. Use only what the script supports; never invent a person."""

_SUBJECT_SCHEMA = {"type": "object",
                   "properties": {"person": {"type": "string"}, "concept": {"type": "string"}},
                   "required": ["person", "concept"], "additionalProperties": False}


def _subject_query(idea: dict, script: str) -> tuple[str, str]:
    """(person, concept) via one structured LLM call; ('', '') on any failure."""
    try:
        client = anthropic.Anthropic(max_retries=5)
        title = (idea.get("title_variants") or [idea.get("title", "")])[0]
        resp = client.messages.create(
            model=MODEL, max_tokens=64, system=_SUBJECT_SYSTEM,
            messages=[{"role": "user",
                       "content": f"TITLE: {title}\n\nSCRIPT:\n{script[:4000]}\n\nIdentify the subject."}],
            output_config={"format": {"type": "json_schema", "schema": _SUBJECT_SCHEMA}})
        data = json.loads(next(b.text for b in resp.content if b.type == "text"))
        return (data.get("person", "") or "").strip(), (data.get("concept", "") or "").strip()
    except Exception:
        return "", ""


def _read_script(idea_id: str, fmt: str) -> str:
    for f in (fmt, "long", "short"):
        p = paths.script_path(idea_id, f)
        if os.path.exists(p):
            try:
                return open(p).read()
            except OSError:
                return ""
    return ""


def _download(url: str, out_path: str) -> bool:
    """Download url → out_path. Never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TheUntoldGame/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(out_path, "wb") as f:
            shutil.copyfileobj(r, f)
        return True
    except Exception:
        return False


def _write_credit(idea_id: str, fmt: str, credit: str) -> None:
    try:
        with open(os.path.join(paths.artifact_dir(idea_id, fmt), "subject_credit.txt"), "w") as f:
            f.write(credit + "\n")
    except OSError:
        pass


def source_subject(idea: dict, fmt: str) -> dict:
    """Populate produced/<id>/<fmt>/subject.png. Order: existing human photo (untouched) →
    Wikipedia lead image of the person → Pexels stock for the fallback concept → none.
    Returns {'source', 'path', 'credit'}."""
    idea_id = idea["id"]
    target = paths.subject_path(idea_id, fmt)
    if os.path.exists(target):
        return {"source": "human", "path": target, "credit": ""}
    out = os.path.join(paths.artifact_dir(idea_id, fmt), "subject.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    script = idea.get("script") or _read_script(idea_id, fmt)
    person, concept = _subject_query(idea, script)

    if person:
        hit = wikipedia.lead_image(person)
        if hit and _download(hit[0], out):
            _write_credit(idea_id, fmt, hit[1])
            return {"source": "wikipedia", "path": out, "credit": hit[1]}
    if concept:
        credit = footage.fetch_photo(concept, out)
        if credit:
            _write_credit(idea_id, fmt, credit)
            return {"source": "pexels", "path": out, "credit": credit}
    return {"source": None, "path": out, "credit": ""}
