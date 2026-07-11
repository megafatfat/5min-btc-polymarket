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

PROFILES = {
    "conservative": {"threshold": 0.70, "min_entry_seconds_left": 60, "poll_sec": 5.0},
    "aggressive": {"threshold": 0.70, "min_entry_seconds_left": 60, "poll_sec": 5.0},
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Dry-run BTC 5m signal monitor (no credentials required)")
    ap.add_argument("--profile", choices=["conservative", "aggressive"], default="conservative")
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--min-entry-seconds-left", type=int, default=None)
    ap.add_argument("--poll-sec", type=float, default=None)
    ap.add_argument("--duration-min", type=int, default=5, help="How long to monitor before exiting")
    ap.add_argument("--json", action="store_true", help="Print one JSON object per poll")
    args = ap.parse_args()

    prof = PROFILES[args.profile]
    threshold = args.threshold if args.threshold is not None else prof["threshold"]
    min_entry = (
        args.min_entry_seconds_left
        if args.min_entry_seconds_left is not None
        else prof["min_entry_seconds_left"]
    )
    poll_sec = args.poll_sec if args.poll_sec is not None else prof["poll_sec"]

    deadline = time.time() + max(1, args.duration_min) * 60
    signals = 0

    print(
        f"[dry-run] profile={args.profile} threshold={threshold} "
        f"min_entry_sec={min_entry} duration_min={args.duration_min}",
        flush=True,
    )

    while time.time() < deadline:
        snap = evaluate_entry_signal(threshold=threshold, min_entry_seconds_left=min_entry)
        if snap.get("status") == "signal_ready":
            signals += 1

        if args.json:
            print(json.dumps(snap, ensure_ascii=False), flush=True)
        else:
            status = snap.get("status", "unknown")
            slug = snap.get("slug", "-")
            sec_left = snap.get("seconds_left")
            up_ask = snap.get("clob_up_ask")
            dn_ask = snap.get("clob_down_ask")
            extra = ""
            if status == "signal_ready":
                extra = f" side={snap.get('side')} trigger={snap.get('trigger_price')}"
            print(
                f"{snap.get('ts')} {status:28} slug={slug} "
                f"left={sec_left if sec_left is not None else '-'}s "
                f"up_ask={up_ask} dn_ask={dn_ask}{extra}",
                flush=True,
            )

        time.sleep(poll_sec)

    print(f"[dry-run] finished signals={signals}", flush=True)


if __name__ == "__main__":
    main()