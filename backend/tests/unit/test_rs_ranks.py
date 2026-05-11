import pytest
import datetime
import pandas as pd
from unittest.mock import MagicMock, patch
from app.pipeline.rs_ranks import compute_rs_ranks
from app.db.models import TechnicalSignal

def test_compute_rs_ranks_no_benchmark():
    db = MagicMock()
    with patch('app.pipeline.rs_ranks.fetch_stock_data', return_value=(None, None)):
        compute_rs_ranks(db, datetime.date.today())
    db.query.assert_not_called()

def test_compute_rs_ranks_success():
    db = MagicMock()
    signal_date = datetime.date.today()
    
    # Mock benchmark data
    # Need at least 252 bars. Last price is 110, price 252 bars ago is 100.
    # Return = (110/100 - 1) * 100 = 10%
    hist = pd.DataFrame({'Close': [100] * 251 + [110]}, index=pd.date_range('2022-01-01', periods=252))
    
    # Mock signals
    s1 = MagicMock(spec=TechnicalSignal)
    s1.id = 1
    s1.symbol = 'S1'
    s1.momentum_12m = 20.0
    
    s2 = MagicMock(spec=TechnicalSignal)
    s2.id = 2
    s2.symbol = 'S2'
    s2.momentum_12m = 5.0
    
    s3 = MagicMock(spec=TechnicalSignal)
    s3.id = 3
    s3.symbol = 'S3'
    s3.momentum_12m = 15.0
    
    # Setup query mock
    # db.query(TechnicalSignal).filter(...).filter(...).all()
    query_mock = db.query.return_value.filter.return_value.filter.return_value
    query_mock.all.return_value = [s1, s2, s3]
    
    with patch('app.pipeline.rs_ranks.fetch_stock_data', return_value=(hist, {})):
        compute_rs_ranks(db, signal_date)
    
    # Expected ranks (sorted by excess return):
    # S2 (5% momentum, -5% excess): Rank 1/3 -> 33.33
    # S3 (15% momentum, 5% excess): Rank 2/3 -> 66.66
    # S1 (20% momentum, 10% excess): Rank 3/3 -> 100.0
    
    db.bulk_update_mappings.assert_called_once()
    updates = db.bulk_update_mappings.call_args[0][1]
    
    updates_dict = {u['id']: u['rs_score'] for u in updates}
    assert updates_dict[1] == pytest.approx(100.0)
    assert updates_dict[2] == pytest.approx(33.3333333)
    assert updates_dict[3] == pytest.approx(66.6666666)
    db.commit.assert_called()

def test_compute_rs_ranks_no_signals():
    db = MagicMock()
    signal_date = datetime.date.today()
    hist = pd.DataFrame({'Close': [100] * 252}, index=pd.date_range('2022-01-01', periods=252))
    
    query_mock = db.query.return_value.filter.return_value.filter.return_value
    query_mock.all.return_value = []
    
    with patch('app.pipeline.rs_ranks.fetch_stock_data', return_value=(hist, {})):
        compute_rs_ranks(db, signal_date)
    
    db.bulk_update_mappings.assert_not_called()

def test_compute_rs_ranks_no_valid_signals():
    db = MagicMock()
    signal_date = datetime.date.today()
    hist = pd.DataFrame({'Close': [100] * 252}, index=pd.date_range('2022-01-01', periods=252))
    
    s1 = TechnicalSignal(id=1, symbol='S1', momentum_12m=None)
    
    query_mock = db.query.return_value.filter.return_value.filter.return_value
    query_mock.all.return_value = [s1]
    
    with patch('app.pipeline.rs_ranks.fetch_stock_data', return_value=(hist, {})):
        compute_rs_ranks(db, signal_date)
    
    db.bulk_update_mappings.assert_not_called()
