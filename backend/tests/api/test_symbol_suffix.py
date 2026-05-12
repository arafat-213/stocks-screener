import pytest
from unittest.mock import patch
from app.db.models import Stock, FundamentalCache
import datetime

@patch('app.routers.stocks.fetch_stock_data')
def test_get_stock_detail_case_insensitive_suffix(mock_fetch, db, client):
    # Seed data
    stock = Stock(symbol="RELIANCE", name="Reliance Industries", sector="Energy")
    db.add(stock)
    db.commit()
    
    import pandas as pd
    mock_df = pd.DataFrame({"Close": [100.0], "Open": [95.0], "High": [105.0], "Low": [90.0], "Volume": [1000]}, index=pd.to_datetime(["2024-05-11"]))
    mock_df.index.name = "Date"
    mock_fetch.return_value = (mock_df, {})

    # Test with .NS (works currently)
    response = client.get("/api/stocks/RELIANCE.NS")
    assert response.status_code == 200
    assert response.json()["symbol"] == "RELIANCE"
    
    # Test with .ns (currently fails because .replace(".NS", "") is case sensitive)
    response = client.get("/api/stocks/RELIANCE.ns")
    assert response.status_code == 200, f"Expected 200 for RELIANCE.ns, got {response.status_code}. Detail: {response.json().get('detail')}"
    assert response.json()["symbol"] == "RELIANCE"

def test_refresh_cache_case_insensitive_suffix(db, client):
    stock = Stock(symbol="RELIANCE", name="Reliance Industries", sector="Energy")
    db.add(stock)
    db.commit()
    
    # Test with .ns
    response = client.post("/api/stocks/RELIANCE.ns/refresh-cache")
    assert response.status_code == 200
    # The message should contain the clean symbol
    assert response.json()["message"] == "Force refresh scheduled for RELIANCE"
    
    # Verify DB entry
    cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == "RELIANCE").first()
    assert cache is not None
    assert cache.force_refresh == True
    
def test_cache_status_case_insensitive_suffix(db, client):
    stock = Stock(symbol="RELIANCE", name="Reliance Industries", sector="Energy")
    db.add(stock)
    fund_cache = FundamentalCache(symbol="RELIANCE", force_refresh=False)
    db.add(fund_cache)
    db.commit()
    
    # Test with .ns
    response = client.get("/api/stocks/RELIANCE.ns/cache-status")
    assert response.status_code == 200
    assert response.json()["symbol"] == "RELIANCE"
    assert "force_refresh" in response.json()
