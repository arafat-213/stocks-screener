import pytest
from datetime import date, timedelta, datetime
from app.db.models import Stock, TechnicalSignal, Watchlist
import pandas as pd
from unittest.mock import MagicMock

def test_get_watchlist_active_only(client, db):
    # Setup: 1 active, 1 expired/skipped
    db.add(Watchlist(symbol="RELIANCE.NS", signal_date=date(2025, 1, 1), status="watching"))
    db.add(Watchlist(symbol="TCS.NS", signal_date=date(2025, 1, 1), status="expired"))
    db.commit()

    response = client.get("/api/watchlist/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] == "RELIANCE.NS"

def test_get_watchlist_live_data(client, db, monkeypatch):
    # Setup entry
    symbol = "RELIANCE.NS"
    signal_date = date(2025, 1, 1)
    db.add(Watchlist(
        symbol=symbol, 
        signal_date=signal_date, 
        status="watching",
        planned_entry_low=2400.0,
        planned_entry_high=2500.0
    ))
    db.commit()

    # Mock OHLCV data
    # We need dates after 2025-01-01
    dates = [
        pd.Timestamp("2025-01-01"),
        pd.Timestamp("2025-01-02"),
        pd.Timestamp("2025-01-03"),
        pd.Timestamp("2025-01-04"),
    ]
    df = pd.DataFrame({
        "Close": [2500.0, 2480.0, 2450.0, 2460.0],
        "High": [2510.0, 2490.0, 2460.0, 2470.0],
        "Low": [2490.0, 2470.0, 2440.0, 2450.0],
        "Open": [2500.0, 2500.0, 2480.0, 2450.0],
    }, index=dates)
    
    mock_cache = MagicMock()
    mock_cache.get.return_value = df
    monkeypatch.setattr("app.routers.watchlist._ohlcv_cache", mock_cache)

    response = client.get("/api/watchlist/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    item = data[0]
    
    # 2025-01-02, 03, 04 are after 2025-01-01 -> 3 days elapsed
    assert item["days_elapsed"] == 3
    assert item["current_price"] == 2460.0
    # EMA20 will be calculated in the helper
    assert "vs_ema20_pct" in item
    assert "in_zone" in item

def test_auto_expiration(client, db, monkeypatch):
    # Setup entry older than 8 trading days
    symbol = "INFY.NS"
    signal_date = date(2025, 1, 1)
    db.add(Watchlist(symbol=symbol, signal_date=signal_date, status="watching"))
    db.commit()

    # Mock 10 days of OHLCV after signal_date
    dates = [pd.Timestamp(signal_date) + timedelta(days=i) for i in range(11)]
    df = pd.DataFrame({
        "Close": [1500.0] * 11,
    }, index=dates)
    
    mock_cache = MagicMock()
    mock_cache.get.return_value = df
    monkeypatch.setattr("app.routers.watchlist._ohlcv_cache", mock_cache)

    # First call should trigger expiration
    response = client.get("/api/watchlist/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0 # Should be empty because it expired

    # Verify status in DB
    entry = db.query(Watchlist).filter_by(symbol=symbol).first()
    assert entry.status == "expired"
