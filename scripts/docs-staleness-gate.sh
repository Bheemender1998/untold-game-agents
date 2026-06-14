#!/usr/bin/env bash
# PreToolUse hook on `gh pr create`. Keeps docs from going stale: if the branch changed
# engine/** but updated NONE of the docs, block PR creation until docs are synced — or until
# an explicit 'Docs-Synced: <reason>' marker in the PR body acknowledges no doc change is
# needed. Mirrors scripts/pr-review-gate.sh. Silent (allow) otherwise.
set -uo pipefail

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c \
  "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)

# SELF-GUARD: the hook `if` filter fires on every Bash command — only act on a real
# `gh pr create`. Everything else passes through untouched.
case "$CMD" in
  *"gh pr create"*) ;;
  *) exit 0 ;;
esac

DIR="${CLAUDE_PROJECT_DIR:-/Users/bheemendergurram/untold_game_agents}"
cd "$DIR" 2>/dev/null || exit 0

CHANGED=$(git diff --name-only origin/main...HEAD 2>/dev/null)

# Only care when engine/** changed. No engine change → nothing to keep in sync.
printf '%s\n' "$CHANGED" | grep -qE '^engine/' || exit 0

# Docs updated in the same branch? Then they're in sync — pass.
if printf '%s\n' "$CHANGED" | grep -qE '(^|/)(CLAUDE\.md|README([.-][^/]*)?|HANDOFF\.md)$|^docs/'; then
  exit 0
fi

# Explicit acknowledgement that no doc change is needed.
if printf '%s' "$CMD" | grep -qE 'Docs-Synced:[[:space:]]*[^[:space:]]+'; then exit 0; fi

cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"engine/** changed but no docs were updated in this branch. Keep project info from going stale: update the docs this change affects (CLAUDE.md status/entrypoints, README, docs/execution-plan, docs/adr, HANDOFF.md), then recreate the PR. If no doc change is genuinely needed, add 'Docs-Synced: <reason>' to the PR body to acknowledge."}}
JSON
