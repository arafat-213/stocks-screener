from unittest.mock import MagicMock, patch

import pandas as pd

from app.pipeline.orchestrator import process_symbol


def test_process_symbol_maps_ema_levels():
    ta_data = {
        "score": 50.0,
        "is_bullish": True,
        "rsi": 60.0,
        "macd": 1.0,
        "ema_signal": "bullish",
        "close_price": 105.0,
        "ema5_level": 104.0,
        "ema13_level": 102.0,
        "ema20_level": 100.0,
        "ema26_level": 98.0,
    }

    # Mock fetch_stock_data to return a simple DF
    df = pd.DataFrame(
        {"Close": [100, 105]}, index=pd.to_datetime(["2023-01-01", "2023-01-02"])
    )

    with (
        patch(
            "app.pipeline.orchestrator._scorer.calculate_score", return_value=ta_data
        ),
        patch(
            "app.pipeline.fetcher.fetch_stock_data",
            return_value=(df, {"longName": "Apple Inc."}),
        ),
        patch("app.pipeline.orchestrator.resample_ohlcv", return_value=pd.DataFrame()),
    ):
        # Mock DB session
        mock_db = MagicMock()
        # Mock query to return None so it creates a new signal
        mock_db.query().filter_by().first.return_value = None

        # Call the function
        signals = process_symbol(
            "AAPL", mock_db, hist=df, info={"longName": "Apple Inc."}
        )

        # In multi-timeframe, daily is usually first if it exists
        assert len(signals) > 0
        signal = signals[0]

        assert signal.ema5_level == 104.0
        assert signal.ema13_level == 102.0
        assert signal.ema20_level == 100.0
        assert signal.ema26_level == 98.0
