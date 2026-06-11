import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig, simulate_trades


def test_stop_loss_selection_logic():
    """Verify that engine selects the tighter of struct_stop and atr_stop, and respects hard cap."""
    # 1. Setup data: price goes up significantly, then drops.
    n = 300
    dates = pd.date_range("2020-01-01", periods=n, freq="B")

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
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
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
    # Data:
    # Bars 0-250: Price 100
    # Bars 251-260: Price 150
    # Bars 261-300: Price 160

    n = 300
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    prices = np.concatenate(
        [np.full(250, 100.0), np.full(10, 150.0), np.full(40, 160.0)]
    )
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

    # Signal at 260. consol_bars=5.
    # pre-signal (255-260) Low min is 150 * 0.99 = 148.5.
    # Entry at 261 (immediately because condition is met).
    # Wait, if entry is 261, pre-entry (256-261) Low min is 150 * 0.99 = 148.5.
    # Still the same.

    # Let's make it wait.
    # EMA21 = 158. Price at 261-265 is 160. Low = 158.4.
    # 158.4 <= 158 * 1.02 = 161.16. Correct.

    # I want pre-entry to be higher.
    # Pre-signal (255-260) Low = 148.5.
    # If entry is at 266.
    # Pre-entry (261-266) Low = 160 * 0.99 = 158.4.
    # consol_low = max(148.5, 158.4) = 158.4.
    # struct_stop = 158.4 * 0.98 = 155.232.

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
        "is_consolidating": True,
        "signal_ema21": 158.0,  # to trigger pullback entry
        "consolidation_bars": 5,
    }

    config = BacktestConfig(
        use_pullback_entry=True,
        pullback_tolerance_pct=2.0,
        pullback_max_wait_bars=10,
        stop_loss_pct=20.0,
        initial_stop_atr_multiplier=10.0,  # 160 - 10 = 150
        holding_days=10,
        require_trend_alignment=False,
        require_consolidation=False,
        min_market_breadth_pct=0.0,
        use_regime_position_scaling=False,
    )

    # Force exit via SL on next day after entry
    # Entry will happen at 261 in this setup actually, because conditions are met immediately.
    # Let's check: at 261, Low=158.4, EMA21=158. 158.4 <= 158*1.02=161.16. Yes.
    # At 261, pre-entry (256-261) Low is STILL 148.5.

    # To force it to wait, I'll make the price jump LATER.
    # Prices: 150 (251-265), 160 (266-300)
    prices[251:266] = 150.0
    prices[266:300] = 160.0
    df["Open"] = prices
    df["High"] = prices * 1.01
    df["Low"] = prices * 0.99
    df["Close"] = prices

    # Signal at 260. pre-signal (255-260) Low = 148.5.
    # At 261-265, Low=148.5. EMA21=158. Close=150.
    # 150 < 158 * 0.995 = 157.21. Pullback condition NOT met (close too low).
    # At 266, Price=160, Low=158.4, Close=160.
    # 158.4 <= 158 * 1.02 = 161.16.
    # 160 >= 158 * 0.995 = 157.21.
    # ENTRY at 266!
    # Pre-entry (261-266) Low min is 148.5 (at 261-265) and 158.4 (at 266).
    # Wait, 261-266 includes 261, 262, 263, 264, 265. All have low 148.5.
    # Still the same!

    # I need the 5 bars BEFORE 266 to be 160.
    # So 261-265 must be 160.
    prices[261:300] = 160.0
    df["Open"] = prices
    df["High"] = prices * 1.01
    df["Low"] = prices * 0.99
    df["Close"] = prices

    # Now at 261: Price=160, Low=158.4, Close=160.
    # Pullback condition met immediately at 261.
    # Pre-entry (256-261) still has 256-260 (Price 150, Low 148.5).

    # I'll just use a very long wait or manual data.
    # Let's just use the fallback entry.
    # If it doesn't meet pullback, it enters at signal_idx + pullback_max_wait_bars.
    # signal_idx = 260. max_wait = 10. Entry at 270.
    # 261-270 prices = 160.
    # Pre-entry (265-270) Low = 158.4.
    # Pre-signal (255-260) Low = 148.5.

    signal["signal_ema21"] = 100.0  # EMA far below price, pullback won't trigger
    config.use_pullback_fallback = True

    # Force SL
    df.iloc[271, df.columns.get_loc("Low")] = 50.0

    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.entry_date == df.index[270]
    assert trade.exit_price == pytest.approx(155.232, abs=1e-3)


if __name__ == "__main__":
    pytest.main([__file__])
