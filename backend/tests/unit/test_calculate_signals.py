import numpy as np
import pandas as pd

from app.core.strategy import TechnicalStrategy
from app.core.trading_config import UnifiedTradingConfig


def test_calculate_signals_matches_evaluate():
    # Create 300 days of data with some variance to trigger signals
    n = 300
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    df = pd.DataFrame(
        {
            "Close": close,
            "High": close + 2,
            "Low": close - 2,
            "Open": close - 0.5,
            "Volume": np.random.randint(1000, 5000, n),
        },
        index=pd.date_range("2020-01-01", periods=n),
    )

    config = UnifiedTradingConfig()
    strategy = TechnicalStrategy(config)

    # Calculate indicators and signals
    df_signals = strategy.calculate_signals(df.copy())

    # Check a few indices to see if they match evaluate()
    # Skip the first 60 bars as evaluate has a min_bars check
    for i in range(60, n):
        result = strategy.evaluate(df_signals, i=i, skip_ta=True)

        # Check IS_BULLISH
        assert df_signals["IS_BULLISH"].iloc[i] == result["is_bullish"], (
            f"IS_BULLISH mismatch at index {i}"
        )

        # Check IS_OVEREXTENDED
        assert df_signals["IS_OVEREXTENDED"].iloc[i] == result["is_overextended"], (
            f"IS_OVEREXTENDED mismatch at index {i}"
        )

        # Check intermediate signals
        # SIGNAL_EMA_CROSS in calculate_signals vs fresh_ema_cross in evaluate
        # We can't directly check intermediate variables in evaluate,
        # but we can check if they lead to same is_bullish.


def test_calculate_signals_no_ta_precomputed():
    n = 100
    df = pd.DataFrame(
        {
            "Close": np.linspace(100, 200, n),
            "High": np.linspace(105, 205, n),
            "Low": np.linspace(95, 195, n),
            "Open": np.linspace(98, 198, n),
            "Volume": np.linspace(1000, 2000, n),
        },
        index=pd.date_range("2020-01-01", periods=n),
    )

    strategy = TechnicalStrategy()
    # This should call calculate_indicators internally
    df_signals = strategy.calculate_signals(df)

    assert "EMA_5" in df_signals.columns
    assert "IS_BULLISH" in df_signals.columns
    assert "IS_OVEREXTENDED" in df_signals.columns
