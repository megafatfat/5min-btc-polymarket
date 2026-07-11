#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
REPORTS_DIR="$ROOT/reports"
mkdir -p "$REPORTS_DIR"

PROFILE="${1:-conservative}"
DURATION_MIN="${2:-5}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$REPORTS_DIR/dry_run_${PROFILE}_${STAMP}.json"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Missing venv. Run: python3 -m venv $ROOT/.venv && source $ROOT/.venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

echo "Running canonical dry-run (no --execute) -> $OUT"
"$VENV_PY" "$ROOT/scripts/test_btc_5m_session_exit_sl.py" \
  --profile "$PROFILE" \
  --entry-timeout-min "$DURATION_MIN" \
  --poll-sec 3 \
  >"$OUT"

echo "Saved report: $OUT"
tail -n 30 "$OUT"