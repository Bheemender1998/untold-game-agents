# Kill the script-scaffold leak — design

**Date:** 2026-06-13
**Status:** approved (brainstorm) → writing-plans next
**Branch:** `feat/shortform-pacing-broll` (kept with the short-form work — overlaps `script.py` prompts; whole branch gets one final review before merge)

## Problem

The short-script writer leaks model scaffolding into `produced/<id>/<fmt>/script.md`, and the
narration extractors don't fully remove it — so it would be **narrated and captioned** into the
video. Three forms, all observed on the Cantona short (`25051da8`):

1. **Leading reasoning preamble** — e.g. "Good — I now have solid verified facts. Let me compile
   what I know:" followed by a bullet list of facts.
2. **Trailing word-count tallies** — e.g. "**Word count:** Let me count carefully. A(1) kung-fu(2)
   kick(3) …", "137 words — slightly under.", "154 words — within range. ✅".
3. **Multiple drafts** — the model re-emitted `MOOD: triumphant` + the full narration three times,
   with counting blocks between.

Root cause: `script._parse_short` strips only a *leading* preamble before the **first** valid
`MOOD:` line and leading noise; `tts.script_to_narration_text` strips only `#`/`[CUE]`/`MOOD:`
lines and markdown emphasis. Neither removes trailing scaffold or collapses repeated drafts.
This corrupts every produce and currently requires manual hand-cleaning before each render.
(Tracked in memory `script-scaffold-leak-bug`.)

## Decision (locked in brainstorm)

**Defense + prompt nudge.** Robust extraction is the guarantee (we can't trust the model);
a prompt nudge reduces how often it leaks. Defense in depth: clean at BOTH the short parser
(so `script.md` on disk is clean) and the render-time extractor (so TTS never speaks scaffold,
even for old files / long-form / hand edits).

## Scope

In scope:

| Surface | Change |
|---------|--------|
| `engine/video/tts.py` | new `is_scaffold_line(line)`; `script_to_narration_text` skips scaffold lines |
| `engine/pipeline/script.py` | `_parse_short` takes the narration after the **last** valid `MOOD:` and drops scaffold lines (imports `is_scaffold_line` from tts) |
| `engine/pipeline/script.py` | `SHORT_SYSTEM` + `DERIVE_TEASE_SYSTEM` prompt nudge (no shown work) |
| tests | `test_tts.py`, `test_script.py` |

Out of scope: long-form `_trim_preamble` rewrite (it already handles long leading preamble; it
benefits from the render-time net via `script_to_narration_text`); changing the produce flow.

## Design

### 1. Shared scaffold detector — `tts.is_scaffold_line(line: str) -> bool`

Lives in `tts.py` (the render-time extractor is there; the lower-level `video` module is a fine
home, and `script.py` may import `engine.video.tts` cheaply — kokoro/numpy are imported lazily
inside functions, not at module top). Conservative, anchored to line start, so it never matches
real narration. Returns True when the **stripped, lowercased** line matches any:

- `^word count\b` or `^\*+\s*word count` (the footer header)
- `^let me (count|recount|write|compile|now|expand)\b`
- `^now let me\b`, `^here'?s\b`, `^here is\b`, `^good[\s,—-]`, `^i'?ll write\b`,
  `^i (now )?have\b`, `^let me\b`
- a token-count tally: line contains **3 or more** `(\d+)` groups (e.g. "A(1) kung-fu(2) kick(3)")
- `^\d+\s+words\b` or contains `words —` followed by `within range|slightly under|over`
- the line is just a checkmark/status: contains `✅` and ≤ 6 words

The "≥3 numbered groups" and "word count" rules carry the load and are essentially zero-false-
positive on sports narration; the verb-prefix rules are the riskier ones but our narration style
doesn't open lines with "Let me…"/"Here's…"/"Good,…".

### 2. `script._parse_short` — keep the final draft, drop scaffold

Today: finds the **first** valid `MOOD:` header, narration = everything after it. Change:

- Scan all content lines for valid `MOOD:` headers; if any exist, narration starts after the
  **LAST** one (the final draft — each leaked draft is preceded by its own `MOOD:`), and `mood`
  is that last header's value. If none exist, keep current behaviour (first content line is
  narration, with the existing leading-preamble heuristic).
- After choosing the start index, build the body from the remaining lines **excluding**
  `_is_noise` lines, `MOOD:` lines, and `tts.is_scaffold_line` lines.
- Trailing scaffold (the word-count block after the final narration) is removed by the
  per-line scaffold filter — no separate "trailing" logic needed.

`clean_short_body` already delegates to `_parse_short`, so the fact-correct re-clean path is
covered.

### 3. `tts.script_to_narration_text` — render-time safety net

Add one skip condition in the existing per-line loop: `if is_scaffold_line(s): continue`
(placed after the `MOOD:` skip, before markdown-emphasis stripping). Guarantees scaffold never
reaches TTS even if `script.md` has residue.

### 4. Prompt nudge

Append to `SHORT_SYSTEM` and `DERIVE_TEASE_SYSTEM`, near the existing "narration only" line:

> Output ONLY the final narration after the MOOD line. Do NOT show your work — no preamble,
> no "let me…", no bullet fact lists, no word counts, no multiple drafts, no commentary.

## Data flow

```
model output (messy: preamble + MOOD + draft1 + counts + MOOD + draft2 + counts + MOOD + draft3 + counts)
   └─ _parse_short: start after LAST MOOD → draft3 region; drop noise/MOOD/scaffold lines
        → script.md = clean final narration
                 │
   run_video → script_to_narration_text: drop #/[CUE]/MOOD/scaffold → spoken text
                 → TTS (never speaks scaffold)
```

## Error handling / edge cases

- **No MOOD line** in output → existing leading-preamble heuristic + scaffold filter (still cleans
  trailing tallies).
- **Clean script (normal case)** → scaffold filter matches nothing; output byte-identical to today
  (guarded by an explicit regression test).
- **Empty after filtering** → returns "" (caller already handles empty; self-stub unchanged).

## Testing

`python3 -m pytest tests/ -q` is the contract. New/updated:

- `test_tts.py::is_scaffold_line` — true for: "Word count: Let me count carefully.",
  "A(1) kung-fu(2) kick(3) into(4)", "154 words — within range. ✅", "Good — I now have solid
  verified facts.", "Let me compile what I know:". **False** for real narration:
  "A kung-fu kick into the stands shook English football to its core.", "Eight-month ban.",
  "October 1995 — Cantona walks back out at Old Trafford."
- `test_tts.py::script_to_narration_text` — given preamble + narration + trailing word-count,
  returns only narration; **a clean script is unchanged** (regression).
- `test_script.py::_parse_short` — fed a synthetic 3-draft leak (preamble, MOOD+draft1, counts,
  MOOD+draft2, counts, MOOD+draft3, counts) → returns ONLY draft3's narration + mood `triumphant`;
  single clean MOOD+narration unchanged; no-MOOD preamble case still works.
- `test_script.py` prompt firewall — `SHORT_SYSTEM`/`DERIVE_TEASE_SYSTEM` contain the no-shown-work
  rule (string assertion).

## Proof

Re-produce the Cantona short (`25051da8`) — `script.md` comes out clean with **no hand-editing**,
and (with the word-band recalibration already on this branch) lands ~50-55s. Render + QC.
