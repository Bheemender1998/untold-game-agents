#!/usr/bin/env bash
# The Untold Game — nightly batch: produce + render 3 long-form videos for AM review.
# Run by launchd (com.untoldgame.overnight) at 01:00. Render is local (M2).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
exec python3 -m engine.run_auto --count 3
