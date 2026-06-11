---
name: fact-review
description: Human-grade fact-review of a produced script that the auto fact-gate flagged (needs_review). Verifies flags against an authoritative source, fixes only the real errors, and clears the idea to render. Use when the user says "fact-review <id>", "verify the script", "the fact-gate flagged it", or after run_produce marks an idea needs_review.
---

# Fact-review (authoritative human override)

The auto fact-gate (`engine/pipeline/factcheck.py`) uses **free DuckDuckGo search**, which is
**noisy on well-documented topics** — it surfaces unrelated matches and weak sources, so a
*correct* script on a famous event rarely reaches `passed`. Its flags are a **starting point,
not truth**. This skill is the human override ADR-0005 intends: verify against a real source,
fix only genuine errors, clear to render. The gate not passing is normal — not a failure.

## Workflow

1. **Get the flags.** Read `produced/<id>/factcheck.json` (or regenerate with
   `python3 -m engine.run_factcheck --id <id>`). Note `checked / supported / issues / complete`.

2. **Triage each flag — real error vs search artifact.** Do **not** trust the auto-correction
   text; it is often garbled (on Kolkata 2001 the gate once cited an *Edgbaston 2025* match and
   a Facebook post). For each flagged claim decide: genuine error, unverifiable stat, or
   false-positive where the script is actually right.

3. **Verify the disputed/real ones against an AUTHORITATIVE source — not DDG.** WebFetch a
   primary/reference source and pull the ground-truth facts in one go: Wikipedia match article,
   ESPNcricinfo / official scorecard, federation record, reputable obituary, etc. Prefer a
   single authoritative page that settles every disputed number at once.

4. **Fix ONLY the confirmed errors in `produced/<id>/script.md`.** Grep the script for each
   disputed line and edit just those. Leave correct lines untouched. Never state an
   unverifiable specific as fact — soften or cut it. Never invent specifics about real
   people/events. Keep the narration word count in the target band
   (`config.TARGET_SCRIPT_WORDS_MIN..MAX`, ~8–9 min).

5. **Re-verify (optional).** Re-run `run_factcheck --id <id>` to confirm no NEW real error.
   Expect residual DDG false-positives — that's fine; your authoritative check is the override.

6. **Clear it to render.** `python3 -m engine.run_auto --review <id> --note "verified vs <source>"`
   (sets `human_reviewed: True` + a dated note; `fact_passed` stays `False` — honest: the auto
   gate didn't pass, a human did). Then render via `python3 -m engine.run_auto --render <id>`.

## Worked example (Kolkata 2001, idea `85a68197`)

Gate flagged 11 claims. Authoritative Wikipedia scorecard showed: **1 real error** (script said
"India won the First Test" — Australia won by 10 wickets; streak 15→16), 2 wording/stat fixes,
and **8 false-positives** (Harbhajan's age, Laxman 281 out, the 384 target — all correct; the
gate's rebuttals were wrong). Fixed the real ones, added the hat-trick beat (a *verified* fact
the script omitted), set `human_reviewed`, rendered. ~7.5 min, QC-clean.

## Guardrails

- **Never publish unverified specifics about real people/events** (CLAUDE.md, ADR-0005).
- Fix real errors only — do **not** rewrite lines the script got right.
- The gate's `correction`/`source` fields are unreliable; your WebFetch of an authoritative
  page is the source of truth, not the gate's text.
- A *verified* fact the script omitted (a hat-trick, a record) is worth adding; an unverifiable
  one is worth cutting.
