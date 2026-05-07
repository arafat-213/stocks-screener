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
def test_run_pipeline_tiered_flow(
    mock_resample,
    mock_fetch_cache,
    mock_calc_score,
    mock_t1_filter,
    mock_fetch_data,
    mock_get_symbols
):
    # Setup mocks
    mock_db = MagicMock()
    mock_get_symbols.return_value = ['RELIANCE', 'INFY']
    
    # Mock data for RELIANCE
    mock_hist = MagicMock()
    mock_hist.empty = False
    mock_hist.index = [datetime.datetime.utcnow()]
    mock_fetch_data.side_effect = [
        (mock_hist, {'longName': 'Reliance', 'marketCap': 1000}), # RELIANCE
        (None, None)   # INFY (fetcher returns None, None if hist.empty or error)
    ]
    
    mock_resample.return_value = mock_hist
    
    # RELIANCE passes T1, INFY fails T1 (but hist was empty so it won't even reach T1 filter in first loop if I updated orchestrator correctly)
    # Actually, in the orchestrator:
    # hist, info = fetch_stock_data(symbol, period="3y")
    # if hist is None or info is None: ... continue
    # INFY returns (empty, info) from fetch_stock_data? Let's check fetcher.
    # fetcher.py: if hist.empty: return None, None
    
    # So if INFY returns None, None, it continues.
    
    mock_t1_filter.side_effect = [
        (True, False) # RELIANCE
    ]
    
    # Mock cache check for RELIANCE
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None, # RELIANCE Stock entry not found (first loop)
        None, # RELIANCE FundamentalCache not found (refresh check)
        MagicMock(profitability_streak_passed=True, de_check_passed=True) # RELIANCE Cache (final filter)
    ]
    
    # Mock scoring upsert query
    mock_db.query.return_value.filter_by.return_value.first.return_value = None
    
    mock_calc_score.return_value = {
        'score': 80, 'rsi': 60, 'macd': 1.0, 
        'ema_signal': 'bullish', 'volume_signal': 'high',
        'is_bullish': True, 'rsi_signal': 'neutral'
    }
    
    run_pipeline(mock_db)
    
    # Verify RELIANCE triggered Tier 2 fetch
    mock_fetch_cache.assert_called_once()
    
    # Verify RELIANCE was scored for 3 timeframes (D, W, M)
    assert mock_calc_score.call_count == 3
    
    # Verify commit calls
    assert mock_db.commit.called
