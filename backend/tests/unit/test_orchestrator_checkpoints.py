import pytest
from unittest.mock import MagicMock, patch
from app.pipeline.orchestrator import run_pipeline
from app.db.models import PipelineRun, PipelineCheckpoint, Stock, FundamentalCache
import datetime
import json
import pandas as pd

# Define standard decorators to reuse across tests
ORCHESTRATOR_PATCHES = [
    patch('app.pipeline.orchestrator.get_nse_symbols'),
    patch('app.pipeline.orchestrator.yf.download'),
    patch('app.pipeline.orchestrator.slice_bulk_df'),
    patch('app.pipeline.orchestrator.yf.Ticker'),
    patch('app.pipeline.orchestrator.fetch_stock_data'),
    patch('app.pipeline.orchestrator.passes_tier1_fast_filters'),
    patch('app.pipeline.orchestrator.calculate_combined_score'),
    patch('app.pipeline.orchestrator.fetch_and_cache_deep_fundamentals'),
    patch('app.pipeline.orchestrator.resample_ohlcv'),
    patch('app.pipeline.orchestrator.fetch_market_snapshots'),
    patch('app.pipeline.orchestrator.generate_daily_report'),
    patch('app.screens.materializer.materialize_all_screens'),
    patch('app.pipeline.orchestrator.compute_rs_ranks')
]

def apply_patches(func):
    for p in ORCHESTRATOR_PATCHES:
        func = p(func)
    return func

def get_mock_ta_data(score=80, bullish=True):
    return {
        'score': score, 'is_bullish': bullish, 'combined_score': score,
        'rsi': 60, 'macd': 1.0, 'ema_signal': 'bullish',
        'volume_signal': 'high', 'rsi_signal': 'neutral', 'atr': 2.5
    }

@apply_patches
def test_run_pipeline_resumes_from_checkpoint(
    mock_get_symbols,
    mock_download,
    mock_slice,
    mock_ticker,
    mock_fetch_data,
    mock_t1_filter,
    mock_calc_score,
    mock_fetch_cache,
    mock_resample,
    mock_market,
    mock_report,
    mock_materialize,
    mock_rs_ranks
):
    mock_db = MagicMock()
    mock_get_symbols.return_value = ['STK1', 'STK2', 'STK3']
    
    mock_hist = pd.DataFrame({'Close': [100.0]}, index=pd.to_datetime([datetime.datetime.now()]))
    mock_hist.index.name = "Date"
    mock_download.return_value = MagicMock()
    mock_slice.return_value = mock_hist
    
    mock_ticker_inst = MagicMock()
    mock_ticker_inst.fast_info = {'marketCap': 3000000000, 'threeMonthAverageVolume': 1000000, 'lastPrice': 100}
    mock_ticker_inst.info = {'longName': 'Stock'}
    mock_ticker.return_value = mock_ticker_inst
    
    mock_resample.return_value = mock_hist
    mock_calc_score.return_value = get_mock_ta_data()
    mock_market.return_value = []
    
    # Mock existing checkpoint: STK1 and STK2 already done in tier1
    mock_checkpoint = MagicMock()
    mock_checkpoint.completed_symbols = json.dumps(['STK1', 'STK2'])
    
    mock_run = MagicMock(run_id="old-run", status="failed", stop_requested=False, stocks_fetched=2)
    
    # query().filter().first() side effect
    call_idx = [0]
    def first_side_effect():
        idx = call_idx[0]
        call_idx[0] += 1
        return mock_run
    
    mock_db.query.return_value.filter.return_value.first.side_effect = first_side_effect
    mock_db.query.return_value.order_by.return_value.first.return_value = mock_run
    
    # filter_by is used for checkpoints and stock lookups
    def filter_by_side_effect(**kwargs):
        m = MagicMock()
        if kwargs.get('phase') == 'tier1':
            m.first.return_value = mock_checkpoint
        else:
            m.first.return_value = None
        return m
    mock_db.query.return_value.filter_by.side_effect = filter_by_side_effect
    
    run_pipeline(mock_db, resume_run_id="old-run")
    
    assert mock_run.status == "complete"
    # Should only process STK3
    assert mock_slice.call_count == 1
