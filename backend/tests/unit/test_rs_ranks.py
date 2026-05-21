import pytest
import datetime
import pandas as pd
from unittest.mock import MagicMock, patch
from app.pipeline.rs_ranks import compute_rs_ranks
from app.db.models import TechnicalSignal

def test_compute_rs_ranks_no_benchmark():
    db = MagicMock()
    with patch('app.pipeline.rs_ranks._ohlcv_cache.get', return_value=None):
        compute_rs_ranks(db, datetime.date.today())
    db.query.assert_not_called()

def test_compute_rs_ranks_success():
    db = MagicMock()
    signal_date = datetime.date.today()
    
    # Mock benchmark data
    hist = pd.DataFrame({'Close': [100] * 251 + [110]}, index=pd.date_range('2022-01-01', periods=252))
    
    s1 = TechnicalSignal(id=1, symbol='S1', momentum_12m=20.0)
    s2 = TechnicalSignal(id=2, symbol='S2', momentum_12m=5.0)
    s3 = TechnicalSignal(id=3, symbol='S3', momentum_12m=15.0)
    
    # The code calls: db.query(TechnicalSignal).filter(date==sd, tf=='D').all()
    # That is ONE filter call.
    db.query.return_value.filter.return_value.all.return_value = [s1, s2, s3]
    
    with patch('app.pipeline.rs_ranks._ohlcv_cache.get', return_value=hist):
        compute_rs_ranks(db, signal_date)
    
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
    
    db.query.return_value.filter.return_value.all.return_value = []
    
    with patch('app.pipeline.rs_ranks._ohlcv_cache.get', return_value=hist):
        compute_rs_ranks(db, signal_date)
    
    db.bulk_update_mappings.assert_not_called()

def test_compute_rs_ranks_no_valid_signals():
    db = MagicMock()
    signal_date = datetime.date.today()
    hist = pd.DataFrame({'Close': [100] * 252}, index=pd.date_range('2022-01-01', periods=252))
    
    s1 = TechnicalSignal(id=1, symbol='S1', momentum_12m=None)
    db.query.return_value.filter.return_value.all.return_value = [s1]
    
    with patch('app.pipeline.rs_ranks._ohlcv_cache.get', return_value=hist):
        compute_rs_ranks(db, signal_date)
    
    db.bulk_update_mappings.assert_not_called()
