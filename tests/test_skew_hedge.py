from src.risk.skew_hedge import HedgeConfig, compute_hedge_notional_usd, evaluate_skew_hedge


def test_hedge_not_triggered_when_skew_below_threshold():
    cfg = HedgeConfig(trigger_side_price_gte=0.95, trigger_seconds_left_lte=45)
    out = evaluate_skew_hedge(
        seconds_left=40,
        up_ask=0.12,
        down_ask=0.89,
        cfg=cfg,
        main_side="DOWN",
    )
    assert out["hedge_triggered"] is False
    assert out["reason"] == "skew_below_threshold"


def test_hedge_not_triggered_when_too_early():
    cfg = HedgeConfig(trigger_side_price_gte=0.95, trigger_seconds_left_lte=45)
    out = evaluate_skew_hedge(
        seconds_left=90,
        up_ask=0.03,
        down_ask=0.97,
        cfg=cfg,
        main_side="DOWN",
    )
    assert out["hedge_triggered"] is False
    assert out["reason"] == "too_early_for_hedge"


def test_conservative_hedge_triggers_near_close():
    cfg = HedgeConfig(
        trigger_side_price_gte=0.95,
        trigger_seconds_left_lte=45,
        hedge_share_of_main_pct=3,
        hedge_notional_usd_min=1,
        hedge_notional_usd_max=2,
        main_stake_usd=5,
    )
    out = evaluate_skew_hedge(
        seconds_left=40,
        up_ask=0.04,
        down_ask=0.96,
        cfg=cfg,
        main_side="DOWN",
    )
    assert out["hedge_triggered"] is True
    assert out["status"] == "hedge_ready"
    assert out["hedge_side"] == "UP"
    assert out["hedge_notional_usd"] == 1.0
    assert out["dry_run_action"] == "would_hedge"


def test_aggressive_hedge_uses_lower_skew_threshold():
    cfg = HedgeConfig(
        trigger_side_price_gte=0.93,
        trigger_seconds_left_lte=50,
        hedge_share_of_main_pct=5,
        hedge_notional_usd_min=1,
        hedge_notional_usd_max=3,
        main_stake_usd=5,
    )
    out = evaluate_skew_hedge(
        seconds_left=48,
        up_ask=0.06,
        down_ask=0.94,
        cfg=cfg,
        main_side="DOWN",
    )
    assert out["hedge_triggered"] is True
    assert out["hedge_side"] == "UP"
    assert out["hedge_notional_usd"] == 1.0


def test_compute_hedge_notional_clamped_to_max():
    cfg = HedgeConfig(
        hedge_share_of_main_pct=50,
        hedge_notional_usd_min=1,
        hedge_notional_usd_max=2,
        main_stake_usd=10,
    )
    assert compute_hedge_notional_usd(cfg) == 2.0