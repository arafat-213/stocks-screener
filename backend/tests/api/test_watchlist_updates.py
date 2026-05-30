from datetime import date

from app.db.models import Watchlist


def test_update_watchlist_status_success(client, db):
    # Setup
    symbol = "RELIANCE.NS"
    entry = Watchlist(symbol=symbol, signal_date=date(2026, 5, 20), status="watching")
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # Call endpoint
    payload = {"status": "entered"}
    response = client.patch(f"/api/watchlist/{symbol}", json=payload)

    # Assertions
    assert response.status_code == 200
    assert response.json()["status"] == "entered"

    # Verify in DB
    db.refresh(entry)
    assert entry.status == "entered"


def test_update_watchlist_status_invalid_status(client, db):
    # Setup
    symbol = "TCS.NS"
    entry = Watchlist(symbol=symbol, signal_date=date(2026, 5, 20), status="watching")
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # Call endpoint with invalid status
    payload = {"status": "invalid"}
    response = client.patch(f"/api/watchlist/{symbol}", json=payload)

    # Assertions
    assert response.status_code == 422  # Pydantic validation error or 400


def test_update_watchlist_status_not_found(client, db):
    # Call endpoint for non-existent symbol
    payload = {"status": "skipped"}
    response = client.patch("/api/watchlist/NONEXISTENT.NS", json=payload)

    # Assertions
    assert response.status_code == 404


def test_remove_from_watchlist_success(client, db):
    # Setup
    symbol = "INFY.NS"
    entry = Watchlist(symbol=symbol, signal_date=date(2026, 5, 20), status="watching")
    db.add(entry)
    db.commit()

    # Call endpoint
    response = client.delete(f"/api/watchlist/{symbol}")

    # Assertions
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify in DB
    assert db.query(Watchlist).filter_by(symbol=symbol).first() is None


def test_get_expired_watchlist_entries(client, db):
    # Setup
    db.add(Watchlist(symbol="S1.NS", signal_date=date(2026, 5, 1), status="watching"))
    db.add(Watchlist(symbol="S2.NS", signal_date=date(2026, 5, 2), status="expired"))
    db.add(Watchlist(symbol="S3.NS", signal_date=date(2026, 5, 3), status="entered"))
    db.add(Watchlist(symbol="S4.NS", signal_date=date(2026, 5, 4), status="skipped"))
    db.commit()

    # Call endpoint
    response = client.get("/api/watchlist/expired")

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    symbols = [item["symbol"] for item in data]
    assert "S2.NS" in symbols
    assert "S3.NS" in symbols
    assert "S4.NS" in symbols
    assert "S1.NS" not in symbols
