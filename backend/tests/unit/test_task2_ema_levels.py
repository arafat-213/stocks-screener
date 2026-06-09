import pandas as pd

from app.pipeline.momentum_scorer import MomentumScorer

scorer = MomentumScorer()


def test_calculate_technical_score_returns_ema_levels():
    # Setup dummy dataframe that the scorer expects
    # Note: Scorer calculates EMAs using pandas-ta, so we can provide price data
    # and it will calculate them. Or we can mock the columns if we want to test extraction.
    # The requirement says: Setup dummy dataframe that the scorer expects
    # "Note: Scorer expects columns like "EMA_5", "EMA_13", etc. based on how pandas-ta names them"
    # Actually, MomentumScorer.calculate_technical_indicators calls df.ta.ema(length=5, append=True) etc.
    # which APPENDS columns to the dataframe.

    # Let's create a DF with enough rows (min 260 bars as per MomentumScorer logic for 'D' timeframe)
    data = {
        "Open": [100.0] * 300,
        "High": [105.0] * 300,
        "Low": [95.0] * 300,
        "Close": [102.0] * 300,
        "Volume": [1000] * 300,
    }
    df = pd.DataFrame(data)

    # We want to verify that the RETURNED dict contains these keys.
    # Since we are adding these keys to the returned dict in the implementation,
    # the test should fail if they are missing.

    result = scorer.calculate_score(df)

    assert "ema5_level" in result
    assert "ema13_level" in result
    assert "ema21_level" in result

    # Verify they are not None if the columns were calculated
    assert result["ema5_level"] is not None
    assert result["ema13_level"] is not None
    assert result["ema21_level"] is not None


def test_calculate_technical_score_empty_df_returns_none_levels():
    df = pd.DataFrame()
    result = scorer.calculate_score(df)

    assert result["ema5_level"] is None
    assert result["ema13_level"] is None
    assert result["ema21_level"] is None
