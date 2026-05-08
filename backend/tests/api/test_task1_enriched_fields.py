import pytest
from app.db import models
import datetime

def setup_test_data(db):
    # Add a stock
    stock = models.Stock(symbol="TEST.NS", name="Test Stock", sector="Technology", market_cap=1000.0)
    db.add(stock)
    db.flush()
    
    # Add technical signal
    now = datetime.datetime.utcnow()
    tech = models.TechnicalSignal(
        date=now,
        symbol="TEST.NS",
        timeframe='D',
        is_bullish=True,
        entry_score=80.0,
        rs_score=90.0,
        momentum_1m=5.0,
        momentum_3m=10.0,
        adx=25.0,
        ema_slope_20=1.5,
        pct_from_52w_high=-2.0,
        pct_from_52w_low=20.0,
        week52_high=100.0,
        week52_low=80.0,
        pct_from_resistance=-1.0,
        volume_breakout=True,
        above_200ema=True,
        close_price=98.0,
        price_change_pct=1.0
    )
    db.add(tech)
    
    # Add fundamental data
    fund = models.FundamentalData(
        date=now,
        symbol="TEST.NS",
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
        de_check_passed=True
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
    
    db.commit()

def test_screens_enriched_fields(db, client):
    # Setup - db fixture handles isolation, setup_test_db handles tables
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
    assert result["ev_to_ebitda"] == 10.0
    assert result["dividend_yield"] == 1.5
    assert result["roce"] == 18.0
    assert result["de_ratio"] == 0.5
    assert result["fcf_positive"] is True
    assert result["dividend_consistency"] is True
    # market_cap_category comes from cache
    assert result["market_cap_category"] == "Small"

def test_dashboard_enriched_fields(db, client):
    # Setup
    setup_test_data(db)
    
    # Execute
    response = client.get("/api/screener/results")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    
    # Find our test stock
    test_stock = next((item for item in data if item["symbol"] == "TEST.NS"), None)
    assert test_stock is not None
    
    # Check roe fallback logic (cache.roe = 16.0, fund.roe = 15.0)
    assert test_stock["fundamentals"]["roe"] == 16.0
    
    # Test fallback to fund.roe
    db.query(models.FundamentalCache).filter(models.FundamentalCache.symbol == "TEST.NS").update({"roe": None})
    db.commit()
    
    response = client.get("/api/screener/results")
    data = response.json()
    test_stock = next((item for item in data if item["symbol"] == "TEST.NS"), None)
    assert test_stock["fundamentals"]["roe"] == 15.0
