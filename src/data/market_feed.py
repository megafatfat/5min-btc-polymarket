"""Public Polymarket market data helpers for dry-run development."""

from __future__ import annotations

import datetime as dt
import json
import time
from typing import Any, Optional

import requests
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

from src.risk.skew_hedge import HedgeConfig, evaluate_skew_hedge, load_hedge_config
from src.signal.entry_window import EntryWindowConfig, evaluate_entry_window, load_entry_window_config

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


def _attach_hedge(
    payload: dict[str, Any],
    *,
    seconds_left: float,
    up_ask: Optional[float],
    down_ask: Optional[float],
    hedge_cfg: HedgeConfig,
    apply_hedge: bool,
    main_side: Optional[str] = None,
) -> dict[str, Any]:
    if not apply_hedge:
        return payload
    hedge = evaluate_skew_hedge(
        seconds_left=seconds_left,
        up_ask=up_ask,
        down_ask=down_ask,
        cfg=hedge_cfg,
        main_side=main_side,
    )
    payload["hedge"] = hedge
    if hedge.get("hedge_triggered"):
        payload["hedge_action"] = hedge.get("dry_run_action")
    return payload


def evaluate_entry_signal(
    threshold: float,
    min_entry_seconds_left: int | None = None,
    entry_window: EntryWindowConfig | None = None,
    apply_entry_window: bool = True,
    profile: str = "conservative",
    hedge_config: HedgeConfig | None = None,
    apply_hedge: bool = True,
) -> dict[str, Any]:
    window_cfg = entry_window or load_entry_window_config(profile=profile)
    hedge_cfg = hedge_config or load_hedge_config(profile=profile)
    if min_entry_seconds_left is not None:
        window_cfg = EntryWindowConfig(
            target_sec=window_cfg.target_sec,
            tolerance_sec=window_cfg.tolerance_sec,
            min_entry_seconds_left=min_entry_seconds_left,
        )

    market = resolve_active_current_5m_market()
    if not market:
        return {"status": "no_market", "ts": dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")}

    gamma_up, gamma_dn, up_token, dn_token, slug, end_iso = market_side_prices(market)
    sec_left = float(market.get("_seconds_left") or 0)

    if sec_left < window_cfg.min_entry_seconds_left:
        return _attach_hedge(
            {
                "status": "skip_too_late_to_enter",
                "slug": slug,
                "seconds_left": sec_left,
                "min_entry_seconds_left": window_cfg.min_entry_seconds_left,
                "gamma_up": gamma_up,
                "gamma_down": gamma_dn,
                "entry_window": window_cfg.as_dict(),
                "ts": dt.datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
            seconds_left=sec_left,
            up_ask=None,
            down_ask=None,
            hedge_cfg=hedge_cfg,
            apply_hedge=apply_hedge,
        )

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
        "entry_window": window_cfg.as_dict(),
        "ts": dt.datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    if not candidates:
        payload["status"] = "skip_price_below_threshold"
        return _attach_hedge(
            payload,
            seconds_left=sec_left,
            up_ask=up_ask,
            down_ask=dn_ask,
            hedge_cfg=hedge_cfg,
            apply_hedge=apply_hedge,
        )

    side, trigger_price = sorted(candidates, key=lambda item: item[1], reverse=True)[0]
    payload["side"] = side
    payload["trigger_price"] = trigger_price

    if apply_entry_window:
        allowed, timing_status, timing_meta = evaluate_entry_window(sec_left, window_cfg)
        if not allowed:
            payload["status"] = timing_status
            payload["window_reason"] = timing_meta.get("reason")
            payload["dry_run_action"] = "would_open_if_in_window"
            return _attach_hedge(
                payload,
                seconds_left=sec_left,
                up_ask=up_ask,
                down_ask=dn_ask,
                hedge_cfg=hedge_cfg,
                apply_hedge=apply_hedge,
                main_side=side,
            )

    payload["status"] = "signal_ready"
    payload["dry_run_action"] = "would_open"
    return _attach_hedge(
        payload,
        seconds_left=sec_left,
        up_ask=up_ask,
        down_ask=dn_ask,
        hedge_cfg=hedge_cfg,
        apply_hedge=apply_hedge,
        main_side=side,
    )