"""Fetch closed BTC 5m markets and minute-level price history."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import requests

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


@dataclass(frozen=True)
class PricePoint:
    ts: int
    seconds_left: float
    up_price: float
    down_price: float


@dataclass
class MarketRound:
    slug: str
    bucket: int
    end_ts: int
    question: str
    outcomes: list[str]
    token_ids: list[str]
    winner: Optional[str]
    price_points: list[PricePoint]


def bucket_5m(ts: int) -> int:
    return ts - (ts % 300)


def _parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def fetch_event(slug: str) -> Optional[dict[str, Any]]:
    r = requests.get(f"{GAMMA_BASE}/events", params={"slug": slug}, timeout=15)
    r.raise_for_status()
    arr = r.json()
    return arr[0] if arr else None


def winner_from_market(market: dict[str, Any], outcomes: list[str]) -> Optional[str]:
    prices = _parse_json_field(market.get("outcomePrices")) or []
    if not prices or not outcomes:
        return None
    pairs = list(zip(outcomes, [float(x) for x in prices]))
    winners = [name for name, px in pairs if px >= 0.99]
    if len(winners) == 1:
        return str(winners[0]).upper().replace("YES", "UP").replace("NO", "DOWN")
    up_i, down_i = 0, 1
    labels = [str(x).lower() for x in outcomes[:2]]
    if len(labels) >= 2 and ("up" in labels[1] or "yes" in labels[1]):
        up_i, down_i = 1, 0
    up_px = float(prices[up_i])
    dn_px = float(prices[down_i])
    if up_px > dn_px:
        return "UP"
    if dn_px > up_px:
        return "DOWN"
    return None


def fetch_price_history(token_id: str, start_ts: int, end_ts: int) -> list[dict[str, Any]]:
    r = requests.get(
        f"{CLOB_BASE}/prices-history",
        params={
            "market": token_id,
            "interval": "1h",
            "fidelity": 1,
        },
        timeout=15,
    )
    r.raise_for_status()
    history = r.json().get("history") or []
    return [p for p in history if start_ts <= int(p["t"]) <= end_ts]


def build_price_points(
    *,
    end_ts: int,
    up_token: str,
    down_token: str,
    start_ts: int,
) -> list[PricePoint]:
    up_hist = {int(p["t"]): float(p["p"]) for p in fetch_price_history(up_token, start_ts, end_ts)}
    dn_hist = {int(p["t"]): float(p["p"]) for p in fetch_price_history(down_token, start_ts, end_ts)}
    all_ts = sorted(set(up_hist) | set(dn_hist))
    points: list[PricePoint] = []
    last_up = None
    last_dn = None
    for ts in all_ts:
        if ts in up_hist:
            last_up = up_hist[ts]
        if ts in dn_hist:
            last_dn = dn_hist[ts]
        if last_up is None or last_dn is None:
            continue
        points.append(
            PricePoint(
                ts=ts,
                seconds_left=float(end_ts - ts),
                up_price=last_up,
                down_price=last_dn,
            )
        )
    return points


def load_market_round(slug: str) -> Optional[MarketRound]:
    event = fetch_event(slug)
    if not event:
        return None
    markets = event.get("markets") or []
    if not markets:
        return None
    market = markets[0]
    outcomes = [str(x) for x in (_parse_json_field(market.get("outcomes")) or [])[:2]]
    token_ids = [str(x) for x in (_parse_json_field(market.get("clobTokenIds")) or [])[:2]]
    if len(outcomes) < 2 or len(token_ids) < 2:
        return None

    up_i, down_i = 0, 1
    labels = [str(x).lower() for x in outcomes]
    if len(labels) >= 2 and ("up" in labels[1] or "yes" in labels[1]):
        up_i, down_i = 1, 0

    end_iso = str(market.get("endDate") or market.get("endDateIso") or "")
    end_ts = int(datetime.fromisoformat(end_iso.replace("Z", "+00:00")).timestamp())
    start_ts = end_ts - 300
    bucket = int(slug.rsplit("-", 1)[-1])

    if market.get("closed") is not True:
        return None

    return MarketRound(
        slug=slug,
        bucket=bucket,
        end_ts=end_ts,
        question=str(market.get("question") or ""),
        outcomes=outcomes,
        token_ids=token_ids,
        winner=winner_from_market(market, outcomes),
        price_points=build_price_points(
            end_ts=end_ts,
            up_token=token_ids[up_i],
            down_token=token_ids[down_i],
            start_ts=start_ts,
        ),
    )


def list_recent_slugs(hours: float = 4.0) -> list[str]:
    now = int(time.time())
    start = now - int(hours * 3600)
    slugs: list[str] = []
    b = bucket_5m(start)
    while b <= bucket_5m(now):
        slugs.append(f"btc-updown-5m-{b}")
        b += 300
    return slugs


def load_recent_rounds(hours: float = 4.0, pause_sec: float = 0.05) -> list[MarketRound]:
    rounds: list[MarketRound] = []
    for slug in list_recent_slugs(hours=hours):
        try:
            rnd = load_market_round(slug)
        except Exception:
            rnd = None
        if rnd and rnd.price_points and rnd.winner:
            rounds.append(rnd)
        if pause_sec:
            time.sleep(pause_sec)
    return rounds