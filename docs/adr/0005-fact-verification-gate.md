# ADR 0005 — Mandatory fact-verification gate before publish

**Status:** Accepted / LIVE (2026-06-11)

## Context
The first published video (Escobar teaser) stated fabricated specifics about a real
death — "Santiago Gallón found dead in a parking lot, shot once" (real death, but
wrong place + invented count). A full check of that script found **7 of 14 claims
flagged**, several clearly wrong (Gallón "acquitted" → never tried; Romania score
direction; "Ernie"→"Earnie" Stewart; homicide rate 380→375). The AI script writer is
not reliable enough, on its own, for a channel about real deaths and crimes
(defamation / misinformation / strikes / credibility risk).

## Decision
A **fact-verification gate is mandatory between produce and publish.**
`engine/pipeline/factcheck.py`: extract every concrete claim (structured output) →
free DuckDuckGo search per claim → Claude judges supported/contradicted/unverified
with a correction + source (structured output). `engine/run_factcheck.py --fix`
rewrites the script removing/correcting flagged claims (backs up to script.md.bak).

**Required workflow:** produce → `run_factcheck --fix` → **human review** → re-render
→ publish. Nothing with unverified specifics ships.

## Consequences
- Removes the existential risk of stating false facts about real people/events.
- The gate is deliberately **conservative** (off-target search results → flag, not
  trust) — so a human still reviews the corrected script; it reduces risk, doesn't
  eliminate judgment.
- Cost: ~1 extract + N verify calls per script (sequential, respects the TPM tier).
- The first published video was rendered from the pre-gate script → must be
  re-rendered from the corrected script.md and re-uploaded before going public.
