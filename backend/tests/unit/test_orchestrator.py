import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from app.db.models import PipelineRun
from app.pipeline.orchestrator import run_pipeline


def setup_robust_db_mock(mock_db, profitability_streak=True):
    """Configures a mock DB session to handle the orchestrator's common patterns."""
    mock_combined = MagicMock(
        stop_requested=False,
        cache_version=1,
        profitability_streak_passed=profitability_streak,
        de_check_passed=True,
        last_updated=datetime.datetime.now(),
        run_id="TEST_RUN",
        timestamp=datetime.datetime.now(),  # For market snapshot filter
    )

    # Track calls to return None for concurrency check (first call)
    call_idx = [0]

    def first_side_effect(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx == 0:
            return None  # Concurrency check
        return mock_combined

    mock_db.query.return_value.filter.return_value.first.side_effect = first_side_effect
    mock_db.query.return_value.filter_by.return_value.first.return_value = (
        None  # For upserts
    )
    mock_db.query.return_value.order_by.return_value.first.side_effect = (
        first_side_effect
    )

    return mock_combined


def get_mock_ta_data(score=80, bullish=True):
    return {
        "score": score,
        "is_bullish": bullish,
        "combined_score": score,
        "rsi": 60,
        "macd": 1.0,
        "ema_signal": "bullish",
        "volume_signal": "high",
        "rsi_signal": "neutral",
        "atr": 2.5,
        "momentum_1m": 5,
        "momentum_3m": 10,
        "momentum_6m": 15,
        "momentum_12m": 20,
        "adx": 25,
        "above_200ema": True,
        "ema_slope_20": 1.5,
        "week52_high": 120,
        "week52_low": 80,
        "pct_from_52w_high": -5,
        "pct_from_52w_low": 20,
        "resistance_level": 110,
        "pct_from_resistance": -2,
        "volume_breakout": True,
    }


@patch("app.pipeline.orchestrator.get_nse_symbols")
@patch("app.pipeline.orchestrator.yf.download")
@patch("app.pipeline.orchestrator.slice_bulk_df")
@patch("app.pipeline.orchestrator.yf.Ticker")
@patch("app.pipeline.orchestrator.fetch_stock_data")
@patch("app.pipeline.orchestrator.passes_tier1_fast_filters")
@patch("app.pipeline.orchestrator.calculate_combined_score")
@patch("app.pipeline.orchestrator.fetch_and_cache_deep_fundamentals")
@patch("app.pipeline.orchestrator.resample_ohlcv")
@patch("app.pipeline.orchestrator.fetch_market_snapshots")
@patch("app.pipeline.orchestrator.generate_daily_report")
@patch("app.screens.materializer.materialize_all_screens")
@patch("app.pipeline.orchestrator.compute_rs_ranks")
@patch("app.pipeline.orchestrator._ohlcv_cache")
def test_run_pipeline_tiered_flow(
    mock_ohlcv_cache,
    mock_rs_ranks,
    mock_materialize,
    mock_report,
    mock_market,
    mock_resample,
    mock_fetch_cache,
    mock_calc_score,
    mock_t1_filter,
    mock_fetch_data,
    mock_ticker,
    mock_slice,
    mock_download,
    mock_get_symbols,
):
    mock_db = MagicMock()
    setup_robust_db_mock(mock_db)
    mock_get_symbols.return_value = ["RELIANCE", "INFY"]

    mock_hist = pd.DataFrame(
        {
            "Open": [90.0, 95.0],
            "High": [105.0, 110.0],
            "Low": [85.0, 90.0],
            "Close": [100.0, 105.0],
            "Volume": [1000, 1100],
        },
        index=pd.to_datetime(
            [
                datetime.datetime.now() - datetime.timedelta(days=1),
                datetime.datetime.now(),
            ]
        ),
    )
    mock_hist.index.name = "Date"
    mock_download.return_value = MagicMock()
    mock_slice.return_value = mock_hist

    mock_ohlcv_cache.get.return_value = mock_hist

    mock_ticker_inst = MagicMock()
    mock_ticker_inst.fast_info = {
        "marketCap": 21_000_000_000,
        "threeMonthAverageVolume": 1_000_000,
        "lastPrice": 100,
    }
    mock_ticker_inst.info = {"longName": "Reliance", "sector": "Energy"}
    mock_ticker.return_value = mock_ticker_inst

    mock_resample.return_value = mock_hist
    mock_market.return_value = []
    mock_calc_score.return_value = get_mock_ta_data()

    run_pipeline(mock_db)

    run = mock_db.add.call_args_list[0][0][0]
    assert isinstance(run, PipelineRun)
    assert run.tier1_count >= 1


@patch("app.pipeline.orchestrator.get_nse_symbols")
@patch("app.pipeline.orchestrator.yf.download")
@patch("app.pipeline.orchestrator.slice_bulk_df")
@patch("app.pipeline.orchestrator.yf.Ticker")
@patch("app.pipeline.orchestrator.fetch_stock_data")
@patch("app.pipeline.orchestrator.passes_tier1_fast_filters")
@patch("app.pipeline.orchestrator.calculate_combined_score")
@patch("app.pipeline.orchestrator.fetch_and_cache_deep_fundamentals")
@patch("app.pipeline.orchestrator.resample_ohlcv")
@patch("app.pipeline.orchestrator.fetch_market_snapshots")
@patch("app.pipeline.orchestrator.generate_daily_report")
@patch("app.screens.materializer.materialize_all_screens")
@patch("app.pipeline.orchestrator.compute_rs_ranks")
@patch("app.pipeline.orchestrator._ohlcv_cache")
def test_run_pipeline_decoupled_scoring(
    mock_ohlcv_cache,
    mock_rs_ranks,
    mock_materialize,
    mock_report,
    mock_market,
    mock_resample,
    mock_fetch_cache,
    mock_calc_score,
    mock_t1_filter,
    mock_fetch_data,
    mock_ticker,
    mock_slice,
    mock_download,
    mock_get_symbols,
):
    mock_db = MagicMock()
    setup_robust_db_mock(mock_db, profitability_streak=False)
    mock_get_symbols.return_value = ["FAILED_QUALITY"]

    mock_hist = pd.DataFrame(
        {
            "Open": [90.0, 95.0],
            "High": [105.0, 110.0],
            "Low": [85.0, 90.0],
            "Close": [100.0, 105.0],
            "Volume": [1000, 1100],
        },
        index=pd.to_datetime(
            [
                datetime.datetime.now() - datetime.timedelta(days=1),
                datetime.datetime.now(),
            ]
        ),
    )
    mock_hist.index.name = "Date"
    mock_download.return_value = MagicMock()
    mock_slice.return_value = mock_hist

    mock_ohlcv_cache.get.return_value = mock_hist

    mock_ticker_inst = MagicMock()
    mock_ticker_inst.fast_info = {
        "marketCap": 3000000000,
        "threeMonthAverageVolume": 1000000,
        "lastPrice": 100,
    }
    mock_ticker_inst.info = {"longName": "Failed Quality Corp"}
    mock_ticker.return_value = mock_ticker_inst

    mock_resample.return_value = mock_hist
    mock_calc_score.return_value = get_mock_ta_data(score=50, bullish=False)
    mock_market.return_value = []

    run_pipeline(mock_db)

    run = mock_db.add.call_args_list[0][0][0]
    assert isinstance(run, PipelineRun)
    assert run.tier1_count == 1
    assert run.stocks_scored == 1


@patch("app.pipeline.orchestrator.get_nse_symbols")
@patch("app.pipeline.orchestrator.yf.download")
@patch("app.pipeline.orchestrator.slice_bulk_df")
@patch("app.pipeline.orchestrator.yf.Ticker")
@patch("app.pipeline.orchestrator.fetch_stock_data")
@patch("app.pipeline.orchestrator.passes_tier1_fast_filters")
@patch("app.pipeline.orchestrator.calculate_combined_score")
@patch("app.pipeline.orchestrator.fetch_and_cache_deep_fundamentals")
@patch("app.pipeline.orchestrator.resample_ohlcv")
@patch("app.pipeline.orchestrator.fetch_market_snapshots")
@patch("app.pipeline.orchestrator.generate_daily_report")
@patch("app.screens.materializer.materialize_all_screens")
@patch("app.pipeline.orchestrator.compute_rs_ranks")
@patch("app.pipeline.orchestrator._ohlcv_cache")
def test_run_pipeline_lazy_loading(
    mock_ohlcv_cache,
    mock_rs_ranks,
    mock_materialize,
    mock_report,
    mock_market,
    mock_resample,
    mock_fetch_cache,
    mock_calc_score,
    mock_t1_filter,
    mock_fetch_data,
    mock_ticker,
    mock_slice,
    mock_download,
    mock_get_symbols,
):
    mock_db = MagicMock()
    setup_robust_db_mock(mock_db)
    symbols = [f"STK{i}" for i in range(301)]
    mock_get_symbols.return_value = symbols

    mock_hist = pd.DataFrame(
        {
            "Open": [90.0, 95.0],
            "High": [105.0, 110.0],
            "Low": [85.0, 90.0],
            "Close": [100.0, 105.0],
            "Volume": [1000, 1100],
        },
        index=pd.to_datetime(
            [
                datetime.datetime.now() - datetime.timedelta(days=1),
                datetime.datetime.now(),
            ]
        ),
    )
    mock_hist.index.name = "Date"
    mock_download.return_value = MagicMock()
    mock_slice.return_value = mock_hist

    mock_ohlcv_cache.get.return_value = mock_hist

    mock_ticker_inst = MagicMock()
    mock_ticker_inst.fast_info = {
        "marketCap": 3000000000,
        "threeMonthAverageVolume": 1000000,
        "lastPrice": 100,
    }
    mock_ticker_inst.info = {"longName": "Test Stock"}
    mock_ticker.return_value = mock_ticker_inst

    mock_fetch_data.return_value = (
        mock_hist,
        {"longName": "Test Stock", "marketCap": 1000},
    )
    mock_resample.return_value = mock_hist
    mock_calc_score.return_value = get_mock_ta_data()
    mock_market.return_value = []

    run_pipeline(mock_db)

    assert mock_ohlcv_cache.get.call_count >= 300
