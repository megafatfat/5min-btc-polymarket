"""Public Polymarket market data helpers for dry-run development."""

from __future__ import annotations

import datetime as dt
import json
import time
from typing import Any, Optional

import requests
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

UTC = dt.timezone.utc
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


def bucket_5m(ts: int) -> int:
    return ts - (ts % 300)


def fetch_event(slug: str) -> Optional[dict[str, Any]]:
    r = requests.get(f"{GAMMA_BASE}/events", params={"slug": slug}, timeout=12)
    r.raise_for_status()
    arr = r.json()
    return arr[0] if arr else None


def parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def market_side_prices(market: dict[str, Any]) -> tuple[float, float, str, str, str, str]:
    outcomes = parse_json_field(market.get("outcomes")) or []
    prices = parse_json_field(market.get("outcomePrices")) or []
    token_ids = parse_json_field(market.get("clobTokenIds")) or []
    if len(prices) < 2 or len(token_ids) < 2:
        raise RuntimeError("missing outcomePrices/clobTokenIds")

    up_i, down_i = 0, 1
    labels = [str(x).lower() for x in outcomes[:2]] if isinstance(outcomes, list) else []
    if len(labels) >= 2 and ("up" in labels[1] or "yes" in labels[1]):
        up_i, down_i = 1, 0

    up_p = float(prices[up_i])
    dn_p = float(prices[down_i])
    up_t = str(token_ids[up_i])
    dn_t = str(token_ids[down_i])
    slug = str(market.get("slug") or market.get("_event_slug") or "")
    end_iso = str(market.get("endDate") or market.get("endDateIso") or "")
    return up_p, dn_p, up_t, dn_t, slug, end_iso


def _best_bid_ask(book) -> tuple[Optional[float], Optional[float]]:
    bids = getattr(book, "bids", []) or []
    asks = getattr(book, "asks", []) or []
    best_bid = None
    best_ask = None
    for bid in bids:
        price = float(getattr(bid, "price", 0) or 0)
        if best_bid is None or price > best_bid:
            best_bid = price
    for ask in asks:
        price = float(getattr(ask, "price", 0) or 0)
        if best_ask is None or price < best_ask:
            best_ask = price
    return best_bid, best_ask


def clob_side_prices(
    up_token: str,
    down_token: str,
    clob_base: str = CLOB_BASE,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    pub = ClobClient(host=clob_base, chain_id=POLYGON)
    up_book = pub.get_order_book(str(up_token))
    dn_book = pub.get_order_book(str(down_token))
    up_bid, up_ask = _best_bid_ask(up_book)
    dn_bid, dn_ask = _best_bid_ask(dn_book)

    picked_spread = None
    if up_ask is not None and up_bid is not None:
        picked_spread = max(0.0, up_ask - up_bid)
    if dn_ask is not None and dn_bid is not None:
        spread = max(0.0, dn_ask - dn_bid)
        picked_spread = spread if picked_spread is None else min(picked_spread, spread)

    return up_ask, dn_ask, picked_spread


def resolve_active_current_5m_market() -> Optional[dict[str, Any]]:
    now = int(time.time())
    slug = f"btc-updown-5m-{bucket_5m(now)}"

    try:
        event = fetch_event(slug)
    except Exception:
        return None
    if not event:
        return None

    markets = event.get("markets") or []
    if not markets:
        return None

    market = markets[0]
    if market.get("closed") is True or market.get("active") is False:
        return None

    end_iso = str(market.get("endDate") or market.get("endDateIso") or "")
    try:
        end_ts = dt.datetime.fromisoformat(end_iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None

    sec_left = end_ts - time.time()
    if sec_left <= 5:
        return None

    enriched = dict(market)
    enriched["_event_slug"] = slug
    enriched["_seconds_left"] = sec_left
    return enriched


def evaluate_entry_signal(
    threshold: float,
    min_entry_seconds_left: int,
) -> dict[str, Any]:
    market = resolve_active_current_5m_market()
    if not market:
        return {"status": "no_market", "ts": dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")}

    gamma_up, gamma_dn, up_token, dn_token, slug, end_iso = market_side_prices(market)
    sec_left = float(market.get("_seconds_left") or 0)

    if sec_left < min_entry_seconds_left:
        return {
            "status": "skip_too_late_to_enter",
            "slug": slug,
            "seconds_left": sec_left,
            "min_entry_seconds_left": min_entry_seconds_left,
            "gamma_up": gamma_up,
            "gamma_down": gamma_dn,
            "ts": dt.datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    try:
        up_ask, dn_ask, spread = clob_side_prices(up_token, dn_token)
    except Exception as exc:
        return {
            "status": "skip_clob_unavailable",
            "slug": slug,
            "error": str(exc),
            "ts": dt.datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    candidates: list[tuple[str, float]] = []
    if up_ask is not None and float(up_ask) >= threshold:
        candidates.append(("UP", float(up_ask)))
    if dn_ask is not None and float(dn_ask) >= threshold:
        candidates.append(("DOWN", float(dn_ask)))

    payload: dict[str, Any] = {
        "status": "heartbeat",
        "slug": slug,
        "seconds_left": sec_left,
        "gamma_up": gamma_up,
        "gamma_down": gamma_dn,
        "clob_up_ask": up_ask,
        "clob_down_ask": dn_ask,
        "min_spread": spread,
        "threshold": threshold,
        "ts": dt.datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if not candidates:
        payload["status"] = "skip_price_below_threshold"
        return payload

    side, trigger_price = sorted(candidates, key=lambda item: item[1], reverse=True)[0]
    payload["status"] = "signal_ready"
    payload["side"] = side
    payload["trigger_price"] = trigger_price
    payload["dry_run_action"] = "would_open"
    return payload