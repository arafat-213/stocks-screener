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
    
    # Mock cache check and other filters for RELIANCE
    # Sequence of .query().filter().first() calls:
    # 1. run_pipeline: Secondary Concurrency Guard (existing running run?) -> None
    # Subsequent: stop checks (returns object with stop_requested=False) or Stock/Cache lookups
    mock_run = MagicMock(stop_requested=False)
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None, # Concurrency check
        mock_run, # stop check RELIANCE
        None, # RELIANCE Stock lookup
        mock_run, # stop check INFY
        mock_run, # stop check (Tier 2 loop)
        None, # RELIANCE Cache lookup (T2)
        None, # RELIANCE Stock lookup (T2)
        mock_run, # stop check (Scoring loop)
        MagicMock(profitability_streak_passed=True, de_check_passed=True) # RELIANCE Cache (scoring)
    ]
    
    # Mock scoring upsert query
    mock_db.query.return_value.filter_by.return_value.first.return_value = None
    
    mock_calc_score.return_value = {
        'score': 80, 'rsi': 60, 'macd': 1.0, 
        'ema_signal': 'bullish', 'volume_signal': 'high',
        'is_bullish': True, 'rsi_signal': 'neutral'
    }
    
    run_pipeline(mock_db)
    
    # Get the run object that was added to the mock db
    # It's the first object added via db.add()
    run = mock_db.add.call_args_list[0][0][0]
    assert isinstance(run, PipelineRun)
    assert run.tier1_count == 1 # RELIANCE survived T1
    assert run.tier2_count == 1 # RELIANCE survived T2

    # Verify RELIANCE triggered Tier 2 fetch
    mock_fetch_cache.assert_called_once()
    
    # Verify RELIANCE was scored for 3 timeframes (D, W, M)
    assert mock_calc_score.call_count == 3
    
    # Verify commit calls
    assert mock_db.commit.called

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
    # 1. run_pipeline: Secondary Concurrency Guard -> None
    # Subsequent: stop checks or lookups
    mock_run = MagicMock(stop_requested=False)
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None,       # Concurrency
        mock_run,   # stop check (Tier 1)
        None,       # Stock lookup
        mock_run,   # stop check (Tier 2 loop)
        mock_cache, # Tier 2 check
        None,       # Stock lookup (T2)
        mock_run,   # stop check (Scoring loop)
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

@patch('app.pipeline.orchestrator.get_nse_symbols')
@patch('app.pipeline.orchestrator.fetch_stock_data')
@patch('app.pipeline.orchestrator.passes_tier1_fast_filters')
@patch('app.pipeline.orchestrator.calculate_combined_score')
@patch('app.pipeline.orchestrator.fetch_and_cache_deep_fundamentals')
@patch('app.pipeline.orchestrator.resample_ohlcv')
@patch('app.pipeline.orchestrator.generate_daily_report')
@patch('app.screens.materializer.materialize_all_screens')
@patch('app.pipeline.orchestrator._compute_rs_ranks')
def test_run_pipeline_lazy_loading(
    mock_rs_ranks,
    mock_materialize,
    mock_report,
    mock_resample,
    mock_fetch_cache,
    mock_calc_score,
    mock_t1_filter,
    mock_fetch_data,
    mock_get_symbols
):
    # Setup mocks for > 300 symbols to trigger lazy loading
    # We only need one symbol in symbols, but we mock tier1_survivors to be large
    mock_db = MagicMock()
    symbols = [f'STK{i}' for i in range(301)]
    mock_get_symbols.return_value = symbols
    
    mock_hist = MagicMock()
    mock_hist.empty = False
    mock_hist.index = [datetime.datetime.now()]
    mock_fetch_data.return_value = (mock_hist, {'longName': 'Test Stock', 'marketCap': 1000})
    
    mock_resample.return_value = mock_hist
    mock_t1_filter.return_value = (True, False)
    # Mock cache check - SUCCESS quality checks
    # Use a REAL datetime to avoid TypeError: '<' not supported between instances of 'MagicMock' and 'datetime.datetime'
    mock_cache = MagicMock(
        profitability_streak_passed=True,
        de_check_passed=True,
        cache_version=1,
        last_updated=datetime.datetime.now()
    )

    mock_run = MagicMock(stop_requested=False)
    # Mocking long sequence of lookups
    # Sequence of .query().filter().first() calls:
    # 1. run_pipeline: Secondary Concurrency Guard -> None
    # 2. _is_stop_requested (Tier 1 loop)
    # 3. Stock lookup (Tier 1 loop)
    # ...
    # 4. _is_stop_requested (Scoring loop)
    # 5. FundamentalCache lookup (Scoring loop)
    # ...

    # Let's use a simple function for all first() calls
    mock_run = MagicMock(stop_requested=False)
    
    # Track calls to understand the sequence if it fails
    call_idx = [0]
    def db_query_first_side_effect(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx == 0: return None # Concurrency check
        # For all other calls, return mock_run or mock_cache based on likely caller
        # This is safe because both have the fields needed for stop_check and cache_check
        return mock_cache if idx % 2 == 0 else mock_run
    
    mock_db.query.return_value.filter.return_value.first.side_effect = db_query_first_side_effect

    run_pipeline(mock_db)
    
    # Verify results
    # Tier 1 calls: 301
    # Scoring calls: 301 (because hist_cache was cleared)
    # Plus index snapshots (2)
    assert mock_fetch_data.call_count >= 600
