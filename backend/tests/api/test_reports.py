from datetime import datetime

from app.db.models import Stock, TechnicalSignal


def test_get_reports_list(client):
    """Test listing unique dates of reports."""
    response = client.get("/api/reports")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_reports_latest(client):
    """Test getting the latest report."""
    response = client.get("/api/reports/latest")
    assert response.status_code == 200
    # Even if empty, it should return a structure
    data = response.json()
    assert isinstance(data, list)


def test_get_reports_by_date(client):
    """Test getting report for a specific date."""
    # Using a future date that likely doesn't exist to see it handle empty
    response = client.get("/api/reports/2099-01-01")
    assert response.status_code == 200
    assert response.json() == []


def test_reports_data_integrity(db, client):
    """Test report content logic with inserted data."""
    # Insert mock data
    test_date = datetime(2025, 1, 1)
    test_stock = Stock(symbol="TEST.NS", name="Test Stock")
    db.add(test_stock)

    signals = [
        TechnicalSignal(
            date=test_date,
            symbol="TEST.NS",
            timeframe="D",
            is_bullish=True,
            entry_score=85.0,
            rsi=65.0,
        ),
        TechnicalSignal(
            date=test_date,
            symbol="TEST.NS",
            timeframe="W",
            is_bullish=True,
            entry_score=75.0,
            rsi=60.0,
        ),
        TechnicalSignal(
            date=test_date,
            symbol="TEST.NS",
            timeframe="M",
            is_bullish=False,
            entry_score=60.0,
            rsi=55.0,
        ),
    ]

    for s in signals:
        db.add(s)
    db.commit()

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

    # Cleanup handled by db fixture
