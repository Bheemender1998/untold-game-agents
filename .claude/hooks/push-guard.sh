#!/usr/bin/env bash
# PreToolUse(Bash) — deny a direct `git push` while the PUSHING checkout is on main.
# SELF-GUARDS on the actual command read from stdin, because the hook-level `if` filter did
# not reliably scope to git-push (it fired on every Bash command on main, blocking
# everything). Only real pushes-from-a-main-checkout are blocked; every other command passes
# through untouched.
#
# Worktree-aware: inspects the branch of the directory the push actually runs in (the hook's
# `cwd`), NOT a hardcoded checkout. A feature-branch push from a git worktree is therefore
# allowed even when the main checkout happens to sit on main. Falls back to CLAUDE_PROJECT_DIR
# if `cwd` is absent, so behaviour is unchanged when it isn't provided.
set -uo pipefail

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)
case "$CMD" in
  *"git push"*) ;;   # a push — fall through to the branch check
  *) exit 0 ;;       # anything else — allow, do nothing
esac

CWD=$(printf '%s' "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd','') or '')" 2>/dev/null)
DIR="${CWD:-${CLAUDE_PROJECT_DIR:-/Users/bheemendergurram/untold_game_agents}}"

if [ "$(git -C "$DIR" branch --show-current 2>/dev/null)" = "main" ]; then
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"On main: never push main directly. Branch (feat/...), open a PR, then merge — that pushes main for you."}}
JSON
fi
exit 0
