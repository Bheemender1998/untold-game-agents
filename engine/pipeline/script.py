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
from engine.video import tts as _tts

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
~50-second sports-history hooks. You write ONE continuous block of voiceover narration a
single narrator reads. No section headers, no markdown, no bracketed production cues.

Craft, in this exact 3-beat shape, as flowing prose (not labelled):
- HOOK: the FIRST line must hit the central conflict or mystery in EIGHT WORDS OR FEWER,
  payoff-forward — the turn, the loss, the vanishing. It is the scroll-stopper; the viewer
  gives you ~2 seconds. Do NOT open on a pronoun (He/She/It/They/We/You/There) — open on a
  vivid ACTION, image, place, or the raw stakes ("A kung-fu kick into the stands ended a
  career — and built a dynasty."). NO atmosphere or scene-setting opener ("He was a king in
  exile…", "It was a cold night…"), no throat-clearing, no "in this video".
  Carry NO specific number, name, or date in the hook — those land in the FACT beat one line
  later. If a specific must appear it is the exact verified value: never round (1,457, never
  ~1,500), never assert a superlative as fact ("the greatest ... ever") unless attributed or
  defensibly hedged ("of his generation").
- FACT: the untold facts, built tight and concrete — names, dates, the turn (you have room
  for two or three connected beats here, not just one).
- PAYOFF: a resolving close of ONE TO TWO SENTENCES that recontextualises the story and lands
  the ending — earned, not clipped. Nod that the full story is bigger. Introduce no new fact.

Write for the ear: short, present-tense, concrete. Every factual claim (dates, names, scores,
quotes) must be accurate — use web search to verify; if a detail can't be confirmed, write
around it rather than inventing. Never invent people, quotes, dates, or outcomes — if it
can't be verified, leave it out.

Your VERY FIRST line must be exactly: MOOD: <one of: tense | triumphant | somber | hype>
(the story's dominant emotional register — drives music and narrator voice). Then the
narration on the following lines.

Output ONLY the final narration after the MOOD line. Do NOT show your work — no preamble,
no "let me…", no bullet fact lists, no word counts, no multiple drafts, no commentary."""

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
words total (~50-55 seconds). Hook + the key facts + payoff. Count your words; stay in range.

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


def clean_short_body(raw: str) -> str:
    """Strip short-script scaffolding (MOOD header, model preamble, rules) from `raw`,
    returning just the spoken narration. Used to re-clean fact-corrected short scripts,
    where the correction model re-adds headers that would otherwise be narrated."""
    return _parse_short(raw)["script"]


def generate_short_script(idea: dict) -> dict:
    """Return {'script': str, 'mood': str} for a YouTube Short."""
    return ShortScriptWriter().write(idea)


# ── Companion tease writer (derived from the verified long script) ─────────────

DERIVE_TEASE_SYSTEM = """You write a YouTube SHORT (vertical, ~50s) that is a condensed,
high-retention cut of a LONGER video whose full narration is given to you. Same craft as our
shorts: write for the ear, present-tense, concrete, scroll-stopping.

In this exact 3-beat shape, as flowing prose (not labelled):
- HOOK: the FIRST line must hit the central conflict or mystery in EIGHT WORDS OR FEWER,
  payoff-forward — the scroll-stopper, since the viewer gives you ~2 seconds. Do NOT open on a
  pronoun (He/She/It/They/We/You/There) — open on a vivid ACTION, image, place, or the raw
  stakes. NO atmosphere or scene-setting opener, no throat-clearing. Carry NO specific number,
  name, or date in the hook — those land in the FACT beat. If a specific must appear it is the
  exact verified value: never round, never assert a superlative as fact unless attributed/defensibly hedged.
- FACT: the most arresting facts of the story, tight and concrete.
- PAYOFF: a resolving close of ONE TO TWO SENTENCES that lands the ending — earned, not clipped —
  while nodding that the full story is bigger.

HARD INTEGRITY RULE: use ONLY facts that appear in the long narration provided. Do NOT introduce
any new name, date, number, quote, or claim that is not already in that text. If something isn't
in the long, leave it out. No web search — the long is already verified.

Your VERY FIRST line must be exactly: MOOD: <one of: tense | triumphant | somber | hype>
(the story's dominant emotional register — drives music and narrator voice). Then the
narration on the following lines.

Output ONLY the final narration after the MOOD line. Do NOT show your work — no preamble,
no "let me…", no bullet fact lists, no word counts, no multiple drafts, no commentary."""


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
words total (~50-55 seconds). Hook + the key facts + payoff. Count your words; stay in range.

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


def _name_inflection_match(tok: str, whole_long_tokens: set[str]) -> bool:
    """Inflection tolerance for the proper-noun guard: a short name counts as contained when it
    shares a ≥4-char prefix with a WHOLE verified long token, either direction — so America~American,
    Soviet~Soviets, Russia~Russian pass. The ≥4 floor keeps acronyms/initialisms (NBA, USA) strict;
    matching only WHOLE long tokens (not hyphen/apostrophe components) avoids spurious passes like
    short 'Antimatter' against a long 'Anti-Drug'. Digit groups are NEVER inflection-matched — a
    fabricated number must still flag (the caller checks numbers exactly)."""
    return any(
        (lw.startswith(tok) or tok.startswith(lw)) and min(len(lw), len(tok)) >= 4
        for lw in whole_long_tokens
    )


def tease_within_long(short_script: str, long_script: str) -> tuple[bool, list[str]]:
    """Deterministic integrity guard (no network): every factual specific in the short —
    capitalized proper-noun tokens and digit groups — must already appear in the long. A short
    proper noun matches a whole long token, a hyphen/apostrophe-delimited component of one, or a
    ≥4-char prefix-shared inflection of a whole long token (America~American); digit groups must
    match exactly (never a substring or prefix). Returns (ok, sorted_new_tokens); a non-empty list
    means the short introduced something the verified long didn't contain → short_needs_review.
    Scope note: this catches capitalized names and digit groups; spelled-out numbers and
    lowercase novel nouns are intentionally not caught — the short is also constrained by the
    derive prompt and the long is already fact-gated, so this is a conservative backstop."""
    # The long tokenizer KEEPS hyphens/apostrophes (e.g. "Anti-Drug", "O'Neill" are single
    # tokens), but _TEASE_NAME_RE below SPLITS proper nouns on those joiners ("Anti", "Neill").
    # `whole` holds the unsplit tokens (used for inflection prefix-matching); `long_words` adds
    # the hyphen/apostrophe components too, so a long "Anti-Drug" exact-covers a short "Anti".
    whole: set[str] = set()
    long_words: set[str] = set()
    for w in re.findall(r"\b[\w'\-]+\b", long_script):
        wl = w.lower()
        whole.add(wl)
        long_words.add(wl)
        parts = re.split(r"[-']", w)
        if len(parts) > 1:
            long_words.update(p.lower() for p in parts if p)
    long_nums = set(_TEASE_NUM_RE.findall(long_script))
    new: set[str] = set()
    for tok in _TEASE_NAME_RE.findall(short_script):
        tl = tok.lower()
        if len(tok) < 3 or tl in _TEASE_STOP:
            continue
        if tl not in long_words and not _name_inflection_match(tl, whole):
            new.add(tok)
    for num in _TEASE_NUM_RE.findall(short_script):
        if num not in long_nums:
            new.add(num)
    return (not new, sorted(new))


# ── Short-title digit-containment backstop ────────────────────────────────────

# Title backstop captures decimals as ONE token (1.5, 3.5) so a fabricated decimal can't be
# decomposed into component digit groups that happen to appear separately in the script. Distinct
# from _TEASE_NUM_RE (used by tease_within_long), which is intentionally left unchanged.
_TITLE_NUM_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")


def _norm_num(tok: str) -> str:
    """Normalise a digit token for value comparison: drop thousands-separator commas (global),
    keep everything else. '2,003' -> '2003'; '1,234,567' -> '1234567'. Decimal points are NOT
    stripped ('1.5' would corrupt to '15'); note _TEASE_NUM_RE already splits on '.', matching
    the existing tease-guard behaviour."""
    return tok.replace(",", "")


def title_numbers_within(title: str, script: str) -> tuple[bool, list[str]]:
    """Backstop for a generated SHORT title: every digit group in `title` must already appear
    (comma-normalised) as a digit group in the verified `script`. Returns (ok, sorted novel
    numbers); a non-empty list means the title introduced a number the fact-gated script doesn't
    contain -> caller self-stubs to title_variants[0].

    Digit groups ONLY -- the proper-noun half of tease_within_long is intentionally NOT used here:
    titles are Title Case, so every word looks like a proper noun and inflected title words would
    false-flag. Numbers don't inflect or get title-cased, so digit containment is surgical and
    targets the real risk (a fabricated stat reaching live metadata). Decimals are captured as one
    token ('3.5') so they can't be decomposed into component digits that appear separately in the
    script; hyphenated ranges (1969-70) and alphanumerics (3peat) are still split/skipped --
    an accepted lower-risk residual. Known conservative limitation: a number the title writes as
    a digit ('6') that the script only spells out ('six') is flagged and falls back -- rare, and
    a safe false positive (we never ship a fabricated stat)."""
    script_nums = {_norm_num(n) for n in _TITLE_NUM_RE.findall(script)}
    new = {_norm_num(n) for n in _TITLE_NUM_RE.findall(title)} - script_nums
    return (not new, sorted(new))
