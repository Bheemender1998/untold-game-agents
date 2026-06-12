"""
Stage 1 — SCRIPT: turn an approved idea into a full narration script.

A documentary scriptwriter agent (reuses BaseAgent: Claude + free web search to
ground facts). Output is a cinematic voiceover script in the channel's "30 for 30"
voice, with structure and [VISUAL]/[ARCHIVAL] production cues.
"""
from __future__ import annotations

from engine.ideate.base_agent import BaseAgent
from engine import config

SCRIPT_SYSTEM = """You are the lead documentary scriptwriter for "The Untold Game",
a YouTube channel telling forgotten sports-history stories in a cinematic, authoritative,
ESPN "30 for 30" voice. You write voiceover narration that a single narrator reads.

Craft:
- Open with a COLD OPEN — the hook, in-scene, no throat-clearing. Earn the click in 15 seconds.
- Then a clear arc: setup → the turning point → the revelation → the aftermath/legacy → a
  resonant closing line that recontextualises everything.
- Write for the EAR: short sentences, concrete images, present-tense scene-setting, the
  occasional one-line paragraph for impact. No listicle voice, no "in this video".
- BE TIGHT. This is a short, high-retention cut — every sentence must earn its place. Cut
  throat-clearing, restated context, and victory-lap closings. Favour momentum over completeness:
  one vivid concrete detail beats three general ones. If you're unsure a line survives a re-read,
  cut it.
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
WHY IT WORKS: {idea['why_it_works']}

Use web search to verify the key facts (people, dates, results, quotes) before writing.

LENGTH — this is a HARD constraint that OVERRIDES any format suggestion on the idea:
target about {config.TARGET_SCRIPT_WORDS} spoken words ({config.TARGET_SCRIPT_WORDS_MIN}-{config.TARGET_SCRIPT_WORDS_MAX}),
which is roughly {config.TARGET_RUNTIME_LABEL} of narration. Do NOT write a 15-25 minute
epic — tell this story tight. Pick the single strongest spine and cut everything that
isn't load-bearing. Count your words; if you run long, cut, don't pad.

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


# ── YouTube Shorts script writer ──────────────────────────────────────────────

SHORT_SYSTEM = """You are the scriptwriter for "The Untold Game" YouTube SHORTS — vertical
30-50 second sports-history hooks. You write ONE continuous block of voiceover narration a
single narrator reads. No section headers, no markdown, no bracketed production cues.

Craft, in this exact 3-beat shape, as flowing prose (not labelled):
- HOOK: the very first sentence is a scroll-stopping line that lands the stakes in under two
  seconds. No throat-clearing, no "in this video".
- FACT: one untold fact, built tight and concrete — names, dates, the turn.
- PAYOFF: one resonant closing line that recontextualises it.

Write for the ear: short, present-tense, concrete. Every factual claim (dates, names, scores,
quotes) must be accurate — use web search to verify; if a detail can't be confirmed, write
around it rather than inventing. Never invent people, quotes, dates, or outcomes — if it
can't be verified, leave it out.

Your VERY FIRST line must be exactly: MOOD: <one of: tense | triumphant | somber | hype>
(the story's dominant emotional register — drives music and narrator voice). Then the
narration on the following lines, and nothing else."""

_SHORT_MOODS = {"tense", "triumphant", "somber", "hype"}


class ShortScriptWriter(BaseAgent):
    def __init__(self):
        super().__init__()
        self.name = "short_script_writer"
        self.system_prompt = SHORT_SYSTEM

    def write(self, idea: dict) -> dict:
        title = idea["title_variants"][0]
        prompt = f"""{self._context_block}

Write the SHORT narration for this video.

TITLE:    {title}
HOOK:     {idea['hook']}
PILLAR:   {idea['pillar']}
SPORT:    {idea['sport']}
AUDIENCE: {idea['target_audience']}
WHY IT WORKS: {idea['why_it_works']}

Use web search to verify the key facts before writing.

LENGTH — HARD constraint: {config.SHORT_SCRIPT_WORDS_MIN}-{config.SHORT_SCRIPT_WORDS_MAX} spoken
words total (~30-50 seconds). Hook + one fact + payoff. Count your words; if long, cut.

Remember: first line `MOOD: <tense|triumphant|somber|hype>`, then the narration only."""
        return _parse_short(self._call(prompt, use_search=True))


def _parse_short(raw: str) -> dict:
    """Split a short-writer response into {'script', 'mood'}. MOOD is read from a `MOOD: x`
    line at the top, tolerating leading blank lines and markdown rules (the model often wraps
    its output in '---'). The FIRST real content line decides MOOD-vs-narration, so a
    'MOOD:'-prefixed sentence deeper in the narration is never treated as a header. Unknown/
    absent mood → '' (caller falls back to the pillar-derived mood); the MOOD line and any
    leading rules/duplicates are stripped from the script."""
    def _is_noise(t: str) -> bool:
        # blank, or a markdown rule made only of -, *, _, = (e.g. '---', '***', '===')
        return not t or set(t) <= {"-", "*", "_", "="}

    mood = ""
    lines = raw.splitlines()
    body_start = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if _is_noise(s):
            continue
        if s.upper().startswith("MOOD:"):
            cand = s.split(":", 1)[1].strip().lower()
            mood = cand if cand in _SHORT_MOODS else ""
            body_start = i + 1            # narration starts after the MOOD line
        else:
            body_start = i               # first real content line IS the narration start
        break  # the first real content line is the only candidate for the MOOD header
    while body_start < len(lines) and (
        _is_noise(lines[body_start].strip())
        or lines[body_start].strip().upper().startswith("MOOD:")
    ):
        body_start += 1  # drop leading blanks / rules / duplicate MOOD before the script
    return {"script": "\n".join(lines[body_start:]).strip(), "mood": mood}


def generate_short_script(idea: dict) -> dict:
    """Return {'script': str, 'mood': str} for a YouTube Short."""
    return ShortScriptWriter().write(idea)
