#!/usr/bin/env bash
# Overnight unattended render. Fired by launchd (com.untoldgame.overnight) at 01:00.
# launchd hands us a minimal environment, so set PATH and load .env explicitly —
# this is the #1 thing that breaks unattended macOS jobs.
set -uo pipefail

# Hold the Mac awake for the whole run — idle sleep would pause the 45-min render.
# Re-exec self once under caffeinate (-i no idle sleep, -s no system sleep on AC).
# Re-invoke via /bin/bash (matching launchd) so this works even without the +x bit;
# full paths because launchd's minimal env may not have /usr/bin on PATH yet.
if [ -z "${_OVERNIGHT_CAFFEINATED:-}" ]; then
  export _OVERNIGHT_CAFFEINATED=1
  exec /usr/bin/caffeinate -i -s -- /bin/bash "$0" "$@"
fi

REPO="/Users/bheemendergurram/untold_game_agents"
cd "$REPO" || exit 1

# node/npx (Remotion render) + python3 + ffmpeg all live in homebrew on this M2.
# Render is shelled by run_auto into .venv-video, which inherits this PATH.
# IMPORTANT: system dirs (/usr/bin:/bin) MUST precede /usr/local/bin. This machine has
# copies of Apple platform coreutils (mkdir/ls/cp/…) in /usr/local/bin that AMFI SIGKILLs
# on exec ("Killed: 9", not in trust cache) — putting /usr/local/bin first made the job die
# at the first `mkdir`. Homebrew stays first for python3/node/ffmpeg; /usr/local/bin last.
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:$PATH"
if [ -f .env ]; then set -a; set +u; . ./.env; set -u; set +a; fi

# One id ties every API call in tonight's run together for the cost report.
export TUG_RUN_ID="$(date +%Y-%m-%dT%H:%M:%S)"

mkdir -p logs
LOG="logs/overnight-$(date +%Y-%m-%d).log"

{
  echo "=== overnight run $(date) ==="
  echo "-- ideate: top up the queue (headless) --"
  python3 -m engine.run_pipeline --no-review || echo "(ideate failed — non-fatal, continuing)"
  echo "-- produce + render + QC (count=3) --"
  python3 -m engine.run_auto --count 3 || echo "(run_auto exited $? — see above)"
  echo "-- API cost summary for this run --"
  python3 -m engine.run_cost_report --run "$TUG_RUN_ID" || true
  echo "=== done $(date) ==="
} >>"$LOG" 2>&1
