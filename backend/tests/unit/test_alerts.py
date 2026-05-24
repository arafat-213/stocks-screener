import pytest
import datetime
import pandas as pd
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from app.db.models import TradeJournal, AlertLog
from app.alerts.engine import run_exit_alert_cycle

@pytest.fixture
def db_session():
    # This fixture should provide a clean database session
    # Based on existing tests, we can use the one from conftest
    pass

def test_run_exit_alert_cycle_no_positions(db):
    result = run_exit_alert_cycle(db)
    assert result == {"positions_checked": 0, "alerts_fired": 0}

@patch("app.alerts.engine.OHLCVCache")
@patch("app.alerts.engine.send_alert_email")
@patch("app.alerts.engine.build_exit_alert_email")
def test_run_exit_alert_cycle_stop_hit(mock_build_email, mock_send_email, mock_cache_class, db):
    # Setup
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_send_email.return_value = "msg_123"
    mock_build_email.return_value = "<html>test</html>"
    
    signal_date = datetime.date(2024, 1, 10)
    
    # Create an open position
    pos = TradeJournal(
        symbol="TEST.NS",
        entry_price=100.0,
        stop_loss=95.0,
        target=120.0,
        status="open",
        entry_date=datetime.date(2024, 1, 1),
        shares=100,
        position_value=10000.0
    )
    db.add(pos)
    db.commit()
    
    # Setup mock OHLCV data where Low <= stop_loss
    df = pd.DataFrame({
        "Open": [100.0],
        "High": [105.0],
        "Low": [94.0],  # Hit stop
        "Close": [96.0]
    }, index=[pd.Timestamp("2024-01-10")])
    mock_cache.get.return_value = df
    
    # Run
    result = run_exit_alert_cycle(db, signal_date=signal_date)
    
    # Verify
    assert result["positions_checked"] == 1
    assert result["alerts_fired"] == 1
    
    # Check AlertLog
    log = db.query(AlertLog).filter_by(symbol="TEST.NS", alert_type="stop_hit").first()
    assert log is not None
    assert log.signal_date == signal_date
    assert log.email_id == "msg_123"

@patch("app.alerts.engine.OHLCVCache")
@patch("app.alerts.engine.send_alert_email")
@patch("app.alerts.engine.build_exit_alert_email")
def test_run_exit_alert_cycle_target_hit(mock_build_email, mock_send_email, mock_cache_class, db):
    # Setup
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_send_email.return_value = "msg_456"
    mock_build_email.return_value = "<html>test</html>"
    
    signal_date = datetime.date(2024, 1, 10)
    
    # Create an open position
    pos = TradeJournal(
        symbol="TARGET.NS",
        entry_price=100.0,
        stop_loss=95.0,
        target=120.0,
        status="open",
        entry_date=datetime.date(2024, 1, 1),
        shares=100,
        position_value=10000.0
    )
    db.add(pos)
    db.commit()
    
    # Setup mock OHLCV data where High >= target
    df = pd.DataFrame({
        "Open": [115.0],
        "High": [121.0],  # Hit target
        "Low": [114.0],
        "Close": [119.0]
    }, index=[pd.Timestamp("2024-01-10")])
    mock_cache.get.return_value = df
    
    # Run
    result = run_exit_alert_cycle(db, signal_date=signal_date)
    
    # Verify
    assert result["positions_checked"] == 1
    assert result["alerts_fired"] == 1
    
    # Check AlertLog
    log = db.query(AlertLog).filter_by(symbol="TARGET.NS", alert_type="target_hit").first()
    assert log is not None
    assert log.signal_date == signal_date

@patch("app.alerts.engine.OHLCVCache")
@patch("app.alerts.engine.send_alert_email")
def test_run_exit_alert_cycle_approaching_stop(mock_send_email, mock_cache_class, db):
    # Setup
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    mock_send_email.return_value = "msg_789"
    
    signal_date = datetime.date(2024, 1, 10)
    
    # Create an open position
    pos = TradeJournal(
        symbol="NEAR_STOP.NS",
        entry_price=100.0,
        stop_loss=95.0,
        target=120.0,
        status="open",
        entry_date=datetime.date(2024, 1, 1),
        shares=100,
        position_value=10000.0
    )
    db.add(pos)
    db.commit()
    
    # Setup mock OHLCV data where Close is near stop
    df = pd.DataFrame({
        "Open": [98.0],
        "High": [99.0],
        "Low": [96.0],  # Low > stop_loss(95)
        "Close": [96.5] # distance_to_stop_pct = (96.5 - 95)/100 * 100 = 1.5% < 2%
    }, index=[pd.Timestamp("2024-01-10")])
    mock_cache.get.return_value = df
    
    # Run
    result = run_exit_alert_cycle(db, signal_date=signal_date)
    
    # Verify
    assert result["alerts_fired"] == 1
    log = db.query(AlertLog).filter_by(symbol="NEAR_STOP.NS", alert_type="stop_approached").first()
    assert log is not None

@patch("app.alerts.engine.OHLCVCache")
@patch("app.alerts.engine.send_alert_email")
def test_run_exit_alert_cycle_already_alerted(mock_send_email, mock_cache_class, db):
    # Setup
    mock_cache = MagicMock()
    mock_cache_class.return_value = mock_cache
    signal_date = datetime.date(2024, 1, 10)
    
    pos = TradeJournal(
        symbol="DUP.NS",
        entry_price=100.0,
        stop_loss=95.0,
        target=120.0,
        status="open",
        entry_date=datetime.date(2024, 1, 1),
        shares=100,
        position_value=10000.0
    )
    db.add(pos)
    
    # Pre-log an alert
    log = AlertLog(symbol="DUP.NS", signal_date=signal_date, alert_type="stop_hit")
    db.add(log)
    db.commit()
    
    # Setup mock OHLCV data hitting stop
    df = pd.DataFrame({
        "Open": [100.0], "High": [105.0], "Low": [94.0], "Close": [96.0]
    }, index=[pd.Timestamp("2024-01-10")])
    mock_cache.get.return_value = df
    
    # Run
    result = run_exit_alert_cycle(db, signal_date=signal_date)
    
    # Verify
    assert result["alerts_fired"] == 0 # Skipped because already alerted
