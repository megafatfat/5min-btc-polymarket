from src.backtest.engine import BacktestConfig, simulate_round
from src.backtest.historical_data import MarketRound, PricePoint


def test_simulate_round_win_down():
    rnd = MarketRound(
        slug="btc-updown-5m-test",
        bucket=1,
        end_ts=1000,
        question="test",
        outcomes=["Up", "Down"],
        token_ids=["u", "d"],
        winner="DOWN",
        price_points=[
            PricePoint(ts=860, seconds_left=140, up_price=0.2, down_price=0.75),
            PricePoint(ts=920, seconds_left=80, up_price=0.1, down_price=0.9),
        ],
    )
    trade = simulate_round(rnd, BacktestConfig(stake_usd=5.0, threshold=0.70))
    assert trade.status == "win"
    assert trade.side == "DOWN"
    assert trade.pnl_usd > 0


def test_simulate_round_no_trade_when_outside_window():
    rnd = MarketRound(
        slug="btc-updown-5m-test",
        bucket=1,
        end_ts=1000,
        question="test",
        outcomes=["Up", "Down"],
        token_ids=["u", "d"],
        winner="DOWN",
        price_points=[
            PricePoint(ts=860, seconds_left=200, up_price=0.2, down_price=0.8),
        ],
    )
    trade = simulate_round(rnd, BacktestConfig())
    assert trade.status == "no_trade"