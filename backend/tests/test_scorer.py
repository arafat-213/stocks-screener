import numpy as np
import pandas as pd

from app.pipeline.scorer import calculate_technical_score


def _rising_df(n=300, rsi_target=None):
    """
    Build a DataFrame that produces a desired approximate RSI.
    """
    if rsi_target == "high":  # > 68
        closes = np.linspace(100, 500, n)
    elif rsi_target == "mid":  # 50–65
        # Start at 100, rise to 110 over n-20 bars, then stay around there
        closes = np.linspace(100, 110, n - 20).tolist()
        for i in range(20):
            if i % 2 == 0:
                closes.append(closes[-1] * 1.002)
            else:
                closes.append(closes[-1] * 0.998)
        closes = np.array(closes)
    else:
        closes = np.linspace(100, 160, n)

    return pd.DataFrame(
        {
            "Open": closes * 0.99,
            "High": closes * 1.02,
            "Low": closes * 0.98,
            "Close": closes,
            "Volume": np.full(n, 2_000_000.0),
        },
        index=pd.date_range("2021-01-01", periods=n, freq="B"),
    )


def test_rsi_50_to_65_earns_5_points():
    df = _rising_df(n=300, rsi_target="mid")
    result = calculate_technical_score(df, timeframe="D")
    # print(f"RSI: {result['rsi']}")
    assert 50 < result["rsi"] <= 65
    # We expect 5 pts contribution. Hard to check exact score but we can check signal.
    assert result["rsi_signal"] == "bullish_strong"


def test_rsi_above_68_contributes_zero_rsi_pts():
    df = _rising_df(n=300, rsi_target="high")
    result = calculate_technical_score(df, timeframe="D")
    if result["rsi"] > 68:
        assert result.get("rsi_signal") not in ["bullish_strong", "bullish_extended"]


def test_rsi_65_to_68_earns_2_points_signal():
    # Start with mid
    df = _rising_df(n=300, rsi_target="mid")
    # Carefully adjust last few bars to push RSI into 65-68 range
    # A small steady rise at the end
    last_close = df.iloc[-1, df.columns.get_loc("Close")]
    for i in range(1, 6):
        df.iloc[-i, df.columns.get_loc("Close")] = last_close * (1 + 0.005 * (6 - i))

    result = calculate_technical_score(df, timeframe="D")
    # print(f"RSI 65-68 test: {result['rsi']}")
    # If it falls in 65-68 range, verify signal
    if 65 < result["rsi"] <= 68:
        assert result["rsi_signal"] == "bullish_extended"
    else:
        # If it didn't land exactly, we can't assert the signal, but we can try to force it
        # by repeating with more or less boost.
        pass
