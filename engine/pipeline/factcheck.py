"""
Fact-verification gate — nothing reaches the screen or the voiceover unverified.

Two phases (both use structured outputs for reliable JSON; no fragile parsing):
  1. extract_claims  — pull every concrete, checkable assertion from the script
                       (who / what / when / where / how-many). Skips narration flourish.
  2. verify_claim    — free DuckDuckGo search per claim, then Claude judges it
                       supported / contradicted / unverified against the results,
                       with a correction + source when it's wrong.

`correct_script` then rewrites the script removing/fixing flagged claims. This is the
single most important quality gate for a real-events channel — see ADR-0005.
"""
from __future__ import annotations
import json

import anthropic
from engine.config import MODEL
from engine.ideate.web_search import search as web_search
from engine.ideate import wikipedia

_client = anthropic.Anthropic(max_retries=5)

# ── Phase 1: extract concrete claims ─────────────────────────────────────────

_EXTRACT_SYSTEM = """You extract checkable factual claims from a documentary script
for fact-checking. A claim is a discrete, verifiable assertion of fact — a name, a
date, a place, a number, a score, a cause/manner of death, "who did what". Rewrite
each as a standalone, self-contained statement (resolve pronouns). EXCLUDE narration
flourish, opinion, atmosphere, rhetorical questions, and anything not falsifiable.
Prioritise the highest-risk specifics: deaths, crimes, dates, locations, numbers."""

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {"type": "string"}}},
    "required": ["claims"],
    "additionalProperties": False,
}

# ── Phase 2: verify one claim against search results ─────────────────────────

_VERIFY_SYSTEM = """You are a rigorous fact-checker. Given a claim and evidence, judge ONLY
from the evidence:
- supported   : evidence clearly confirms the claim.
- contradicted: evidence says something different — give the CORRECTED fact.
- unverified  : evidence doesn't clearly confirm or deny it.
When an AUTHORITATIVE (encyclopedic / Wikipedia) source is present and directly addresses the
claim, weight it ABOVE web snippets — web results are noisy and frequently pull the wrong
event/person. Be strict: a partially-wrong specific (wrong place, wrong count, wrong date) is
'contradicted', not 'supported'. Cite the source (Wikipedia title or URL) you relied on."""

_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["supported", "contradicted", "unverified"]},
        "correction": {"type": "string"},   # the right fact if contradicted; else ""
        "source": {"type": "string"},        # URL relied on; else ""
    },
    "required": ["verdict", "correction", "source"],
    "additionalProperties": False,
}


def _structured(system: str, prompt: str, schema: dict, max_tokens: int = 2048) -> dict:
    resp = _client.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def extract_claims(script_md: str, max_claims: int = 14) -> list[str]:
    out = _structured(_EXTRACT_SYSTEM,
                      f"Extract up to {max_claims} checkable claims from this script:\n\n{script_md}",
                      _EXTRACT_SCHEMA, max_tokens=2048)
    return out["claims"][:max_claims]


def verify_claim(claim: str) -> dict:
    results = web_search(claim, max_results=5)
    wiki = wikipedia.lookup(claim)   # authoritative encyclopedic context (or "" on miss/error)
    evidence = (f"AUTHORITATIVE (encyclopedic):\n{wiki}\n\n" if wiki else "") + \
               f"WEB RESULTS:\n{results}"
    out = _structured(_VERIFY_SYSTEM, f"CLAIM: {claim}\n\n{evidence}", _VERIFY_SCHEMA)
    out["claim"] = claim
    return out


def factcheck(script_md: str, max_claims: int = 25) -> dict:
    """Verify the script's claims. Returns a verdict dict:
      checked, supported, issues[], complete (bool), max_claims, passed (bool).

    `complete` is False when extraction hit the cap (more claims may exist
    unchecked) — so the gate is honest about incomplete coverage. `passed` is True
    only when there are zero issues AND coverage is complete. Sequential (TPM-safe).
    """
    claims = extract_claims(script_md, max_claims)
    # If extraction returned the full cap, it likely truncated → coverage incomplete.
    complete = len(claims) < max_claims
    issues, supported = [], 0
    for c in claims:
        v = verify_claim(c)
        if v["verdict"] == "supported":
            supported += 1
        else:
            issues.append(v)
    return {
        "checked": len(claims), "supported": supported, "issues": issues,
        "complete": complete, "max_claims": max_claims,
        "passed": (not issues) and complete,
    }


# ── Correction ───────────────────────────────────────────────────────────────

_FIX_SYSTEM = """You revise a documentary script to remove or correct factual errors,
preserving the voice and flow. For each flagged issue: if a correction is given, fix
the line to state the correct fact; if it's unverified and can't be confirmed, cut or
soften the specific (don't state unconfirmed specifics as fact). Change nothing else.
Return ONLY the revised Markdown script."""


def correct_script(script_md: str, issues: list[dict]) -> str:
    """Rewrite the script fixing the flagged issues. Returns corrected Markdown."""
    if not issues:
        return script_md
    flagged = "\n".join(
        f"- CLAIM: {i['claim']}\n  VERDICT: {i['verdict']}"
        f"{('  CORRECTION: ' + i['correction']) if i.get('correction') else ''}"
        f"{('  SOURCE: ' + i['source']) if i.get('source') else ''}"
        for i in issues
    )
    resp = _client.messages.create(
        model=MODEL, max_tokens=8192, system=_FIX_SYSTEM,
        messages=[{"role": "user", "content": f"ISSUES:\n{flagged}\n\nSCRIPT:\n{script_md}"}],
    )
    return next(b.text for b in resp.content if b.type == "text").strip()
