import pandas as pd

from app.backtest.engine import simulate_trades
from app.core.trading_config import UnifiedTradingConfig


def test_pullback_fallback_disabled():
    df = pd.DataFrame(
        {
            "Open": [100] * 20,
            "High": [105] * 20,
            "Low": [95] * 20,
            "Close": [100] * 20,
            "Volume": [1000] * 20,
        },
        index=pd.date_range("2020-01-01", periods=20),
    )

    scored_dates = [
        {
            "date": df.index[0],
            "score": 100,
            "ema_signal": "bullish_cross",
            "signal_ema21": 90,  # close enough to not hit EMA21 but within 8%
            "is_consolidating": True,
            "volume_breakout": False,
        }
    ]

    config = UnifiedTradingConfig(
        use_pullback_entry=True, pullback_max_wait_bars=5, use_pullback_fallback=False
    )

    trades = simulate_trades("TEST", "Tech", df, scored_dates, config)
    assert len(trades) == 0, "Trade should not happen when fallback is disabled"

    config.use_pullback_fallback = True
    trades = simulate_trades("TEST", "Tech", df, scored_dates, config)
    assert len(trades) == 1, "Trade should happen when fallback is enabled"
