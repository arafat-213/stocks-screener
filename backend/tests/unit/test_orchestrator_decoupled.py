import pytest
from unittest.mock import MagicMock, patch
from app.pipeline.orchestrator import run_pipeline
from app.db.models import PipelineRun, Stock, FundamentalCache, TechnicalSignal
import datetime

@patch('app.pipeline.orchestrator.get_nse_symbols')
@patch('app.pipeline.orchestrator.fetch_stock_data')
@patch('app.pipeline.orchestrator.passes_tier1_fast_filters')
@patch('app.pipeline.orchestrator.calculate_combined_score')
@patch('app.pipeline.orchestrator.fetch_and_cache_deep_fundamentals')
@patch('app.pipeline.orchestrator.resample_ohlcv')
@patch('app.pipeline.orchestrator.generate_daily_report')
@patch('app.screens.materializer.materialize_all_screens')
def test_run_pipeline_decoupled_scoring(
    mock_materialize,
    mock_report,
    mock_resample,
    mock_fetch_cache,
    mock_calc_score,
    mock_t1_filter,
    mock_fetch_data,
    mock_get_symbols
):
    # Setup mocks
    mock_db = MagicMock()
    mock_get_symbols.return_value = ['FAILED_QUALITY']
    
    # Mock data for FAILED_QUALITY
    mock_hist = MagicMock()
    mock_hist.empty = False
    mock_hist.index = [datetime.datetime.now()]
    mock_fetch_data.return_value = (mock_hist, {'longName': 'Failed Quality Corp', 'marketCap': 1000})
    
    mock_resample.return_value = mock_hist
    
    # Passes T1
    mock_t1_filter.return_value = (True, False)
    
    # Mock cache check - FAILS quality checks (profitability_streak_passed=False)
    mock_cache = MagicMock(
        profitability_streak_passed=False, 
        de_check_passed=True, 
        cache_version=1,
        last_updated=datetime.datetime.now()
    )
    
    # query().filter().first() sequence:
    # 1. Stock lookup
    # 2. FundamentalCache lookup (Tier 2 check)
    # 3. FundamentalCache lookup (Final filter & scoring stage)
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None,       # Stock lookup
        mock_cache, # Tier 2 check
        mock_cache  # Final filter & scoring
    ]
    
    # Mock TechnicalSignal lookup (to simulate upsert)
    mock_db.query.return_value.filter_by.return_value.first.return_value = None
    
    mock_calc_score.return_value = {
        'score': 50, 'rsi': 50, 'macd': 0.0, 
        'ema_signal': 'neutral', 'is_bullish': False,
        'momentum_1m': 0, 'momentum_3m': 0, 'momentum_6m': 0, 'momentum_12m': 0
    }
    
    run_pipeline(mock_db)
    
    # Verify results
    run = mock_db.add.call_args_list[0][0][0]
    assert isinstance(run, PipelineRun)
    assert run.tier1_count == 1
    # PREVIOUSLY this would be 0 because it would be skipped. 
    # NOW it should be 1 because we decoupled it.
    assert run.tier2_count == 1
    assert run.stocks_scored == 1
    
    # Verify scoring was still called despite failing quality checks
    assert mock_calc_score.call_count == 3 # D, W, M
