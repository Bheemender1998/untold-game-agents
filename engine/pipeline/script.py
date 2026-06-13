"""
Stage 1 — SCRIPT: turn an approved idea into a full narration script.

A documentary scriptwriter agent (reuses BaseAgent: Claude + free web search to
ground facts). Output is a cinematic voiceover script in the channel's "30 for 30"
voice, with structure and [VISUAL]/[ARCHIVAL] production cues.
"""
from __future__ import annotations
import re

from engine.ideate.base_agent import BaseAgent
from engine import config

SCRIPT_SYSTEM = """You are the lead documentary scriptwriter for "The Untold Game",
a YouTube channel telling forgotten sports-history stories in a cinematic, authoritative,
ESPN "30 for 30" voice. You write voiceover narration that a single narrator reads.

Craft:
- Open with a COLD OPEN — the hook, in-scene, no throat-clearing. Earn the click in 15 seconds —
  front-load the mystery, not the data: the strongest cold open carries no specific number, name,
  or date — lead with the stakes and the unanswered question, and let specifics land after. If a
  specific does survive into the opening line it must be the exact verified value: never round,
  never assert a superlative as fact.
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
- HOOK: front-load the mystery, not the data. The strongest hook carries NO specific number,
  name, or date — open on the emotional stakes and the unanswered question ("He was one season
  from immortality. Then he walked away."), and let specifics land in the FACT beat. This
  mystery-first hook is the GOAL, not a safe fallback — it is the scroll-stopper. If a specific
  DOES survive into the hook it must be the exact verified value: never round (1,457, never
  ~1,500), never assert a superlative as fact ("the greatest ... in history"). No throat-clearing,
  no "in this video".
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


def _is_noise(t: str) -> bool:
    # blank, or a markdown rule made only of -, *, _, = (e.g. '---', '***', '===')
    return not t or set(t) <= {"-", "*", "_", "="}


def _mood_value(s: str) -> str | None:
    """The mood named on a `MOOD: x` line, lowercased — or None if not a MOOD line."""
    if s.upper().startswith("MOOD:"):
        return s.split(":", 1)[1].strip().lower()
    return None


def _parse_short(raw: str) -> dict:
    """Split a short-writer response into {'script', 'mood'}.

    The header is a `MOOD: <valid mood>` line near the top. A *valid* mood
    (tense/triumphant/somber/hype) is what makes a line a header — so a chatty model
    preamble that precedes it (e.g. 'All facts confirmed. Now writing the script.') is
    dropped, while a 'MOOD:'-prefixed sentence deeper in the narration (an invalid mood
    value) is kept as narration. Unknown/absent mood → '' (caller falls back to the
    pillar-derived mood); the MOOD line, any preamble before it, and leading rules are
    stripped from the spoken script."""
    lines = raw.splitlines()
    content = [(i, lines[i].strip()) for i in range(len(lines)) if not _is_noise(lines[i].strip())]

    mood = ""
    body_idx = len(lines)
    if content:
        first_i, first_s = content[0]
        m0 = _mood_value(first_s)
        if m0 in _SHORT_MOODS:
            # First content line is a real MOOD header → consume it.
            mood = m0
            body_idx = first_i + 1
        else:
            # Not a valid MOOD header (narration, preamble, or a 'MOOD:'-prefixed sentence
            # with a non-mood value) — keep it as narration unless a real header follows.
            # First content line is narration or a preamble. If a MOOD:<valid> header
            # follows within the next couple of content lines, the lead lines are a model
            # preamble → drop them; otherwise narration starts at the first content line.
            header = next(((i, _mood_value(s)) for (i, s) in content[1:3]
                           if _mood_value(s) in _SHORT_MOODS), None)
            if header:
                mood = header[1]
                body_idx = header[0] + 1
            else:
                body_idx = first_i

    # Drop any leading noise / duplicate valid-MOOD lines right before the narration.
    while body_idx < len(lines):
        s = lines[body_idx].strip()
        if _is_noise(s) or (_mood_value(s) in _SHORT_MOODS):
            body_idx += 1
        else:
            break
    return {"script": "\n".join(lines[body_idx:]).strip(), "mood": mood}


def clean_short_body(raw: str) -> str:
    """Strip short-script scaffolding (MOOD header, model preamble, rules) from `raw`,
    returning just the spoken narration. Used to re-clean fact-corrected short scripts,
    where the correction model re-adds headers that would otherwise be narrated."""
    return _parse_short(raw)["script"]


def generate_short_script(idea: dict) -> dict:
    """Return {'script': str, 'mood': str} for a YouTube Short."""
    return ShortScriptWriter().write(idea)


# ── Companion tease writer (derived from the verified long script) ─────────────

DERIVE_TEASE_SYSTEM = """You write a YouTube SHORT (vertical, 30-50s) that is a condensed,
high-retention cut of a LONGER video whose full narration is given to you. Same craft as our
shorts: write for the ear, present-tense, concrete, scroll-stopping.

In this exact 3-beat shape, as flowing prose (not labelled):
- HOOK: front-load the mystery, not the data — a scroll-stopping first line that carries NO
  specific number, name, or date, opening on the stakes and the unanswered question; specifics
  land in the FACT beat. This mystery-first hook is the GOAL, not a fallback. If a specific does
  survive into the hook it must be the exact verified value: never round, never assert a
  superlative as fact.
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


# ── Companion-short containment guard ─────────────────────────────────────────

# Capitalized words/names (skip sentence-start common words); and number groups.
_TEASE_NAME_RE = re.compile(r"\b(?:[A-ZÁÉÍÓÚÑ]{2,}|[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\b")
_TEASE_NUM_RE = re.compile(r"\b\d[\d,]*\b")
_TEASE_STOP = {"the", "this", "that", "then", "they", "he", "she", "it", "and", "but",
               "in", "on", "at", "a", "an", "his", "her", "their", "by", "so", "no",
               "when", "now"}


def tease_within_long(short_script: str, long_script: str) -> tuple[bool, list[str]]:
    """Deterministic integrity guard (no network): every factual specific in the short —
    capitalized proper-noun tokens and digit groups — must already appear in the long, as a
    whole token (not a substring). Returns (ok, sorted_new_tokens); a non-empty list means the
    short introduced something the verified long didn't contain → caller flags short_needs_review.
    Scope note: this catches capitalized names and digit groups; spelled-out numbers and
    lowercase novel nouns are intentionally not caught — the short is also constrained by the
    derive prompt and the long is already fact-gated, so this is a conservative backstop."""
    long_words = {w.lower() for w in re.findall(r"\b[\w'\-]+\b", long_script)}
    long_nums = set(_TEASE_NUM_RE.findall(long_script))
    new: set[str] = set()
    for tok in _TEASE_NAME_RE.findall(short_script):
        if len(tok) < 3 or tok.lower() in _TEASE_STOP:
            continue
        if tok.lower() not in long_words:
            new.add(tok)
    for num in _TEASE_NUM_RE.findall(short_script):
        if num not in long_nums:
            new.add(num)
    return (not new, sorted(new))
