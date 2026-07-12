"""Bridge helpers for integrating signal/risk modules into the canonical runner."""

from __future__ import annotations

from typing import Any, Optional

from src.risk.skew_hedge import HedgeConfig, evaluate_skew_hedge, with_main_stake
from src.signal.entry_window import EntryWindowConfig, evaluate_entry_window


def build_entry_window_config(
    profile: str,
    min_entry_seconds_left: Optional[int] = None,
) -> EntryWindowConfig:
    from src.signal.entry_window import load_entry_window_config

    cfg = load_entry_window_config(profile=profile)
    if min_entry_seconds_left is None:
        return cfg
    return EntryWindowConfig(
        target_sec=cfg.target_sec,
        tolerance_sec=cfg.tolerance_sec,
        min_entry_seconds_left=min_entry_seconds_left,
    )


def build_hedge_config(profile: str, stake_usd: float) -> HedgeConfig:
    from src.risk.skew_hedge import load_hedge_config

    return with_main_stake(load_hedge_config(profile=profile), stake_usd)


def entry_window_skip_attempt(
    *,
    slug: str,
    seconds_left: float,
    side: str,
    trigger_price: float,
    up_ask: Optional[float],
    down_ask: Optional[float],
    entry_cfg: EntryWindowConfig,
    apply_entry_window: bool,
) -> Optional[dict[str, Any]]:
    if not apply_entry_window:
        return None

    allowed, status, meta = evaluate_entry_window(seconds_left, entry_cfg)
    if allowed:
        return None

    return {
        "slug": slug,
        "status": status,
        "seconds_left": seconds_left,
        "side": side,
        "trigger_price": trigger_price,
        "clob_up_ask": up_ask,
        "clob_down_ask": down_ask,
        "entry_window": entry_cfg.as_dict(),
        "window_reason": meta.get("reason"),
    }


def evaluate_position_hedge(
    *,
    seconds_left: float,
    up_ask: Optional[float],
    down_ask: Optional[float],
    hedge_cfg: HedgeConfig,
    main_side: str,
    apply_hedge: bool,
) -> dict[str, Any]:
    if not apply_hedge:
        return {"hedge_triggered": False, "status": "hedge_disabled_by_flag"}
    return evaluate_skew_hedge(
        seconds_left=seconds_left,
        up_ask=up_ask,
        down_ask=down_ask,
        cfg=hedge_cfg,
        main_side=main_side,
    )