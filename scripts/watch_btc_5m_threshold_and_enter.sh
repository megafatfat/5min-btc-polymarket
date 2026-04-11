#!/usr/bin/env bash
set -euo pipefail

REPO="/Users/evgenianosko/.openclaw/workspace/pm-hl-conservative-plus-repo"
PY="/Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/run_btc_5m_threshold_test.py"
LOG="$REPO/runtime/btc_5m_threshold_watch.log"
STATE="$REPO/runtime/btc_5m_threshold_watch.state"

THRESHOLD="${1:-0.75}"
STAKE="${2:-4}"
SLEEP_SEC="${3:-20}"
MAX_MIN="${4:-180}"

mkdir -p "$REPO/runtime"
start_ts=$(date +%s)
end_ts=$((start_ts + MAX_MIN*60))

echo "[$(date -u +%FT%TZ)] start watch threshold=$THRESHOLD stake=$STAKE sleep=$SLEEP_SEC max_min=$MAX_MIN" | tee -a "$LOG"

while true; do
  now=$(date +%s)
  if [ "$now" -ge "$end_ts" ]; then
    echo "[$(date -u +%FT%TZ)] timeout reached, stop" | tee -a "$LOG"
    exit 0
  fi

  out=$(cd "$REPO" && .venv/bin/python "$PY" --threshold "$THRESHOLD" --stake-usd "$STAKE" --execute 2>&1 || true)
  echo "$out" >> "$LOG"

  # if decision enter and runner returned success/matched -> stop
  if echo "$out" | grep -q '"decision": "enter"'; then
    if echo "$out" | grep -q '"success": true\|"status": "matched"\|"order_post_result"'; then
      echo "[$(date -u +%FT%TZ)] entry attempted, stopping watcher" | tee -a "$LOG"
      echo "entered_at=$(date -u +%FT%TZ)" > "$STATE"
      exit 0
    fi
  fi

  sleep "$SLEEP_SEC"
done
