#!/usr/bin/env bash
set -euo pipefail

REPO="/Users/evgenianosko/.openclaw/workspace/pm-hl-conservative-plus-repo"
RUNNER="/Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py"
PROFILE="${1:-conservative}"

if [[ "$PROFILE" != "conservative" && "$PROFILE" != "aggressive" ]]; then
  echo "Usage: $0 [conservative|aggressive]"
  exit 2
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$REPO/runtime/btc5m_${PROFILE}_${STAMP}.log"

mkdir -p "$REPO/runtime"

echo "[{\"ts\":\"$(date -u +%FT%TZ)\",\"event\":\"start\",\"profile\":\"$PROFILE\",\"stake_usd\":5,\"mode\":\"execute\"}]" | tee -a "$LOG"

cd "$REPO"
set +e
PYTHONUNBUFFERED=1 .venv/bin/python "$RUNNER" --profile "$PROFILE" --execute 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}
set -e

echo "[{\"ts\":\"$(date -u +%FT%TZ)\",\"event\":\"finish\",\"profile\":\"$PROFILE\",\"exit_code\":$RC}]" | tee -a "$LOG"
exit $RC
