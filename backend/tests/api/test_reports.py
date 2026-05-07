from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import Stock, TechnicalSignal
from datetime import datetime, timedelta
import pytest

client = TestClient(app)

@pytest.fixture(scope="module")
def db():
    db = SessionLocal()
    try:
        # Clear existing test data if needed or just use it
        # For safety in this environment, I'll just insert what I need
        yield db
    finally:
        db.close()

def test_get_reports_list():
    """Test listing unique dates of reports."""
    response = client.get("/api/reports")
    # If not included in main.py yet, this might 404
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_get_reports_latest():
    """Test getting the latest report."""
    response = client.get("/api/reports/latest")
    assert response.status_code == 200
    # Even if empty, it should return a structure
    data = response.json()
    assert isinstance(data, list)

def test_get_reports_by_date():
    """Test getting report for a specific date."""
    # Using a future date that likely doesn't exist to see it handle empty
    response = client.get("/api/reports/2099-01-01")
    assert response.status_code == 200
    assert response.json() == []

def test_reports_data_integrity(db):
    """Test report content logic with inserted data."""
    # Insert mock data
    test_date = datetime(2025, 1, 1)
    test_stock = Stock(symbol="TEST.NS", name="Test Stock")
    
    # Check if stock exists to avoid duplicate primary key if test runs multiple times
    existing_stock = db.query(Stock).filter(Stock.symbol == "TEST.NS").first()
    if not existing_stock:
        db.add(test_stock)
    
    signals = [
        TechnicalSignal(date=test_date, symbol="TEST.NS", timeframe='D', is_bullish=True, entry_score=85.0, rsi=65.0),
        TechnicalSignal(date=test_date, symbol="TEST.NS", timeframe='W', is_bullish=True, entry_score=75.0, rsi=60.0),
        TechnicalSignal(date=test_date, symbol="TEST.NS", timeframe='M', is_bullish=False, entry_score=60.0, rsi=55.0),
    ]
    
    # Clean up existing signals for this date/symbol to avoid UniqueConstraint violation
    db.query(TechnicalSignal).filter(TechnicalSignal.date == test_date, TechnicalSignal.symbol == "TEST.NS").delete()
    
    for s in signals:
        db.add(s)
    db.commit()
    
    try:
        response = client.get("/api/reports/2025-01-01")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        
        report_item = next((item for item in data if item["symbol"] == "TEST.NS"), None)
        assert report_item is not None
        assert report_item["confluence"] == "2/3"
        assert report_item["daily_score"] == 85.0
        assert report_item["rsi"] == 65.0
        
        # Test /api/reports list
        response_list = client.get("/api/reports")
        assert "2025-01-01" in response_list.json()
        
    finally:
        # Cleanup
        db.query(TechnicalSignal).filter(TechnicalSignal.date == test_date, TechnicalSignal.symbol == "TEST.NS").delete()
        # db.delete(test_stock) # Keep stock or delete? Delete to stay clean.
        if not existing_stock:
             db.delete(test_stock)
        db.commit()
