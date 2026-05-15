import pytest
from unittest.mock import patch
import pandas as pd
from app.db.models import Stock, TechnicalSignal, FundamentalData, FundamentalCache
import datetime

def test_get_stock_detail_404(client):
    response = client.get("/api/stocks/NONEXISTENT")
    assert response.status_code == 404
    assert response.json()["detail"] == "Stock not found"

@patch('app.routers.stocks.fetch_stock_data')
def test_get_stock_detail_success(mock_fetch, db, client):
    # Mock OHLCV data
    mock_df = pd.DataFrame({"Close": [100.0], "Open": [95.0], "High": [105.0], "Low": [90.0], "Volume": [1000]}, index=pd.to_datetime(["2024-05-11"]))
    mock_df.index.name = "Date"
    mock_fetch.return_value = (mock_df, {})
    # Seed data
    stock = Stock(symbol="TEST_RELIANCE", name="Test Reliance", sector="Energy")
    db.add(stock)
    
    # Daily signal
    sig_d = TechnicalSignal(
        date=datetime.datetime.utcnow(),
        symbol="TEST_RELIANCE",
        timeframe='D',
        is_bullish=True,
        entry_score=80.0,
        rsi=65.0,
        ema_signal="Bullish",
        volume_signal="High",
        rsi_signal="Neutral"
    )
    db.add(sig_d)
    
    # Weekly signal
    sig_w = TechnicalSignal(
        date=datetime.datetime.utcnow(),
        symbol="TEST_RELIANCE",
        timeframe='W',
        is_bullish=True,
        entry_score=75.0,
        rsi=60.0,
        ema_signal="Bullish",
        volume_signal="Normal",
        rsi_signal="Neutral"
    )
    db.add(sig_w)
    
    # Monthly signal
    sig_m = TechnicalSignal(
        date=datetime.datetime.utcnow(),
        symbol="TEST_RELIANCE",
        timeframe='M',
        is_bullish=False,
        entry_score=50.0,
        rsi=45.0,
        ema_signal="Neutral",
        volume_signal="Low",
        rsi_signal="Oversold"
    )
    db.add(sig_m)
    
    # Fundamental Data
    fund_data = FundamentalData(
        date=datetime.datetime.utcnow(),
        symbol="TEST_RELIANCE",
        pe=20.0,
        roe=15.0,
        eps_growth=10.0
    )
    db.add(fund_data)
    
    # Fundamental Cache
    fund_cache = FundamentalCache(
        symbol="TEST_RELIANCE",
        de_ratio=0.5,
        sector="Energy"
    )
    db.add(fund_cache)
    
    db.commit()
    
    response = client.get("/api/stocks/TEST_RELIANCE")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "TEST_RELIANCE"
    assert data["name"] == "Test Reliance"
    assert "ohlcv" in data
    assert "scores" in data
    assert "D" in data["scores"]
    assert "W" in data["scores"]
    assert "M" in data["scores"]
    assert data["scores"]["D"]["score"] == 80.0
    assert "score_history" in data
    assert len(data["score_history"]) >= 1
    assert "fundamentals" in data
    assert data["fundamentals"]["pe"] == 20.0
    assert data["fundamentals"]["debt_equity"] == 0.5
    
@patch('app.routers.stocks.fetch_stock_data')
def test_get_stock_detail_includes_setup(mock_fetch, db, client):
    # Mock OHLCV data
    mock_df = pd.DataFrame({"Close": [100.0], "Open": [95.0], "High": [105.0], "Low": [90.0], "Volume": [1000]}, index=pd.to_datetime(["2024-05-11"]))
    mock_df.index.name = "Date"
    mock_fetch.return_value = (mock_df, {})

    # Seed data
    symbol = "SETUP_STOCK"
    stock = Stock(symbol=symbol, name="Setup Stock", sector="Tech")
    db.add(stock)

    # Daily signal with ATR and close price
    sig_d = TechnicalSignal(
        date=datetime.datetime.utcnow(),
        symbol=symbol,
        timeframe='D',
        close_price=100.0,
        atr=2.5,
        ema_signal="bullish_cross",
        entry_score=85.0
    )
    db.add(sig_d)
    db.commit()

    response = client.get(f"/api/stocks/{symbol}")
    assert response.status_code == 200
    data = response.json()
    
    assert "setup" in data
    assert data["setup"] is not None
    assert data["setup"]["setup_type"] == "ema_crossover"
    assert data["setup"]["atr"] == 2.5
    assert "entry_zone" in data["setup"]
    assert "stop_loss" in data["setup"]
    assert len(data["setup"]["targets"]) > 0
