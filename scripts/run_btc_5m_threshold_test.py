#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from typing import Optional

import requests
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON


def utc_now_ts() -> int:
    return int(dt.datetime.now(dt.timezone.utc).timestamp())


def bucket_5m(ts: int) -> int:
    return ts - (ts % 300)


def fetch_gamma_market(slug: str) -> Optional[dict]:
    r = requests.get("https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=15)
    r.raise_for_status()
    arr = r.json()
    if not arr:
        return None
    ev = arr[0]
    mkts = ev.get("markets") or []
    return mkts[0] if mkts else None


def resolve_active_btc_5m() -> Optional[dict]:
    now = utc_now_ts()
    cur = bucket_5m(now)
    slug = f"btc-updown-5m-{cur}"
    m = fetch_gamma_market(slug)
    if not m:
        return None
    if m.get("closed") is True:
        return None
    if m.get("active") is False:
        return None
    end_iso = str(m.get("endDate") or m.get("endDateIso") or "")
    try:
        end_ts = dt.datetime.fromisoformat(end_iso.replace('Z', '+00:00')).timestamp()
    except Exception:
        return None
    if end_ts <= time.time() + 5:
        return None
    mm = dict(m)
    mm["_resolved_slug"] = slug
    return mm


def parse_json_field(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def _best_bid_ask(book):
    bids = getattr(book, "bids", []) or []
    asks = getattr(book, "asks", []) or []
    best_bid = None
    best_ask = None
    for b in bids:
        p = float(getattr(b, "price", 0) or 0)
        if best_bid is None or p > best_bid:
            best_bid = p
    for a in asks:
        p = float(getattr(a, "price", 0) or 0)
        if best_ask is None or p < best_ask:
            best_ask = p
    return best_bid, best_ask


def choose_side(market: dict, threshold: float, clob_base: str = "https://clob.polymarket.com"):
    outcomes = parse_json_field(market.get("outcomes")) or []
    prices = parse_json_field(market.get("outcomePrices")) or []
    token_ids = parse_json_field(market.get("clobTokenIds")) or []
    if len(prices) < 2 or len(token_ids) < 2:
        raise RuntimeError("No outcomePrices/clobTokenIds in market")

    # fallback assumption: [UP, DOWN]
    up_i, down_i = 0, 1
    labs = [str(x).lower() for x in outcomes[:2]] if isinstance(outcomes, list) else []
    if len(labs) >= 2 and ("up" in labs[1] or "yes" in labs[1]):
        up_i, down_i = 1, 0

    up = float(prices[up_i])
    down = float(prices[down_i])
    up_token = str(token_ids[up_i])
    down_token = str(token_ids[down_i])

    pub = ClobClient(host=clob_base, chain_id=POLYGON)
    up_book = pub.get_order_book(up_token)
    dn_book = pub.get_order_book(down_token)
    _, up_ask = _best_bid_ask(up_book)
    _, dn_ask = _best_bid_ask(dn_book)

    candidates = []
    if up_ask is not None and up_ask >= threshold:
        candidates.append(("UP", up_ask))
    if dn_ask is not None and dn_ask >= threshold:
        candidates.append(("DOWN", dn_ask))
    if not candidates:
        return None, up, down, up_ask, dn_ask
    side, price = sorted(candidates, key=lambda x: x[1], reverse=True)[0]
    return (side, price), up, down, up_ask, dn_ask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.70)
    ap.add_argument("--stake-usd", type=float, default=4.0)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--repo", default="/Users/evgenianosko/.openclaw/workspace/pm-hl-conservative-plus-repo")
    args = ap.parse_args()

    market = resolve_active_btc_5m()
    if not market:
        print(json.dumps({"ok": False, "reason": "no_active_btc_5m_market_found"}, ensure_ascii=False))
        sys.exit(2)

    end_iso = str(market.get("endDate") or market.get("endDateIso") or "")
    sec_left = None
    try:
        sec_left = dt.datetime.fromisoformat(end_iso.replace('Z', '+00:00')).timestamp() - time.time()
    except Exception:
        sec_left = None

    picked, up, down, up_ask, down_ask = choose_side(market, args.threshold)
    payload = {
        "ok": True,
        "mode": "execute" if args.execute else "dry_run",
        "market_slug": market.get("slug") or market.get("_resolved_slug"),
        "question": market.get("question"),
        "seconds_left": sec_left,
        "prices": {"up": up, "down": down},
        "clob_asks": {"up": up_ask, "down": down_ask},
        "threshold": args.threshold,
        "stake_usd": args.stake_usd,
    }

    if sec_left is None:
        payload["decision"] = "skip"
        payload["reason"] = "bad_market_end_time"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if sec_left < 60:
        payload["decision"] = "skip"
        payload["reason"] = "too_late_to_enter"
        payload["min_entry_seconds_left"] = 60
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not picked:
        payload["decision"] = "skip"
        payload["reason"] = "no_side_above_threshold"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    side, entry_price = picked
    payload["decision"] = "enter"
    payload["side"] = side
    payload["entry_price"] = entry_price

    cmd = [
        ".venv/bin/python",
        "src/live/pm_live_trade_runner.py",
        "--market-slug",
        str(payload["market_slug"]),
        "--force-side",
        side,
        "--start-equity",
        "100",
        "--risk-frac",
        str(args.stake_usd / 100.0),
        "--max-notional-usd",
        str(args.stake_usd),
    ]
    if args.execute:
        cmd.append("--execute")

    payload["runner_cmd"] = " ".join(cmd)
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    p = subprocess.run(cmd, cwd=args.repo, capture_output=True, text=True)
    print(p.stdout)
    if p.returncode != 0:
        print(p.stderr, file=sys.stderr)
        sys.exit(p.returncode)


if __name__ == "__main__":
    main()
