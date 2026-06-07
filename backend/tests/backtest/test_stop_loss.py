
import pandas as pd
import numpy as np
import pytest
from app.backtest.engine import simulate_trades, BacktestConfig

def test_stop_loss_selection_logic():
    """Verify that engine selects the tighter of struct_stop and atr_stop, and respects hard cap."""
    # 1. Setup data: price goes up significantly, then drops.
    n = 300
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    
    # Prices: 100 for first 250 bars, then jump to 150.
    prices = np.concatenate([
        np.full(250, 100.0),
        np.full(50, 150.0)
    ])
    
    df = pd.DataFrame({
        "Open": prices,
        "High": prices * 1.01,
        "Low": prices * 0.99,
        "Close": prices,
        "Volume": 1000000
    }, index=dates)
    
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
        "volume_breakout": True
    }
    
    config = BacktestConfig(
        stop_loss_pct=7.0, # 150 * 0.93 = 139.5
        use_pullback_entry=False,
        use_regime_filter=False,
        require_consolidation=False,
        holding_days=10
    )
    
    # Trigger SL on next day
    df.iloc[signal_idx + 1, df.columns.get_loc("Low")] = 80.0
    df.iloc[signal_idx + 1, df.columns.get_loc("Close")] = 80.0
    
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
    df = pd.DataFrame({
        "Open": prices, "High": prices*1.01, "Low": prices*0.99, "Close": prices, "Volume": 1000000
    }, index=dates)
    
    signal_idx = 260
    signal = {
        "date": df.index[signal_idx],
        "score": 80.0, "above_200ema": True, "rsi": 55.0, "adx": 30.0,
        "atr": 10.0, # atr_stop = 100 - 2*10 = 80.0 (20% loss)
        "ema_signal": "bullish", "volume_signal": "bullish", "rsi_signal": "bullish", "volume_breakout": True
    }
    
    # Make struct_stop wider: 80.0 * 0.98 = 78.4
    df.iloc[255:260, df.columns.get_loc("Low")] = 80.0
    
    config = BacktestConfig(
        stop_loss_pct=7.0, # hard_stop = 93.0
        use_pullback_entry=False, use_regime_filter=False, holding_days=10,
        require_consolidation=False
    )
    
    # Trigger SL
    df.iloc[signal_idx + 1, df.columns.get_loc("Low")] = 50.0
    
    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 1
    # Should pick 93.0 (hard_stop) as it is tighter than both dynamic stops
    assert trades[0].exit_price == 93.0
    assert trades[0].return_pct == pytest.approx(-7.0, abs=1e-5)

if __name__ == "__main__":
    pytest.main([__file__])
