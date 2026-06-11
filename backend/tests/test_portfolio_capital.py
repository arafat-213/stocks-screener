import datetime

import pandas as pd

from app.backtest.engine import simulate_portfolio
from app.core.strategy import TechnicalStrategy
from app.core.trading_config import UnifiedTradingConfig as BacktestConfig


def test_portfolio_hard_capital_cap():
    # Setup config: ₹10L capital, 20% pos size (₹2L), no concurrent limit
    config = BacktestConfig(
        starting_capital=1000000.0,
        position_size=200000.0,  # 20%
        use_volatility_sizing=False,
        max_concurrent_positions=0,
        max_sector_positions=0,
        use_regime_position_scaling=False,
    )

    # Create 10 symbols that all have a signal on the same day
    signal_date = datetime.date(2023, 1, 2)
    dates = pd.date_range(start="2023-01-01", end="2023-01-10", freq="D")

    all_dfs = {}
    all_signals = {}
    stocks_info = {}

    for i in range(10):
        sym = f"STOCK_{i}.NS"
        df = pd.DataFrame(
            {
                "Open": [100.0] * len(dates),
                "High": [105.0] * len(dates),
                "Low": [95.0] * len(dates),
                "Close": [102.0] * len(dates),
                "Volume": [1000] * len(dates),
                "EMA_200": [90.0] * len(dates),
                "MOMENTUM_12M": [10.0] * len(dates),
                "RSI_14": [50.0] * len(dates),
                "ADX_14": [30.0] * len(dates),
            },
            index=dates,
        )
        all_dfs[sym] = df
        stocks_info[sym] = "TestSector"
        all_signals[sym] = [
            {
                "date": pd.Timestamp(signal_date),
                "score": 80.0,
                "is_bullish": True,
                "rsi": 50.0,
                "adx": 30.0,
                "ema_signal": "bullish",
                "volume_breakout": True,
                "above_200ema": True,
                "is_consolidating": True,
                "atr": 5.0,
                "ema21_level": 98.0,
                "momentum_12m": 10.0,
                "momentum_3m": 5.0,
            }
        ]

    # Run simulation
    trades = simulate_portfolio(
        all_signals,
        all_dfs,
        stocks_info,
        config,
        strategy=TechnicalStrategy(config),
        regime_scaling_map={signal_date: 1},
    )

    # Should only take 5 trades (5 * 20% = 100%)
    assert len(trades) == 5

    # Verify that at no point utilization exceeds starting_capital
    all_dates = pd.date_range(dates.min(), dates.max())
    for d in all_dates:
        active_trades = [t for t in trades if t.entry_date <= d.date() <= t.exit_date]
        util = sum(t.position_size_used for t in active_trades)
        assert util <= config.starting_capital + 0.01  # Allow for small float epsilon
