import pytest
from app.db.models import Stock, TechnicalSignal, FundamentalData, FundamentalCache
import datetime

def test_get_stock_detail_404(client):
    response = client.get("/api/stocks/NONEXISTENT")
    assert response.status_code == 404
    assert response.json()["detail"] == "Stock not found"

def test_get_stock_detail_success(db, client):
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
    
    # Cleanup handled by db fixture transaction rollback
