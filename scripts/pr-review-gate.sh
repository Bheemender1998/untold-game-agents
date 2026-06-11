#!/usr/bin/env bash
# PreToolUse hook on `gh pr create`. Blocks PR creation when engine/**.py changed vs main
# without a review trailer. Emits a PreToolUse deny on violation; silent (allow) otherwise.
# TUG's analog of ConvictionFinder's pr-adversarial-gate.sh.
set -uo pipefail

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c \
  "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)

# SELF-GUARD: only act on an actual `gh pr create` (the hook `if` filter isn't reliable —
# it fires on every Bash command). Everything else passes through untouched.
case "$CMD" in
  *"gh pr create"*) ;;
  *) exit 0 ;;
esac

DIR="${CLAUDE_PROJECT_DIR:-/Users/bheemendergurram/untold_game_agents}"
cd "$DIR" 2>/dev/null || exit 0

# Only gate engine/*.py logic changes. Dashboard/config/docs PRs auto-pass.
ENGINE=$(git diff --name-only origin/main...HEAD 2>/dev/null | grep -E 'engine/.*\.py$' || true)
[ -z "$ENGINE" ] && exit 0

# Trailer present? (Adversarial-Reviewed: <agentId>  — or  Review-Skip: <reason> for docs/renames)
if printf '%s' "$CMD" | grep -qE '(Adversarial-)?Reviewed:[[:space:]]*[A-Za-z0-9]{6,}'; then exit 0; fi
if printf '%s' "$CMD" | grep -qE 'Review-Skip:[[:space:]]*[^[:space:]]+'; then exit 0; fi

cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"engine/*.py changed but the PR body has no review trailer. Run the ship-video-change skill (pytest + dual review), then add 'Adversarial-Reviewed: <agentId>' to the PR body (or 'Review-Skip: <reason>' for docs/renames only)."}}
JSON
