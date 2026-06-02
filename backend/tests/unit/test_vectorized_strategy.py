import numpy as np
import pandas as pd
import pytest

from app.core.strategy import TechnicalStrategy


def test_vectorized_components():
    # Create 300 days of data
    # We use a linear trend to make calculations predictable
    n = 300
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
    df_ind = strategy.calculate_indicators(df)

    # Check 52W High (approx 252 bars)
    # The current implementation in evaluate uses:
    # recent_252 = df["Close"].iloc[i - 251 : i + 1]
    # week52_high = float(recent_252.max())

    expected_high = df["Close"].rolling(window=252, min_periods=1).max()
    pd.testing.assert_series_equal(
        df_ind["WEEK52_HIGH"], expected_high, check_names=False
    )

    expected_low = df["Close"].rolling(window=252, min_periods=1).min()
    pd.testing.assert_series_equal(
        df_ind["WEEK52_LOW"], expected_low, check_names=False
    )

    # Check Resistance: Highest close in the year prior to the last 20 bars
    # Original: df["Close"].iloc[i - 259 : i - 19].max()
    # This means at index i, it looks at [i-259, i-20] inclusive?
    # Let's re-verify: i - 259 : i - 19 in slice notation is i-259 up to (but not including) i-19.
    # So it includes i-20.
    # Vectorized: shift(20) then rolling(240)
    # If shift(20), at index i we have value from i-20.
    # rolling(240) at index i with shift(20) covers [i-20-239, i-20] = [i-259, i-20].
    # This matches.

    expected_resistance = df["Close"].shift(20).rolling(window=240, min_periods=1).max()
    pd.testing.assert_series_equal(
        df_ind["RESISTANCE_LEVEL"], expected_resistance, check_names=False
    )

    # Check Momentum
    # Original: (price / df["Close"].iloc[i - shift] - 1) * 100
    for period, shift_val in [("1M", 21), ("3M", 63), ("6M", 126), ("12M", 252)]:
        expected_mom = (df["Close"] / df["Close"].shift(shift_val) - 1) * 100
        pd.testing.assert_series_equal(
            df_ind[f"MOMENTUM_{period}"], expected_mom, check_names=False
        )


def test_evaluate_uses_vectorized():
    n = 300
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
    # Calculate indicators first (this is what backtest engine does)
    df_ind = strategy.calculate_indicators(df)

    # Evaluate at the last index
    result = strategy.evaluate(df_ind, i=-1, skip_ta=True)

    # Check if results match the last row of df_ind
    assert result["week52_high"] == df_ind["WEEK52_HIGH"].iloc[-1]
    assert result["week52_low"] == df_ind["WEEK52_LOW"].iloc[-1]
    assert result["resistance_level"] == df_ind["RESISTANCE_LEVEL"].iloc[-1]
    assert result["momentum_1m"] == df_ind["MOMENTUM_1M"].iloc[-1]
    assert result["momentum_3m"] == df_ind["MOMENTUM_3M"].iloc[-1]
    assert result["momentum_6m"] == df_ind["MOMENTUM_6M"].iloc[-1]
    assert result["momentum_12m"] == df_ind["MOMENTUM_12M"].iloc[-1]

    # Verify percentages
    price = df_ind["Close"].iloc[-1]
    expected_pct_high = (price / result["week52_high"] - 1) * 100
    assert pytest.approx(result["pct_from_52w_high"]) == expected_pct_high

    expected_pct_res = (price / result["resistance_level"] - 1) * 100
    assert pytest.approx(result["pct_from_resistance"]) == expected_pct_res
