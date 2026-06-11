#!/usr/bin/env bash
# PostToolUse hook (asyncRewake). After an edit to engine/**.py (excluding tests),
# run the test suite. Silent on pass; wakes Claude (exit 2) with failures on fail.
# TUG's analog of ConvictionFinder's analyzer contract test.
set -uo pipefail

INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | python3 -c \
  "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

# Only fire for engine Python source — not tests, not the Remotion/TS render code.
case "$FILE" in
  *engine/*.py)
    case "$FILE" in *"/tests/"*|*"/test_"*) exit 0 ;; esac ;;
  *) exit 0 ;;
esac

DIR="${CLAUDE_PROJECT_DIR:-/Users/bheemendergurram/untold_game_agents}"
cd "$DIR" || { echo "hook: cannot cd $DIR — run 'python3 -m pytest tests/ -q' manually."; exit 2; }

# Tests run under python3 (main env), never .venv-video (qc/run_auto import only stdlib).
# `timeout`/`gtimeout` is GNU coreutils — absent on stock macOS, so guard for it.
TO=$(command -v timeout || command -v gtimeout || true)
OUT=$([ -n "$TO" ] && "$TO" 120 python3 -m pytest tests/ -q 2>&1 || python3 -m pytest tests/ -q 2>&1); ST=$?
if [ "$ST" -ne 0 ]; then
  echo "Tests FAILED after editing $FILE:"; printf '%s\n' "$OUT" | tail -15; exit 2
fi
exit 0
