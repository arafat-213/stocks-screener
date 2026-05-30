import pandas as pd

from app.pipeline.scorer import calculate_combined_score, calculate_technical_score


def create_sample_df(rows=100, bullish=True):
    """Helper to create a sample dataframe with technical indicators."""
    dates = pd.date_range(start="2023-01-01", periods=rows)
    close = []
    curr = 100.0
    trend = 0.2 if bullish else -0.2
    for i in range(rows):
        noise = (i % 5 - 2) * 0.5
        curr += trend + noise
        close.append(curr)

    df = pd.DataFrame(
        {
            "Open": [c - 0.5 for c in close],
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": [1000] * rows,
        },
        index=dates,
    )
    return df


def test_calculate_technical_score_timeframes():
    df = create_sample_df(bullish=True)

    # Daily
    res_d = calculate_technical_score(df, timeframe="D")
    assert res_d["is_bullish"] is True
    assert res_d["score"] > 0

    # Weekly
    res_w = calculate_technical_score(df, timeframe="W")
    assert res_w["is_bullish"] is True

    # Monthly
    res_m = calculate_technical_score(df, timeframe="M")
    assert res_m["is_bullish"] is True


def test_calculate_technical_score_bearish_mtf():
    df = create_sample_df(bullish=False)

    # Daily
    res_d = calculate_technical_score(df, timeframe="D")
    assert res_d["is_bullish"] is False

    # Weekly
    res_w = calculate_technical_score(df, timeframe="W")
    assert res_w["is_bullish"] is False


def test_combined_score_timeframe_handling():
    """Combined score should skip fundamental score if timeframe != 'D'."""
    df = create_sample_df(bullish=True)
    info = {"forwardPE": 10, "pledgedPercent": 0.0}

    # Daily: should include fundamental
    res_d = calculate_combined_score(df, info, timeframe="D")
    assert res_d["fundamental_score"] == 15.0
    if res_d["rsi"] <= 80:
        assert res_d["score"] > 15.0
    else:
        assert res_d["score"] == 0.0

    # Weekly: should NOT include fundamental
    res_w = calculate_combined_score(df, info, timeframe="W")
    assert res_w["fundamental_score"] == 0.0
