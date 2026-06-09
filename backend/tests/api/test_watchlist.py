from datetime import date, datetime

from app.db.models import FundamentalCache, Stock, TechnicalSignal, Watchlist


def test_add_to_watchlist_success(client, db):
    # 1. Setup prerequisite data
    symbol = "RELIANCE.NS"
    signal_date = date(2026, 5, 20)

    stock = Stock(symbol=symbol, name="Reliance Industries")
    db.add(stock)

    # Technical signal for the data
    signal = TechnicalSignal(
        symbol=symbol,
        date=datetime(2026, 5, 20),
        timeframe="D",
        entry_score=85.5,
        close_price=2500.0,
        atr=50.0,
        ema21_level=2450.0,
        ema_signal="bullish_cross",
        is_bullish=True,
    )
    db.add(signal)

    # Fundamental cache for quality tier
    cache = FundamentalCache(
        symbol=symbol,
        profitability_streak_passed=True,
        de_check_passed=True,
        fcf_positive=True,
    )
    db.add(cache)
    db.commit()

    # 2. Call the endpoint
    payload = {"symbol": symbol, "signal_date": signal_date.isoformat()}
    response = client.post("/api/watchlist/", json=payload)

    # 3. Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == symbol
    assert data["signal_date"] == signal_date.isoformat()
    assert data["quality_tier"] == "A"
    assert data["signal_score"] == 85.5
    assert data["planned_entry_low"] > 0
    assert data["planned_entry_high"] > 0
    assert data["stop_loss"] < 2500.0
    assert data["target"] > 2500.0


def test_add_to_watchlist_duplicate(client, db):
    # Setup
    symbol = "TCS.NS"
    signal_date = date(2026, 5, 20)
    stock = Stock(symbol=symbol, name="TCS")
    db.add(stock)

    signal = TechnicalSignal(
        symbol=symbol,
        date=datetime(2026, 5, 20),
        timeframe="D",
        entry_score=70.0,
        close_price=3500.0,
        atr=70.0,
    )
    db.add(signal)

    # Pre-existing watchlist entry
    existing = Watchlist(
        symbol=symbol, signal_date=signal_date, signal_score=70.0, status="watching"
    )
    db.add(existing)
    db.commit()

    payload = {"symbol": symbol, "signal_date": signal_date.isoformat()}
    response = client.post("/api/watchlist/", json=payload)

    assert response.status_code == 200
    assert response.json()["symbol"] == symbol


def test_add_to_watchlist_no_signal_fails(client, db):
    symbol = "INFY.NS"
    signal_date = date(2026, 5, 20)
    stock = Stock(symbol=symbol, name="Infosys")
    db.add(stock)
    db.commit()

    payload = {"symbol": symbol, "signal_date": signal_date.isoformat()}
    response = client.post("/api/watchlist/", json=payload)

    assert response.status_code == 404
    assert "Signal not found" in response.json()["detail"]
