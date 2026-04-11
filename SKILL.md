---
name: btc-5m-live
description: Run and monitor live/paper BTC 5-minute Up/Down trading on Polymarket with strict entry trigger by market price threshold (e.g. >=0.70), fixed stake sizing, and one-shot or loop execution. Use when user asks to trade BTC 5m markets, backtest/replay threshold entries, or run controlled real-money tests.
---

# BTC 5m Live

## Paths
- Repo: `/Users/evgenianosko/.openclaw/workspace/pm-hl-conservative-plus-repo`
- Runner: `src/live/pm_live_trade_runner.py`
- Wrapper: `scripts/run_btc_5m_threshold_test.py`

## Rules
- Use fixed stake via `--stake-usd`.
- Enter only if `UP >= threshold` or `DOWN >= threshold`.
- If both satisfy, pick higher price.
- Default threshold: `0.70`.
- Default mode: dry-run; use `--execute` for real orders.

## One-shot real test
From repo root:

```bash
.venv/bin/python /Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py --profile conservative --execute
```

Aggressive profile:

```bash
.venv/bin/python /Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py --profile aggressive --execute
```

Override any profile parameter manually (example):

```bash
.venv/bin/python /Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py --profile conservative --stake-usd 5 --entry-timeout-min 90 --execute
```

## Strategy Profiles
- Profiles file: `config/btc_5m_profiles.yaml`
- Contains two presets: `conservative` and `aggressive`
- Test period default stake is set to **$5** for both profiles.
- Includes strict entry/exit, heartbeat/controller checks, market state validation, hedge rules, and CLOB-based trigger pricing.

## Hot Commands (Telegram-friendly)
Use one of these phrases in chat:
- `btc5m консервативный старт`
- `btc5m агрессивный старт`

Handler script:
- `scripts/btc5m_hot.sh [conservative|aggressive]`
- Writes full run log to `runtime/btc5m_<profile>_<UTCSTAMP>.log`
- Intended chat behavior: send start ack, short autolog updates, and final report after completion.

## Notes
- Wrapper resolves current BTC 5m market slug (`btc-updown-5m-<bucket>`).
- Real order placement is delegated to `pm_live_trade_runner.py` with `--force-side` and `--max-notional-usd`.
- Logs are written to stdout JSON for audit.
