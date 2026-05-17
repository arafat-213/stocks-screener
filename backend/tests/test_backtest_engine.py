import pandas as pd
import numpy as np
import datetime
import pytest
from app.backtest.engine import score_series, simulate_trades, BacktestConfig


def _make_ohlcv(n: int) -> pd.DataFrame:
    """Returns a simple uptrending OHLCV DataFrame of length n."""
    np.random.seed(0)
    closes = np.linspace(100, 200, n) + np.random.normal(0, 0.3, n)
    df = pd.DataFrame({
        "Open":   closes * 0.998,
        "High":   closes * 1.01,
        "Low":    closes * 0.99,
        "Close":  closes,
        "Volume": np.full(n, 2_000_000.0),
    }, index=pd.date_range("2020-01-01", periods=n, freq="B"))
    return df


class TestMinBars:
    def test_no_signals_below_210_bars(self):
        """score_series must return an empty list when df has fewer than 210 rows."""
        df = _make_ohlcv(209)
        config = BacktestConfig()
        results = score_series(df, fund_cache=None, config=config)
        assert results == [], (
            f"Expected no signals for a 209-bar DataFrame, got {len(results)}"
        )

    def test_signals_possible_at_210_bars(self):
        """score_series may return signals when df has exactly 210 rows."""
        df = _make_ohlcv(210)
        config = BacktestConfig()
        results = score_series(df, fund_cache=None, config=config)
        # We only assert it doesn't crash and returns a list; signal generation depends on data.
        assert isinstance(results, list)

    def test_no_signals_at_exactly_60_bars(self):
        """Regression: 60 bars (old MIN_BARS) must now produce zero signals."""
        df = _make_ohlcv(60)
        config = BacktestConfig()
        results = score_series(df, fund_cache=None, config=config)
        assert results == [], (
            "60-bar DataFrame should produce no signals after MIN_BARS fix."
        )
