#!/usr/bin/env bash
set -euo pipefail
MODE="${1:-8h}"
REPO_DIR="${REPO_DIR:-/ABS/PATH/TO/iran-watch-openclaw}"
cd "$REPO_DIR"
python -m iran_watch run --mode "$MODE" >> out/cron.log 2>&1
