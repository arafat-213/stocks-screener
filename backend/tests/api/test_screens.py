import pytest

def test_list_screens(client):
    response = client.get("/api/screens/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "slug" in data[0]
    assert "label" in data[0]
    assert "description" in data[0]
    assert "category" in data[0]

def test_get_screen_results_not_found(client):
    response = client.get("/api/screens/non-existent-slug")
    assert response.status_code == 404
    assert response.json()["detail"] == "Screen not found"

def test_get_screen_results_empty(client):
    # Use a real slug but with live=False. 
    # Even if DB is empty, it should fallback to live or return empty list if no data at all.
    response = client.get("/api/screens/52w-high?live=false")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_get_screen_results_with_setup(client, db):
    from app.db import models
    import datetime

    # Seed data
    symbol = "TEST.NS"
    stock = models.Stock(symbol=symbol, name="Test Stock", sector="Test Sector", market_cap=10000)
    db.add(stock)
    
    # 52w-high screen result
    today = datetime.date.today()
    sr = models.ScreenResult(
        screen_slug="52w-high",
        symbol=symbol,
        timeframe="D",
        rank=1,
        score_used=95.0,
        computed_at=today
    )
    db.add(sr)
    
    # Technical signal for setup calculation
    now = datetime.datetime.utcnow().replace(microsecond=0)
    tech = models.TechnicalSignal(
        symbol=symbol,
        date=now,
        timeframe="D",
        close_price=100.0,
        atr=2.5,
        rsi=65.0,
        adx=30.0,
        is_bullish=True,
        above_200ema=True,
        ema_slope_20=0.1
    )
    db.add(tech)
    
    # Fundamental cache (needed for outerjoin sometimes if sqlite behaves weirdly, though it shouldn't)
    fund = models.FundamentalCache(symbol=symbol, roe=15.0)
    db.add(fund)
    
    db.commit()

    # Clear cache to ensure we don't hit empty results from previous tests
    from app.screens.cache import screen_cache
    screen_cache.invalidate()

    response = client.get("/api/screens/52w-high?live=false")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0, f"Response should have data for {symbol}"
    assert data[0]["symbol"] == symbol
    assert "setup" in data[0]

def test_get_sector_rotation(client, db):
    # This endpoint was crashing due to missing table
    response = client.get("/api/screens/data/sector-rotation")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

