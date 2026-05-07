import pytest
from unittest.mock import MagicMock, patch
from app.pipeline.orchestrator import run_pipeline
from app.db.models import PipelineRun, Stock, FundamentalCache, DailyScore
import datetime

@patch('app.pipeline.orchestrator.get_nse_symbols')
@patch('app.pipeline.orchestrator.fetch_stock_data')
@patch('app.pipeline.orchestrator.passes_tier1_fast_filters')
@patch('app.pipeline.orchestrator.calculate_combined_score')
@patch('app.pipeline.orchestrator.fetch_and_cache_deep_fundamentals')
def test_run_pipeline_tiered_flow(
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
    mock_fetch_data.side_effect = [
        (MagicMock(), {'longName': 'Reliance', 'marketCap': 1000}), # RELIANCE
        (MagicMock(), {'longName': 'Infosys', 'marketCap': 500})   # INFY
    ]
    
    # RELIANCE passes T1, INFY fails T1
    mock_t1_filter.side_effect = [
        (True, False), # RELIANCE
        (False, False) # INFY
    ]
    
    # Mock cache check for RELIANCE (needs refresh)
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None, # RELIANCE Stock entry not found (first loop)
        None, # INFY Stock entry not found (first loop)
        None, # RELIANCE FundamentalCache not found (refresh check)
        MagicMock(profitability_streak_passed=True, de_check_passed=True) # RELIANCE Cache (final filter)
    ]
    
    mock_calc_score.return_value = {
        'score': 80, 'rsi': 60, 'macd': 1.0, 
        'ema_signal': 'bullish', 'volume_signal': 'high'
    }
    
    run_pipeline(mock_db)
    
    # Verify RELIANCE triggered Tier 2 fetch
    mock_fetch_cache.assert_called_once()
    assert 'RELIANCE' in mock_fetch_cache.call_args[0][0]
    assert 'INFY' not in mock_fetch_cache.call_args[0][0]
    
    # Verify RELIANCE was scored, INFY was not
    assert mock_calc_score.call_count == 1
    
    # Verify commit calls
    assert mock_db.commit.called
