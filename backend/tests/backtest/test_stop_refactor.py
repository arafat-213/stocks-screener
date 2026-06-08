import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig, simulate_trades


def test_falling_knife_entry_skipped():
    """
    Verify that if the entry day low hits the stop price, the trade is skipped.
    """
    n = 300
    df = pd.DataFrame(
        {
            "Open": 100.0,
            "High": 105.0,
            "Low": 100.0,
            "Close": 100.0,
            "Volume": 2_000_000.0,
        },
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )

    signal_idx = 250
    entry_idx = signal_idx + 1

    # Setup entry bar to hit stop
    df.iloc[entry_idx, df.columns.get_loc("Open")] = 100.0
    df.iloc[entry_idx, df.columns.get_loc("Low")] = 94.0
    df.iloc[entry_idx, df.columns.get_loc("Close")] = 98.0

    config = BacktestConfig(
        score_threshold=10.0,
        stop_loss_pct=5.0,  # Hard stop = 95
        use_pullback_entry=False,
        use_regime_filter=False,
        require_consolidation=False,
        initial_stop_atr_multiplier=2.0,
    )

    signal = {
        "date": df.index[signal_idx],
        "score": 80.0,
        "above_200ema": True,
        "rsi": 55.0,
        "adx": 25.0,
        "ema_signal": "bullish_cross",
        "atr": 1.0,  # atr_stop = 100 - 2*1.0 = 98
        "close": 100.0,
    }

    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert trades == [], (
        f"Expected entry to be skipped due to falling knife, but got {len(trades)} trades"
    )


def test_zombie_stop_anchoring():
    """
    Verify that the stop_price is anchored to the entry_price (110)
    rather than the signal_close (100).
    """
    n = 300
    df = pd.DataFrame(
        {
            "Open": 100.0,
            "High": 105.0,
            "Low": 95.0,
            "Close": 100.0,
            "Volume": 2_000_000.0,
        },
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )

    signal_idx = 100
    entry_idx = signal_idx + 1
    exit_idx = entry_idx + 1

    # Signal close is 100
    df.iloc[signal_idx, df.columns.get_loc("Close")] = 100.0

    # Gap up entry at 110
    df.iloc[entry_idx, df.columns.get_loc("Open")] = 110.0
    df.iloc[entry_idx, df.columns.get_loc("High")] = 115.0
    df.iloc[entry_idx, df.columns.get_loc("Low")] = 108.0
    df.iloc[entry_idx, df.columns.get_loc("Close")] = 112.0

    # Exit day hits stop
    # Hard stop 7% of 110 = 102.3
    # If it was 7% of 100, it would be 93.
    # We set Low to 100 on exit day.
    df.iloc[exit_idx, df.columns.get_loc("Open")] = 112.0
    df.iloc[exit_idx, df.columns.get_loc("High")] = 113.0
    df.iloc[exit_idx, df.columns.get_loc("Low")] = 100.0  # Hits 102.3
    df.iloc[exit_idx, df.columns.get_loc("Close")] = 101.0

    config = BacktestConfig(
        score_threshold=10.0,
        stop_loss_pct=7.0,  # 7% hard stop
        use_pullback_entry=False,
        use_regime_filter=False,
        require_consolidation=False,
        use_atr_trailing_stop=False,  # Disable trailing stop
        initial_stop_atr_multiplier=10.0,  # Make vol stop very deep so hard stop wins
    )

    signal = {
        "date": df.index[signal_idx],
        "score": 80.0,
        "above_200ema": True,
        "rsi": 55.0,
        "adx": 25.0,
        "ema_signal": "bullish_cross",
        "atr": 1.0,  # vol_stop = 110 - 10*1.0 = 100
        "close": 100.0,
    }

    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 1
    trade = trades[0]

    # entry_price should be 110.0
    assert trade.entry_price == 110.0

    # stop_price should be 110 * 0.93 = 102.3
    # The exit_price in TradeResult is set to stop_price when stopped out
    assert trade.exit_price == pytest.approx(102.3)
    assert trade.return_pct == pytest.approx(-7.0)
    assert trade.exit_reason == "stop_loss"
