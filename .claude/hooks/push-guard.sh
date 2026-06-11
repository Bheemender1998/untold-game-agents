#!/usr/bin/env bash
# PreToolUse(Bash) — deny a direct `git push` while on main. SELF-GUARDS on the actual
# command read from stdin, because the hook-level `if` filter did not reliably scope to
# git-push (it fired on every Bash command on main, blocking everything). Only real
# pushes-to-main are blocked; every other command passes through untouched.
set -uo pipefail

CMD=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)
case "$CMD" in
  *"git push"*) ;;   # a push — fall through to the branch check
  *) exit 0 ;;       # anything else — allow, do nothing
esac

DIR="${CLAUDE_PROJECT_DIR:-/Users/bheemendergurram/untold_game_agents}"
if [ "$(git -C "$DIR" branch --show-current 2>/dev/null)" = "main" ]; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"On main: never push main directly. Branch (feat/...), open a PR, then merge — that pushes main for you."}}
JSON
fi
exit 0
