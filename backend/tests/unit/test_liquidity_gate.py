from app.db.models import PipelineRun, Stock
from app.pipeline.orchestrator import run_pipeline

# Mock fetcher or orchestrator internal methods to simulate a < 500Cr market cap stock
# For a pure unit test, we can mock `yf.Ticker` or the fetch info.


def test_liquidity_gate_rejects_microcaps(monkeypatch, db):
    """
    Ensures that stocks with market cap < 500 Cr (5,000,000,000) are dropped
    at Tier 1.5 and do not reach the scoring phase.
    """
    db_session = db
    # 1. Setup mock DB state
    db_session.add(Stock(symbol="MICRO.NS", sector="Technology"))
    db_session.add(Stock(symbol="MEGA.NS", sector="Technology"))
    db_session.commit()

    # 2. Mock Tier 1 to return our test stocks
    monkeypatch.setattr(
        "app.pipeline.orchestrator.get_nse_symbols",
        lambda *args, **kwargs: ["MICRO", "MEGA"],
    )
    monkeypatch.setattr(
        "app.pipeline.orchestrator.fetch_market_snapshots", lambda *args, **kwargs: []
    )

    # 3. Mock Tier 1.5 yfinance FastInfo to simulate sizes
    mock_fast_info_micro = {
        "marketCap": 400_000_000,
        "lastVolume": 100_000,
        "lastPrice": 100,
    }  # 400 Cr, 1Cr ADV
    mock_fast_info_mega = {
        "marketCap": 6_000_000_000,
        "lastVolume": 500_000,
        "lastPrice": 100,
    }  # 6000 Cr, 5Cr ADV

    def side_effect_fast_info(symbol):
        if "MICRO" in symbol:
            return mock_fast_info_micro
        return mock_fast_info_mega

    class MockTicker:
        def __init__(self, sym):
            self.sym = sym

        @property
        def fast_info(self):
            return side_effect_fast_info(self.sym)

        @property
        def info(self):
            return {"longName": "Test", "sector": "Test", "industry": "Test"}

    monkeypatch.setattr("app.pipeline.orchestrator.yf.Ticker", MockTicker)

    # 4. Mock process_symbol (scoring) so we don't need real OHLCV data
    class CallTracker:
        def __init__(self):
            self.calls = []

        def __call__(self, *args, **kwargs):
            self.calls.append(args)

    mock_process = CallTracker()
    monkeypatch.setattr("app.pipeline.orchestrator.process_symbol", mock_process)

    # 5. Mock ohlcv_cache.get and yf.download to return a dummy bullish dataframe
    import numpy as np
    import pandas as pd

    dates = pd.date_range(end=pd.Timestamp.today(), periods=300)
    prices = np.linspace(100, 200, 300)  # Uptrend
    mock_df = pd.DataFrame(
        {
            "Open": prices - 1,
            "High": prices + 1,
            "Low": prices - 2,
            "Close": prices,
            "Volume": [1000000] * 300,
        },
        index=dates,
    )

    monkeypatch.setattr(
        "app.pipeline.orchestrator.slice_bulk_df", lambda *args, **kwargs: mock_df
    )
    monkeypatch.setattr(
        "app.pipeline.orchestrator._ohlcv_cache.get", lambda *args, **kwargs: mock_df
    )

    # Disable sub-pipelines
    monkeypatch.setattr(
        "app.pipeline.orchestrator.compute_rs_ranks", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "app.screens.materializer.materialize_all_screens", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "app.pipeline.signal_digest.generate_signal_digest",
        lambda *args, **kwargs: None,
    )

    # Run
    run_pipeline(db_session, limit=2)

    # Verification
    run = db_session.query(PipelineRun).order_by(PipelineRun.timestamp.desc()).first()

    # Tier 1 count should be 1 (only MEGA survived the liquidity gate)
    assert run.tier1_count == 1

    # Scored count should be 1 (only MEGA survived the liquidity gate)
    assert run.stocks_scored == 1

    # Ensure process_symbol was ONLY called for MEGA (and the indices)
    called_symbols = [call[0] for call in mock_process.calls]
    assert "MEGA" in called_symbols
    assert "MICRO" not in called_symbols
