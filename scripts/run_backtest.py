#!/usr/bin/env python3
"""Run historical backtest on recent BTC 5m markets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.engine import BacktestConfig, run_backtest
from src.backtest.historical_data import load_recent_rounds


def render_markdown(report: dict) -> str:
    s = report["summary"]
    c = report["config"]
    lines = [
        "# BTC 5m Backtest Report",
        "",
        f"- **Profile**: `{c['profile']}`",
        f"- **Threshold**: {c['threshold']}",
        f"- **Stake**: ${c['stake_usd']}",
        f"- **Stop loss**: {int(c['stop_loss_pct'] * 100)}%",
        f"- **Entry window**: {c['entry_window']['window_min_sec']:.0f}-{c['entry_window']['window_max_sec']:.0f}s",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| Rounds loaded | {s['rounds_loaded']} |",
        f"| Trades | {s['trades']} |",
        f"| No trade | {s['no_trade']} |",
        f"| Wins | {s['wins']} |",
        f"| Losses | {s['losses']} |",
        f"| Stopped out | {s['stopped_out']} |",
        f"| Win rate | {s['win_rate']*100:.1f}% |",
        f"| Total PnL | ${s['total_pnl_usd']:+.2f} |",
        f"| Avg PnL / trade | ${s['avg_pnl_usd']:+.2f} |",
        "",
        "## Trades",
        "",
    ]
    for t in report["trades"]:
        if t["status"] == "no_trade":
            continue
        lines.append(
            f"- `{t['slug']}` {t['status']} {t['side']} @{t['entry_price']} "
            f"left={t['seconds_left']:.0f}s winner={t['winner']} pnl=${t['pnl_usd']:+.2f}"
        )
    lines.append("")
    lines.append(
        "> Uses CLOB minute price history as ask proxy. Results are approximate, not live execution replay."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest BTC 5m strategy on recent closed markets")
    ap.add_argument("--profile", choices=["conservative", "aggressive"], default="conservative")
    ap.add_argument("--hours", type=float, default=4.0, help="Lookback hours of closed 5m rounds")
    ap.add_argument("--threshold", type=float, default=0.70)
    ap.add_argument("--stake-usd", type=float, default=5.0)
    ap.add_argument("--stop-loss-pct", type=float, default=0.25)
    ap.add_argument("--no-entry-window", action="store_true")
    ap.add_argument("--out-json", default=str(ROOT / "reports" / "backtest_latest.json"))
    ap.add_argument("--out-md", default=str(ROOT / "reports" / "backtest_latest.md"))
    args = ap.parse_args()

    print(f"[backtest] loading last {args.hours}h of closed rounds...")
    rounds = load_recent_rounds(hours=args.hours)
    cfg = BacktestConfig(
        profile=args.profile,
        threshold=args.threshold,
        stake_usd=args.stake_usd,
        stop_loss_pct=args.stop_loss_pct,
        apply_entry_window=not args.no_entry_window,
    )
    report = run_backtest(rounds, cfg)

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")

    s = report["summary"]
    print(f"rounds={s['rounds_loaded']} trades={s['trades']} wins={s['wins']} losses={s['losses']}")
    print(f"total_pnl=${s['total_pnl_usd']:+.2f} win_rate={s['win_rate']*100:.1f}%")
    print(f"JSON: {out_json}")
    print(f"Markdown: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())