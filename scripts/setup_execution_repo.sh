#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECTS_ROOT="$(cd "$SKILL_ROOT/.." && pwd)"
EXEC_REPO="${BTC5M_REPO:-$PROJECTS_ROOT/pm-hl-conservative-plus-repo}"
UPSTREAM="https://github.com/Novals83/polymarket-hl-strategy.git"

echo "[setup] execution repo target: $EXEC_REPO"

if [[ ! -d "$EXEC_REPO/.git" ]]; then
  git clone "$UPSTREAM" "$EXEC_REPO"
fi

cd "$EXEC_REPO"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f "$EXEC_REPO/.env" ]]; then
  cp .env.example .env
fi

if [[ -f "$SKILL_ROOT/.env" ]]; then
  ln -sf "$SKILL_ROOT/.env" "$EXEC_REPO/.env"
  echo "[setup] linked $EXEC_REPO/.env -> $SKILL_ROOT/.env"
fi

python "$SKILL_ROOT/scripts/patch_execution_repo.py" --repo "$EXEC_REPO"

echo "[setup] done"
echo "Next:"
echo "  1) Fill credentials in $SKILL_ROOT/.env"
echo "  2) Dry-run:  cd $SKILL_ROOT && source .venv/bin/activate && python scripts/test_btc_5m_session_exit_sl.py --profile conservative --entry-timeout-min 3"
echo "  3) Live test: python scripts/test_btc_5m_session_exit_sl.py --profile conservative --execute"