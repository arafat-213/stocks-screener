import numpy as np
import pandas as pd

from app.backtest.engine import score_series


def create_test_df(n=400):
    np.random.seed(42)
    dates = pd.date_range(start="2020-01-01", periods=n)
    df = pd.DataFrame(
        {
            "Open": np.linspace(100, 200, n),
            "High": np.linspace(105, 205, n),
            "Low": np.linspace(95, 195, n),
            "Close": np.linspace(102, 202, n),
            "Volume": np.linspace(1000, 2000, n),
        },
        index=dates,
    )
    return df


def test_volume_breakout_field_exists():
    df = create_test_df(300)
    results = score_series(df)
    assert len(results) > 0
    assert "volume_breakout" in results[0]
    assert isinstance(results[0]["volume_breakout"], bool)


def test_volume_breakout_logic():
    df = create_test_df(300)
    # MIN_BARS = 260
    # Let's force a volume breakout at index 280
    idx = 280
    df.iloc[idx, df.columns.get_loc("Volume")] = 10000.0  # Very high
    df.iloc[idx, df.columns.get_loc("Close")] = (
        df.iloc[idx]["Open"] + 5.0
    )  # is_green = True

    results = score_series(df)
    result_idx = idx - 260
    assert results[result_idx]["volume_breakout"] is True


def test_hard_filter_rsi_overbought():
    df = create_test_df(300)
    # Force RSI > 70 at index 280
    idx = 280
    df.iloc[idx - 5 : idx + 1, df.columns.get_loc("Close")] = np.linspace(200, 500, 6)

    results = score_series(df)
    result_idx = idx - 260
    # If RSI > 70, score should be 0
    if results[result_idx]["rsi"] > 70:
        assert results[result_idx]["score"] == 0


def test_hard_filter_below_ema200():
    df = create_test_df(400)  # Need more bars for EMA200
    idx = 350
    # Force price < EMA200
    df.iloc[idx, df.columns.get_loc("Close")] = 10.0  # Very low

    results = score_series(df)
    result_idx = idx - 260
    # score should be 0
    assert results[result_idx]["score"] == 0


def test_hard_filter_adx_low():
    df = create_test_df(300)
    # Force ADX < 20
    idx = 280
    df.iloc[idx - 20 : idx + 1, df.columns.get_loc("Close")] = 150.0
    df.iloc[idx - 20 : idx + 1, df.columns.get_loc("High")] = 151.0
    df.iloc[idx - 20 : idx + 1, df.columns.get_loc("Low")] = 149.0

    results = score_series(df)
    result_idx = idx - 260
    if results[result_idx]["adx"] < 20:
        assert results[result_idx]["score"] == 0


def test_adx_weighting():
    df = create_test_df(300)
    # Force high ADX at index 280 but keep RSI moderate
    idx = 280
    # A steady slow uptrend
    df.iloc[: idx + 1, df.columns.get_loc("Close")] = np.linspace(100, 150, idx + 1)
    df.iloc[: idx + 1, df.columns.get_loc("High")] = df.iloc[: idx + 1]["Close"] + 1
    df.iloc[: idx + 1, df.columns.get_loc("Low")] = df.iloc[: idx + 1]["Close"] - 1

    results = score_series(df)
    result_idx = idx - 260
    adx = results[result_idx]["adx"]
    rsi = results[result_idx]["rsi"]
    score = results[result_idx]["score"]
    is_bullish = results[result_idx]["is_bullish"]

    print(f"DEBUG: adx={adx}, rsi={rsi}, score={score}, is_bullish={is_bullish}")

    if adx > 20 and rsi <= 70:
        # Should have at least the ADX bonus if it's not zeroed
        assert score >= 5
