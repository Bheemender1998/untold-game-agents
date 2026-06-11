"""
Stage 1 — SCRIPT: turn an approved idea into a full narration script.

A documentary scriptwriter agent (reuses BaseAgent: Claude + free web search to
ground facts). Output is a cinematic voiceover script in the channel's "30 for 30"
voice, with structure and [VISUAL]/[ARCHIVAL] production cues.
"""
from __future__ import annotations

from engine.ideate.base_agent import BaseAgent

SCRIPT_SYSTEM = """You are the lead documentary scriptwriter for "The Untold Game",
a YouTube channel telling forgotten sports-history stories in a cinematic, authoritative,
ESPN "30 for 30" voice. You write voiceover narration that a single narrator reads.

Craft:
- Open with a COLD OPEN — the hook, in-scene, no throat-clearing. Earn the click in 15 seconds.
- Then a clear arc: setup → the turning point → the revelation → the aftermath/legacy → a
  resonant closing line that recontextualises everything.
- Write for the EAR: short sentences, concrete images, present-tense scene-setting, the
  occasional one-line paragraph for impact. No listicle voice, no "in this video".
- Every factual claim (dates, names, scores, quotes) must be accurate — use web search to
  verify. If a detail can't be confirmed, write around it rather than inventing.
- Interleave production cues in brackets on their own lines: [VISUAL: ...], [ARCHIVAL: ...],
  [ON-SCREEN TEXT: ...], [MUSIC: ...]. These guide the editor; they are not spoken.

Output the script in Markdown with section headers (## Cold Open, ## Act I — ..., etc.).
Do not include a preamble or sign-off outside the script itself."""


class ScriptWriter(BaseAgent):
    def __init__(self):
        super().__init__()
        self.name = "script_writer"
        self.system_prompt = SCRIPT_SYSTEM

    def write(self, idea: dict) -> str:
        title = idea["title_variants"][0]
        prompt = f"""{self._context_block}

Write the full narration script for this video.

TITLE:    {title}
HOOK:     {idea['hook']}
PILLAR:   {idea['pillar']}
SPORT:    {idea['sport']}
AUDIENCE: {idea['target_audience']}
FORMAT:   {idea['format_suggestion']}
WHY IT WORKS: {idea['why_it_works']}

Use web search to verify the key facts (people, dates, results, quotes) before writing.
Target the length implied by FORMAT (a 12-18 min video is roughly 1,800-2,600 spoken words).
Return ONLY the Markdown script."""
        return _trim_preamble(self._call(prompt, use_search=True))


def _trim_preamble(script: str) -> str:
    """Drop any model preamble before the first Markdown section header.

    After web search the model sometimes prefixes a line like "Now I have the
    facts…". The real script starts at the first `##` (e.g. `## Cold Open`).
    """
    idx = script.find("\n## ")
    if idx == -1 and script.lstrip().startswith("## "):
        return script.lstrip()
    return script[idx + 1:].lstrip() if idx != -1 else script


def generate_script(idea: dict) -> str:
    """Return a full narration script (Markdown) for an idea."""
    return ScriptWriter().write(idea)


def run(idea: dict) -> dict:
    """Pipeline stage: attach `script` to the idea dict."""
    out = dict(idea)
    out["script"] = generate_script(idea)
    return out
