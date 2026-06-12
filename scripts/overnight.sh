#!/usr/bin/env bash
# Overnight unattended render. Fired by launchd (com.untoldgame.overnight) at 01:00.
# launchd hands us a minimal environment, so set PATH and load .env explicitly —
# this is the #1 thing that breaks unattended macOS jobs.
set -uo pipefail

REPO="/Users/bheemendergurram/untold_game_agents"
cd "$REPO" || exit 1

# node/npx (Remotion render) + python3 + ffmpeg all live in homebrew on this M2.
# Render is shelled by run_auto into .venv-video, which inherits this PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
[ -f .env ] && set -a && . ./.env && set +a

mkdir -p logs
LOG="logs/overnight-$(date +%Y-%m-%d).log"

{
  echo "=== overnight run $(date) ==="
  echo "-- ideate: top up the queue (headless) --"
  python3 -m engine.run_pipeline --no-review || echo "(ideate failed — non-fatal, continuing)"
  echo "-- produce + render + QC (count=3) --"
  python3 -m engine.run_auto --count 3
  echo "=== done $(date) ==="
} >>"$LOG" 2>&1
