#!/usr/bin/env python3
"""Lightweight public-API monitor for dry-run development (no wallet/API keys)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.market_feed import evaluate_entry_signal
from src.risk.skew_hedge import load_hedge_config
from src.signal.entry_window import load_entry_window_config

PROFILES = {
    "conservative": {"threshold": 0.70, "poll_sec": 5.0},
    "aggressive": {"threshold": 0.70, "poll_sec": 5.0},
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Dry-run BTC 5m signal monitor (no credentials required)")
    ap.add_argument("--profile", choices=["conservative", "aggressive"], default="conservative")
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--min-entry-seconds-left", type=int, default=None)
    ap.add_argument("--entry-window-target", type=int, default=None)
    ap.add_argument("--entry-window-tolerance", type=int, default=None)
    ap.add_argument("--no-entry-window", action="store_true", help="Disable 120s entry window filter")
    ap.add_argument("--no-hedge", action="store_true", help="Disable extreme skew hedge evaluation")
    ap.add_argument("--poll-sec", type=float, default=None)
    ap.add_argument("--duration-min", type=int, default=5, help="How long to monitor before exiting")
    ap.add_argument("--json", action="store_true", help="Print one JSON object per poll")
    args = ap.parse_args()

    prof = PROFILES[args.profile]
    threshold = args.threshold if args.threshold is not None else prof["threshold"]
    poll_sec = args.poll_sec if args.poll_sec is not None else prof["poll_sec"]
    entry_window = load_entry_window_config(profile=args.profile)
    if args.min_entry_seconds_left is not None:
        entry_window = entry_window.__class__(
            target_sec=entry_window.target_sec,
            tolerance_sec=entry_window.tolerance_sec,
            min_entry_seconds_left=args.min_entry_seconds_left,
        )
    if args.entry_window_target is not None:
        entry_window = entry_window.__class__(
            target_sec=args.entry_window_target,
            tolerance_sec=entry_window.tolerance_sec,
            min_entry_seconds_left=entry_window.min_entry_seconds_left,
        )
    if args.entry_window_tolerance is not None:
        entry_window = entry_window.__class__(
            target_sec=entry_window.target_sec,
            tolerance_sec=args.entry_window_tolerance,
            min_entry_seconds_left=entry_window.min_entry_seconds_left,
        )

    hedge_cfg = load_hedge_config(profile=args.profile)
    deadline = time.time() + max(1, args.duration_min) * 60
    signals = 0
    hedges = 0

    print(
        f"[dry-run] profile={args.profile} threshold={threshold} "
        f"entry_window={entry_window.window_min_sec:.0f}-{entry_window.window_max_sec:.0f}s "
        f"hedge_gte={hedge_cfg.trigger_side_price_gte} hedge_left_lte={hedge_cfg.trigger_seconds_left_lte}s "
        f"duration_min={args.duration_min}",
        flush=True,
    )

    while time.time() < deadline:
        snap = evaluate_entry_signal(
            threshold=threshold,
            entry_window=entry_window,
            apply_entry_window=not args.no_entry_window,
            profile=args.profile,
            hedge_config=hedge_cfg,
            apply_hedge=not args.no_hedge,
        )
        if snap.get("status") == "signal_ready":
            signals += 1
        if (snap.get("hedge") or {}).get("hedge_triggered"):
            hedges += 1

        if args.json:
            print(json.dumps(snap, ensure_ascii=False), flush=True)
        else:
            status = snap.get("status", "unknown")
            slug = snap.get("slug", "-")
            sec_left = snap.get("seconds_left")
            up_ask = snap.get("clob_up_ask")
            dn_ask = snap.get("clob_down_ask")
            extra = ""
            if snap.get("side"):
                extra = f" side={snap.get('side')} trigger={snap.get('trigger_price')}"
                if status != "signal_ready":
                    extra += f" ({status})"
            hedge = snap.get("hedge") or {}
            if hedge.get("hedge_triggered"):
                extra += (
                    f" hedge={hedge.get('hedge_side')}"
                    f" ${hedge.get('hedge_notional_usd')}"
                    f"@{hedge.get('hedge_price')}"
                )
            print(
                f"{snap.get('ts')} {status:28} slug={slug} "
                f"left={sec_left if sec_left is not None else '-'}s "
                f"up_ask={up_ask} dn_ask={dn_ask}{extra}",
                flush=True,
            )

        time.sleep(poll_sec)

    print(f"[dry-run] finished signals={signals} hedges={hedges}", flush=True)


if __name__ == "__main__":
    main()