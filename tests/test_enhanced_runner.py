from src.execution.enhanced_runner import (
    build_entry_window_config,
    build_hedge_config,
    entry_window_skip_attempt,
    evaluate_position_hedge,
)


def test_entry_window_skip_attempt_blocks_early_signal():
    cfg = build_entry_window_config("conservative")
    attempt = entry_window_skip_attempt(
        slug="btc-updown-5m-test",
        seconds_left=271.0,
        side="UP",
        trigger_price=0.73,
        up_ask=0.73,
        down_ask=0.28,
        entry_cfg=cfg,
        apply_entry_window=True,
    )
    assert attempt is not None
    assert attempt["status"] == "skip_too_early_to_enter"


def test_entry_window_skip_attempt_allows_in_window():
    cfg = build_entry_window_config("conservative")
    attempt = entry_window_skip_attempt(
        slug="btc-updown-5m-test",
        seconds_left=116.0,
        side="UP",
        trigger_price=0.71,
        up_ask=0.71,
        down_ask=0.3,
        entry_cfg=cfg,
        apply_entry_window=True,
    )
    assert attempt is None


def test_build_hedge_config_uses_runtime_stake():
    cfg = build_hedge_config("conservative", stake_usd=8.0)
    assert cfg.main_stake_usd == 8.0


def test_evaluate_position_hedge_disabled_flag():
    cfg = build_hedge_config("conservative", stake_usd=5.0)
    out = evaluate_position_hedge(
        seconds_left=40,
        up_ask=0.04,
        down_ask=0.96,
        hedge_cfg=cfg,
        main_side="DOWN",
        apply_hedge=False,
    )
    assert out["status"] == "hedge_disabled_by_flag"