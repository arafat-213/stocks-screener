import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime
from app.pipeline.orchestrator import _compute_rs_ranks
from app.db.models import TechnicalSignal
import pandas as pd
import numpy as np

@pytest.fixture
def mock_db_session():
    session = MagicMock()
    return session

@patch('app.pipeline.orchestrator.fetch_stock_data')
def test_compute_rs_ranks_logic(mock_fetch, mock_db_session):
    # 1. Mock benchmark data (10% return)
    benchmark_dates = pd.date_range(end='2024-05-13', periods=300)
    mock_benchmark_df = pd.DataFrame({
        'Close': [100.0] * 300
    }, index=benchmark_dates)
    mock_benchmark_df.iloc[-1] = 110.0 # Today
    mock_benchmark_df.iloc[-252] = 100.0 # 1y ago
    
    mock_fetch.return_value = (mock_benchmark_df, {})

    # 2. Mock DB query results
    signal_date = date(2024, 5, 13)
    s1 = TechnicalSignal(id=1, symbol="ABC", date=signal_date, timeframe='D', momentum_12m=5.0)
    s2 = TechnicalSignal(id=2, symbol="XYZ", date=signal_date, timeframe='D', momentum_12m=15.0)
    s3 = TechnicalSignal(id=3, symbol="MNO", date=signal_date, timeframe='D', momentum_12m=25.0)
    s4 = TechnicalSignal(id=4, symbol="PQR", date=signal_date, timeframe='D', momentum_12m=None) # Should be skipped
    
    mock_db_session.query().filter().all.return_value = [s1, s2, s3, s4]

    # 3. Execute
    _compute_rs_ranks(mock_db_session, signal_date)

    # 4. Verify bulk_update_mappings call
    assert mock_db_session.bulk_update_mappings.called
    args, kwargs = mock_db_session.bulk_update_mappings.call_args
    assert args[0] == TechnicalSignal
    updates = args[1]
    
    # Sort updates by id for verification
    updates.sort(key=lambda x: x['id'])
    
    assert len(updates) == 3 # s4 skipped
    # Percentiles:
    # 5.0 (s1) -> rank 1/3 = 33.33
    # 15.0 (s2) -> rank 2/3 = 66.66
    # 25.0 (s3) -> rank 3/3 = 100.0
    
    assert updates[0]['rs_score'] == pytest.approx(33.33, 0.1)
    assert updates[1]['rs_score'] == pytest.approx(66.66, 0.1)
    assert updates[2]['rs_score'] == pytest.approx(100.0, 0.1)
    
    assert mock_db_session.commit.called

@patch('app.pipeline.orchestrator.fetch_stock_data')
def test_compute_rs_ranks_no_benchmark(mock_fetch, mock_db_session):
    # Benchmark fetch fails or has insufficient data
    mock_fetch.return_value = (None, None)
    
    _compute_rs_ranks(mock_db_session, date.today())
    
    assert not mock_db_session.bulk_update_mappings.called
    assert not mock_db_session.commit.called
