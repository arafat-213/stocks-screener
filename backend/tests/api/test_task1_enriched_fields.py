import pytest
from app.db import models
import datetime

def setup_test_data(db):
    now = datetime.datetime.utcnow()
    # Use a fixed date to avoid any timezone/midnight issues
    test_date = datetime.datetime(now.year, now.month, now.day)
    
    # Add Stock
    stock = models.Stock(symbol="TEST.NS", name="Test Stock", sector="Technology", market_cap=1000.0)
    db.add(stock)
    
    # Daily signal
    sig_d = models.TechnicalSignal(
        symbol="TEST.NS",
        date=test_date,
        timeframe='D',
        is_bullish=True,
        entry_score=80.0,
        rsi=60.0,
        macd=1.5,
        ema_signal="Bullish",
        rs_score=90.0,
        momentum_1m=5.0,
        momentum_3m=10.0,
        adx=25.0,
        above_200ema=True,
        ema_slope_20=1.5,
        week52_high=100.0,
        week52_low=80.0,
        pct_from_52w_high=-2.0,
        pct_from_52w_low=20.0,
        pct_from_resistance=-1.0,
        volume_breakout=True,
        close_price=98.0,
        price_change_pct=2.0
    )
    db.add(sig_d)
    
    # Weekly signal
    sig_w = models.TechnicalSignal(
        symbol="TEST.NS",
        date=test_date,
        timeframe='W',
        is_bullish=True,
        entry_score=75.0
    )
    db.add(sig_w)
    
    # Add fundamental data
    fund = models.FundamentalData(
        symbol="TEST.NS",
        date=test_date,
        roe=15.0,
        pe=20.0,
        market_cap=1000.0
    )
    db.add(fund)
    
    # Add fundamental cache
    cache = models.FundamentalCache(
        symbol="TEST.NS",
        peg_ratio=1.2,
        ev_to_ebitda=10.0,
        dividend_yield=1.5,
        roce=18.0,
        de_ratio=0.5,
        fcf_positive=True,
        dividend_consistency=True,
        market_cap_category="Small",
        roe=16.0,
        profitability_streak_passed=True,
        de_check_passed=True,
        last_updated=test_date
    )
    db.add(cache)
    
    # Add screen result
    sr = models.ScreenResult(
        screen_slug="momentum-monsters",
        symbol="TEST.NS",
        timeframe='D',
        rank=1,
        score_used=80.0
    )
    db.add(sr)
    
    db.flush()

def test_screens_enriched_fields(db, client):
    # Setup - db fixture handles isolation
    setup_test_data(db)
    
    # Execute
    response = client.get("/api/screens/momentum-monsters?live=false")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    result = data[0]
    
    # Check enriched fields
    assert result["symbol"] == "TEST.NS"
    assert result["rs_score"] == 90.0
    assert result["momentum_1m"] == 5.0
    assert result["momentum_3m"] == 10.0
    assert result["adx"] == 25.0
    assert result["ema_slope"] == 1.5
    assert result["pct_from_52w_high"] == -2.0
    assert result["pct_from_52w_low"] == 20.0
    assert result["week52_high"] == 100.0
    assert result["week52_low"] == 80.0
    assert result["pct_from_resistance"] == -1.0
    assert result["volume_breakout"] is True
    assert result["above_200ema"] is True
    assert result["peg_ratio"] == 1.2

def test_dashboard_enriched_fields(db, client):
    # Setup
    setup_test_data(db)
    
    # Clear cache to ensure we hit the DB
    from app.core.cache import response_cache
    response_cache.invalidate()
    
    # Execute
    response = client.get("/api/dashboard/screener/results")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0
    test_stock = next((item for item in data["items"] if item["symbol"] == "TEST.NS"), None)
    assert test_stock is not None
    assert test_stock["fundamentals"]["roe"] == 16.0
