import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig, simulate_trades


def test_stop_loss_selection_logic():
    """Verify that engine selects the tighter of struct_stop and atr_stop, and respects hard cap."""
    # 1. Setup data: price goes up significantly, then drops.
    n = 300
    dates = pd.date_range("2021-01-01", periods=n, freq="B")

    # Prices: 100 for first 250 bars, then jump to 150.
    prices = np.concatenate([np.full(250, 100.0), np.full(50, 150.0)])

    df = pd.DataFrame(
        {
            "Open": prices,
            "High": prices * 1.01,
            "Low": prices * 0.99,
            "Close": prices,
            "Volume": 1000000,
        },
        index=dates,
    )

    # 2. Setup Signal at index 260.
    signal_idx = 260
    signal_date = df.index[signal_idx]

    # consolidation_bars is 15 by default.
    # consol_low = df.iloc[260-15 : 260]["Low"].min()
    # so consol_low = 100.0 * 0.99 = 99.0.
    # struct_stop = 99.0 * 0.98 = 97.02. (approx 35% risk)

    # atr_stop: entry_price - atr_multiplier * atr
    # atr = 5.0, atr_multiplier = 2.0 -> atr_stop = 150.0 - 10.0 = 140.0. (approx 6.6% risk)

    signal = {
        "date": signal_date,
        "score": 80.0,
        "above_200ema": True,
        "rsi": 55.0,
        "adx": 30.0,
        "atr": 5.0,
        "ema_signal": "bullish",
        "volume_signal": "bullish",
        "rsi_signal": "bullish",
        "volume_breakout": True,
    }

    config = BacktestConfig(
        stop_loss_pct=7.0,  # 150 * 0.93 = 139.5
        use_pullback_entry=False,
        require_consolidation=False,
        holding_days=10,
    )

    # Trigger SL on day after entry
    df.iloc[signal_idx + 2, df.columns.get_loc("Low")] = 80.0
    df.iloc[signal_idx + 2, df.columns.get_loc("Close")] = 80.0

    trades = simulate_trades("TEST", "Tech", df, [signal], config)

    assert len(trades) == 1
    trade = trades[0]

    # Should pick 140.0 (atr_stop) as it is tighter than struct_stop (97.02)
    assert trade.exit_price == 140.0
    assert trade.return_pct == pytest.approx(-6.6666666, abs=1e-5)


def test_hard_cap_stop_loss():
    """Verify that the hard stop_loss_pct cap is enforced when both dynamic stops are too wide."""
    n = 300
    dates = pd.date_range("2021-01-01", periods=n, freq="B")
    prices = np.full(n, 100.0)
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": prices * 1.01,
            "Low": prices * 0.99,
            "Close": prices,
            "Volume": 1000000,
        },
        index=dates,
    )

    signal_idx = 260
    signal = {
        "date": df.index[signal_idx],
        "score": 80.0,
        "above_200ema": True,
        "rsi": 55.0,
        "adx": 30.0,
        "atr": 10.0,  # atr_stop = 100 - 2*10 = 80.0 (20% loss)
        "ema_signal": "bullish",
        "volume_signal": "bullish",
        "rsi_signal": "bullish",
        "volume_breakout": True,
    }

    # Make struct_stop wider: 80.0 * 0.98 = 78.4
    df.iloc[255:260, df.columns.get_loc("Low")] = 80.0

    config = BacktestConfig(
        stop_loss_pct=7.0,  # hard_stop = 93.0
        use_pullback_entry=False,
        holding_days=10,
        require_consolidation=False,
    )

    # Trigger SL
    df.iloc[signal_idx + 2, df.columns.get_loc("Low")] = 50.0

    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 1
    # Should pick 93.0 (hard_stop) as it is tighter than both dynamic stops
    assert trades[0].exit_price == 93.0
    assert trades[0].return_pct == pytest.approx(-7.0, abs=1e-5)


def test_pullback_entry_tighter_stop():
    """Verify that structural stop uses the tighter of signal-relative and entry-relative consolidation."""
    n = 300
    dates = pd.date_range("2021-01-01", periods=n, freq="B")
    prices = np.full(n, 100.0)
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": prices * 1.01,
            "Low": prices * 0.99,
            "Close": prices,
            "Volume": 1000000,
        },
        index=dates,
    )

    # Signal at 260. Entry at 261.
    # consol_bars = 1.
    # pre-signal (259:260). Low = 148.5 (Price 150).
    # pre-entry (260:261). Low = 168.3 (Price 170).

    df.iloc[259, df.columns.get_loc("Open")] = 150.0
    df.iloc[259, df.columns.get_loc("Low")] = 148.5
    df.iloc[259, df.columns.get_loc("Close")] = 150.0

    df.iloc[260, df.columns.get_loc("Open")] = 170.0
    df.iloc[260, df.columns.get_loc("Low")] = 168.3
    df.iloc[260, df.columns.get_loc("Close")] = 170.0

    df.iloc[261, df.columns.get_loc("Open")] = 170.0
    df.iloc[261, df.columns.get_loc("Low")] = 168.3
    df.iloc[261, df.columns.get_loc("Close")] = 170.0

    # Force SL on next day
    df.iloc[262, df.columns.get_loc("Low")] = 50.0

    signal_idx = 260
    signal = {
        "date": df.index[signal_idx],
        "score": 80.0,
        "above_200ema": True,
        "rsi": 55.0,
        "adx": 30.0,
        "atr": 1.0,
        "ema_signal": "bullish",
        "volume_signal": "bullish",
        "rsi_signal": "bullish",
        "volume_breakout": True,
        "consolidation_bars": 1,
    }

    config = BacktestConfig(
        use_pullback_entry=False,
        stop_loss_pct=20.0,
        initial_stop_atr_multiplier=10.0,
        holding_days=10,
        require_consolidation=False,
    )

    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 1
    trade = trades[0]
    # Expected tighter stop: 168.3 * 0.98 = 164.934
    assert trade.exit_price == pytest.approx(164.934, abs=1e-3)


if __name__ == "__main__":
    pytest.main([__file__])
