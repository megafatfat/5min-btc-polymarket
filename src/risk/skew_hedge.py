"""Optional micro-hedge when market skew becomes extreme near close."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "btc_5m_profiles.yaml"
OPPOSITE_SIDE = {"UP": "DOWN", "DOWN": "UP"}


@dataclass(frozen=True)
class HedgeConfig:
    enabled: bool = True
    trigger_side_price_gte: float = 0.95
    trigger_seconds_left_lte: int = 45
    hedge_share_of_main_pct: float = 3.0
    hedge_notional_usd_min: float = 1.0
    hedge_notional_usd_max: float = 2.0
    main_stake_usd: float = 5.0

    def as_dict(self) -> dict[str, float | int | bool]:
        return {
            "enabled": self.enabled,
            "trigger_side_price_gte": self.trigger_side_price_gte,
            "trigger_seconds_left_lte": self.trigger_seconds_left_lte,
            "hedge_share_of_main_pct": self.hedge_share_of_main_pct,
            "hedge_notional_usd_min": self.hedge_notional_usd_min,
            "hedge_notional_usd_max": self.hedge_notional_usd_max,
            "main_stake_usd": self.main_stake_usd,
        }


def with_main_stake(cfg: HedgeConfig, stake_usd: float) -> HedgeConfig:
    return HedgeConfig(
        enabled=cfg.enabled,
        trigger_side_price_gte=cfg.trigger_side_price_gte,
        trigger_seconds_left_lte=cfg.trigger_seconds_left_lte,
        hedge_share_of_main_pct=cfg.hedge_share_of_main_pct,
        hedge_notional_usd_min=cfg.hedge_notional_usd_min,
        hedge_notional_usd_max=cfg.hedge_notional_usd_max,
        main_stake_usd=float(stake_usd),
    )


def load_hedge_config(
    config_path: Optional[Path] = None,
    profile: str = "conservative",
) -> HedgeConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    prof = (raw.get("profiles") or {}).get(profile) or {}
    hedge = prof.get("hedge") or {}
    sizing = prof.get("sizing") or {}

    return HedgeConfig(
        enabled=bool(hedge.get("enabled", True)),
        trigger_side_price_gte=float(hedge.get("trigger_side_price_gte", 0.95)),
        trigger_seconds_left_lte=int(hedge.get("trigger_seconds_left_lte", 45)),
        hedge_share_of_main_pct=float(hedge.get("hedge_share_of_main_pct", 3)),
        hedge_notional_usd_min=float(hedge.get("hedge_notional_usd_min", 1)),
        hedge_notional_usd_max=float(hedge.get("hedge_notional_usd_max", 2)),
        main_stake_usd=float(sizing.get("stake_usd", 5)),
    )


def dominant_side_from_asks(
    up_ask: Optional[float],
    down_ask: Optional[float],
) -> tuple[Optional[str], Optional[float]]:
    if up_ask is None and down_ask is None:
        return None, None
    if up_ask is None:
        return "DOWN", float(down_ask)
    if down_ask is None:
        return "UP", float(up_ask)
    if float(up_ask) >= float(down_ask):
        return "UP", float(up_ask)
    return "DOWN", float(down_ask)


def compute_hedge_notional_usd(cfg: HedgeConfig) -> float:
    pct_notional = cfg.main_stake_usd * (cfg.hedge_share_of_main_pct / 100.0)
    return max(cfg.hedge_notional_usd_min, min(cfg.hedge_notional_usd_max, pct_notional))


def evaluate_skew_hedge(
    *,
    seconds_left: float,
    up_ask: Optional[float],
    down_ask: Optional[float],
    cfg: HedgeConfig,
    main_side: Optional[str] = None,
) -> dict[str, Any]:
    """Evaluate whether a small opposite hedge should be placed."""
    dominant_side, dominant_price = dominant_side_from_asks(up_ask, down_ask)
    result: dict[str, Any] = {
        "enabled": cfg.enabled,
        "config": cfg.as_dict(),
        "dominant_side": dominant_side,
        "dominant_price": dominant_price,
        "main_side": main_side,
        "hedge_triggered": False,
        "status": "hedge_not_triggered",
    }

    if not cfg.enabled:
        result["reason"] = "hedge_disabled"
        return result

    if dominant_side is None or dominant_price is None:
        result["reason"] = "missing_quotes"
        return result

    if dominant_price < cfg.trigger_side_price_gte:
        result["reason"] = "skew_below_threshold"
        return result

    if seconds_left > cfg.trigger_seconds_left_lte:
        result["reason"] = "too_early_for_hedge"
        return result

    hedge_side = OPPOSITE_SIDE[dominant_side]
    hedge_notional = compute_hedge_notional_usd(cfg)
    hedge_price = down_ask if hedge_side == "DOWN" else up_ask

    result.update(
        {
            "hedge_triggered": True,
            "status": "hedge_ready",
            "hedge_side": hedge_side,
            "hedge_notional_usd": round(hedge_notional, 4),
            "hedge_price": hedge_price,
            "dry_run_action": "would_hedge",
            "reason": "extreme_skew_near_close",
        }
    )
    return result