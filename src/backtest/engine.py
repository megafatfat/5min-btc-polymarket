"""Simple historical backtest for BTC 5m momentum strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.backtest.historical_data import MarketRound, PricePoint
from src.execution.enhanced_runner import build_entry_window_config, build_hedge_config
from src.signal.entry_window import evaluate_entry_window


@dataclass
class BacktestConfig:
    profile: str = "conservative"
    threshold: float = 0.70
    stake_usd: float = 5.0
    stop_loss_pct: float = 0.25
    apply_entry_window: bool = True


@dataclass
class TradeResult:
    slug: str
    status: str
    side: Optional[str] = None
    entry_price: Optional[float] = None
    seconds_left: Optional[float] = None
    winner: Optional[str] = None
    pnl_usd: float = 0.0
    reason: Optional[str] = None


def _pick_side(point: PricePoint, threshold: float) -> Optional[tuple[str, float]]:
    candidates: list[tuple[str, float]] = []
    if point.up_price >= threshold:
        candidates.append(("UP", point.up_price))
    if point.down_price >= threshold:
        candidates.append(("DOWN", point.down_price))
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x[1], reverse=True)[0]


def _side_price(point: PricePoint, side: str) -> float:
    return point.up_price if side == "UP" else point.down_price


def simulate_round(round_: MarketRound, cfg: BacktestConfig) -> TradeResult:
    entry_cfg = build_entry_window_config(cfg.profile)
    entry_point: Optional[PricePoint] = None
    entry_side: Optional[str] = None
    entry_price: Optional[float] = None

    for point in round_.price_points:
        pick = _pick_side(point, cfg.threshold)
        if not pick:
            continue
        side, trigger = pick
        if cfg.apply_entry_window:
            allowed, status, _ = evaluate_entry_window(point.seconds_left, entry_cfg)
            if not allowed:
                continue
        entry_point = point
        entry_side = side
        entry_price = trigger
        break

    if not entry_point or not entry_side or entry_price is None:
        return TradeResult(slug=round_.slug, status="no_trade", winner=round_.winner)

    stop_price = entry_price * (1.0 - cfg.stop_loss_pct)
    stopped = False
    for point in round_.price_points:
        if point.ts <= entry_point.ts:
            continue
        px = _side_price(point, entry_side)
        if px <= stop_price:
            stopped = True
            # Approximate exit at stop price on remaining stake.
            pnl = cfg.stake_usd * (stop_price / entry_price - 1.0)
            return TradeResult(
                slug=round_.slug,
                status="stopped_out",
                side=entry_side,
                entry_price=entry_price,
                seconds_left=entry_point.seconds_left,
                winner=round_.winner,
                pnl_usd=round(pnl, 4),
                reason=f"stop_loss_{int(cfg.stop_loss_pct * 100)}pct",
            )

    won = entry_side == round_.winner
    if won:
        pnl = cfg.stake_usd * (1.0 / entry_price - 1.0)
        status = "win"
    else:
        pnl = -cfg.stake_usd
        status = "loss"

    return TradeResult(
        slug=round_.slug,
        status=status,
        side=entry_side,
        entry_price=entry_price,
        seconds_left=entry_point.seconds_left,
        winner=round_.winner,
        pnl_usd=round(pnl, 4),
        reason="held_to_resolution" if not stopped else "stopped_out",
    )


def run_backtest(rounds: list[MarketRound], cfg: BacktestConfig) -> dict[str, Any]:
    trades = [simulate_round(r, cfg) for r in rounds]
    traded = [t for t in trades if t.status != "no_trade"]
    wins = [t for t in traded if t.status == "win"]
    losses = [t for t in traded if t.status == "loss"]
    stops = [t for t in traded if t.status == "stopped_out"]
    total_pnl = round(sum(t.pnl_usd for t in traded), 4)

    return {
        "config": {
            "profile": cfg.profile,
            "threshold": cfg.threshold,
            "stake_usd": cfg.stake_usd,
            "stop_loss_pct": cfg.stop_loss_pct,
            "apply_entry_window": cfg.apply_entry_window,
            "entry_window": build_entry_window_config(cfg.profile).as_dict(),
        },
        "summary": {
            "rounds_loaded": len(rounds),
            "trades": len(traded),
            "no_trade": len(trades) - len(traded),
            "wins": len(wins),
            "losses": len(losses),
            "stopped_out": len(stops),
            "win_rate": round(len(wins) / len(traded), 4) if traded else 0.0,
            "total_pnl_usd": total_pnl,
            "avg_pnl_usd": round(total_pnl / len(traded), 4) if traded else 0.0,
        },
        "trades": [t.__dict__ for t in trades],
    }