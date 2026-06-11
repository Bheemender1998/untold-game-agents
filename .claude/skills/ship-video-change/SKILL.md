---
name: ship-video-change
description: The release rail for shipping any engine/*.py change in The Untold Game — feature branch, pytest, an orchestrator smoke, dual adversarial review (Codex + Claude), and a PR/squash-merge with a review trailer. Use when the user says "ship this", "open the PR", "merge this change", or is finishing engine/*.py work and about to create a PR. Do NOT use for docs/config-only PRs (plain gh pr create, no trailer), fact-review (use fact-review), or producing a video (run_produce/run_auto).
---

# ship-video-change

One guided rail for shipping `engine/*.py` changes — adapted from ConvictionFinder's
`ship-engine-change`. CLAUDE.md is the source of truth; if a command here disagrees, CLAUDE.md
wins. Create one TodoWrite item per step before starting.

## Checklist

1. **On a feature branch off `main`.** Never `main` directly (the pre-push hook blocks it).
   `git checkout -b feat/<slug>` if not already on one.

2. **Tests green.** `python3 -m pytest tests/ -q` — must pass (the contract; the PostToolUse
   hook already runs it on each engine edit). Tests run under **`python3`**, never `.venv-video`.

3. **Orchestrator smoke (if `run_auto.py`/`qc.py` touched).** `python3 -m engine.run_auto --list`
   (no traceback) and, for pipeline changes, `python3 -m engine.run_auto --no-render` against a
   throwaway/known idea. The 45-min render is NOT a gate — never block a PR on a render; rely on
   tests + the QC gate + the still-preview trick (`npx remotion still ... --frame=N`).

4. **Dual adversarial review, in parallel.** Run BOTH — they catch different bug classes:
   - `codex:rescue` (Codex second pass), and
   - spawn `Agent(superpowers:code-reviewer)` — **capture the reviewer's agentId** from its output.
   For a multi-file feature, prefer the full `superpowers:subagent-driven-development` rail
   (per-task review + final whole-impl review), which is how Stage B was built.

5. **Gate: 0 Critical + 0 Important from BOTH reviewers.** Otherwise fix → re-review. Do NOT
   merge with any Critical/Important open. Run this end-of-branch pass even if per-task reviews
   already approved — it catches integration bugs the per-task ones miss.

6. **Open the PR** with the reviewer trailer:
   ```
   gh pr create --base main --body "<summary>

   Adversarial-Reviewed: <agentId>"
   ```

7. **Merge:** `gh pr merge --squash --delete-branch`.

## Integrity gate (TUG-specific, non-negotiable)

If the change touches script/visual generation, confirm it cannot publish unverified specifics
about real people/events and cannot fabricate real footage (CLAUDE.md, ADR-0005). This is TUG's
equivalent of CF's silent-zero billing guard — a hard gate, not a nicety.

## Bypass (docs / renames only)

Pure docs or renames may skip steps 4–5 by putting `Review-Skip: <reason>` in the PR body
instead of `Adversarial-Reviewed:`. Any `engine/*.py` logic change does NOT qualify.

## Scope guard

Release rail only. Defers: fact-checking a script → `fact-review`; producing/rendering a video →
`run_produce` / `run_auto`; dashboard/config/docs-only PRs → plain `gh pr create --base main`
(no trailer, no review needed).
