import pytest
from unittest.mock import MagicMock, patch
from app.pipeline.reporter import generate_daily_report
from app.db.models import TechnicalSignal, Stock
import datetime
import os

def test_generate_daily_report(tmp_path):
    # Setup mocks
    mock_db = MagicMock()
    today = datetime.datetime.utcnow().date()
    
    # Mock scores and stocks
    score1 = TechnicalSignal(symbol='REL', entry_score=90.0, rsi=65.0, ema_signal='bullish', volume_signal='high', date=today, timeframe='D')
    stock1 = Stock(symbol='REL', name='Reliance')
    
    score2 = TechnicalSignal(symbol='INF', entry_score=85.0, rsi=55.0, ema_signal='neutral', volume_signal='normal', date=today, timeframe='D')
    stock2 = Stock(symbol='INF', name='Infosys')
    
    # Query join results
    mock_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        (score1, stock1),
        (score2, stock2)
    ]
    
    # Mock join to return a path in tmp_path
    original_join = os.path.join
    with patch('os.path.join', side_effect=lambda *args: str(tmp_path) if 'reports' in args else original_join(*args)):
        report_path = generate_daily_report(mock_db)
        
        assert report_path is not None
        assert os.path.exists(report_path)
        assert f"report_{today}.md" in report_path
        
        with open(report_path, 'r') as f:
            content = f.read()
            assert "# Daily Stock Scan Report" in content
            assert "REL" in content
            assert "Reliance" in content
            assert "90.00" in content
            assert "INF" in content
            assert "Infosys" in content
            assert "85.00" in content

def test_generate_daily_report_no_data():
    mock_db = MagicMock()
    mock_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    
    report_path = generate_daily_report(mock_db)
    assert report_path is None
