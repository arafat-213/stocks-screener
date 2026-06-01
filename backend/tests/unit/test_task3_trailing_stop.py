import numpy as np
import pandas as pd

from app.backtest.engine import BacktestConfig, simulate_trades


def create_trending_df(n=100):
    dates = pd.date_range(start="2020-01-01", periods=n)
    # Price goes from 100 to 150 then back to 120
    close = (
        np.linspace(100, 150, n // 2).tolist()
        + np.linspace(150, 120, n - n // 2).tolist()
    )
    df = pd.DataFrame(
        {
            "Open": close,
            "High": [c * 1.01 for c in close],
            "Low": [c * 0.99 for c in close],
            "Close": close,
            "Volume": [1000] * n,
        },
        index=dates,
    )
    return df


def test_trailing_stop_triggered():
    df = create_trending_df(100)
    # Signal at day 10
    signal_date = df.index[10]
    scored_dates = [
        {
            "date": signal_date,
            "score": 100.0,
            "rsi": 50.0,
            "adx": 25.0,
            "ema_signal": "bullish_cross",
            "volume_breakout": True,
            "above_200ema": True,
            "is_consolidating": True,
        }
    ]

    # Entry at day 11 Open. Price around 104.
    # Peak will be at day 50. Price 150.
    # Trailing stop of 10% from 150 = 135.
    # Price hits 135 on the way down after day 50.

    config = BacktestConfig(
        score_threshold=80.0,
        holding_days=80,
        trailing_stop_pct=10.0,
        use_atr_trailing_stop=False,
        stop_loss_pct=0,
        target_pct=0,
        risk_reward_ratio=100.0,
        require_consolidation=False,
        use_pullback_entry=False,
    )

    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason in ["trailing_stop", "atr_trailing_stop"]
    # Peak was 150 * 1.01 (High) = 151.5
    # TS = 151.5 * 0.9 = 136.35
    # Let's check if exit price is reasonable
    assert trade.exit_price < 151.5
    assert trade.exit_date > df.index[50].date()


def test_regime_filter_blocks_trade():
    df = create_trending_df(100)
    signal_date = df.index[10]
    scored_dates = [
        {
            "date": signal_date,
            "score": 100.0,
            "rsi": 50.0,
            "adx": 25.0,
            "ema_signal": "bullish_cross",
            "volume_breakout": True,
            "above_200ema": True,
            "is_consolidating": True,
        }
    ]

    # Regime says FALSE for entry date (T+1)
    entry_date = df.index[11].date()
    regime_dict = {entry_date: False}

    config = BacktestConfig(
        use_regime_filter=True,
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades(
        "TEST.NS", "Tech", df, scored_dates, config, regime_dict=regime_dict
    )

    assert len(trades) == 0


def test_regime_filter_allows_trade():
    df = create_trending_df(100)
    signal_date = df.index[10]
    scored_dates = [
        {
            "date": signal_date,
            "score": 100.0,
            "rsi": 50.0,
            "adx": 25.0,
            "ema_signal": "bullish_cross",
            "volume_breakout": True,
            "above_200ema": True,
            "is_consolidating": True,
        }
    ]

    # Regime says TRUE for entry date (T+1)
    entry_date = df.index[11].date()
    regime_dict = {entry_date: True}

    config = BacktestConfig(
        use_regime_filter=True,
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades(
        "TEST.NS", "Tech", df, scored_dates, config, regime_dict=regime_dict
    )

    assert len(trades) == 1


def test_volume_breakout_filter():
    df = create_trending_df(100)
    signal_date = df.index[10]

    # Signal WITHOUT volume breakout
    scored_dates = [
        {
            "date": signal_date,
            "score": 100.0,
            "rsi": 50.0,
            "adx": 25.0,
            "ema_signal": "bullish_cross",
            "volume_breakout": False,
            "above_200ema": True,
            "is_consolidating": True,
        }
    ]

    config = BacktestConfig(
        require_volume_breakout=True,
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)
    assert len(trades) == 0

    # Signal WITH volume breakout
    scored_dates[0]["volume_breakout"] = True
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)
    assert len(trades) == 1
