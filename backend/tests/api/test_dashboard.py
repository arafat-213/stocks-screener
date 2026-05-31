from datetime import datetime, timezone

from app.core.cache import response_cache
from app.db.models import FundamentalCache, Stock, TechnicalSignal


def test_get_screener_results(client):
    response = client.get("/api/dashboard/screener/results")
    assert response.status_code == 200
    # The response is now a dict with "items" key, not a list
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_get_screener_results_includes_setup(client, db):
    # Invalidate cache to ensure we see seeded data
    response_cache.invalidate()

    # Seed data
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stock = Stock(symbol="TEST.NS", name="Test Stock", sector="IT", market_cap=100000)
    db.add(stock)

    cache = FundamentalCache(
        symbol="TEST.NS",
        profitability_streak_passed=True,
        de_check_passed=True,
        roe=15.0,
        roce=20.0,
        de_ratio=0.5,
        market_cap_category="Large",
    )
    db.add(cache)

    for tf in ["D", "W", "M"]:
        sig = TechnicalSignal(
            symbol="TEST.NS",
            timeframe=tf,
            date=now,
            is_bullish=True,
            close_price=100.0,
            price_change_pct=2.0,
            entry_score=80,
            rsi=60,
            atr=5.0,
        )
        db.add(sig)

    db.commit()

    # Debug: Check if joins work
    from sqlalchemy import case, func

    latest_signal_sub = (
        db.query(
            TechnicalSignal.symbol,
            TechnicalSignal.timeframe,
            func.max(TechnicalSignal.date).label("max_date"),
        )
        .group_by(TechnicalSignal.symbol, TechnicalSignal.timeframe)
        .subquery()
    )

    confluence_sub = (
        db.query(
            TechnicalSignal.symbol,
            func.sum(case((TechnicalSignal.is_bullish, 1), else_=0)).label(
                "confluence_count"
            ),
        )
        .join(
            latest_signal_sub,
            (TechnicalSignal.symbol == latest_signal_sub.c.symbol)
            & (TechnicalSignal.timeframe == latest_signal_sub.c.timeframe)
            & (TechnicalSignal.date == latest_signal_sub.c.max_date),
        )
        .group_by(TechnicalSignal.symbol)
        .subquery()
    )

    debug_confluence = db.query(
        confluence_sub.c.symbol, confluence_sub.c.confluence_count
    ).all()
    print(f"DEBUG: Confluence Query Result: {debug_confluence}")

    query = (
        db.query(Stock, FundamentalCache, confluence_sub.c.confluence_count)
        .join(confluence_sub, Stock.symbol == confluence_sub.c.symbol)
        .outerjoin(FundamentalCache, Stock.symbol == FundamentalCache.symbol)
        .filter(FundamentalCache.profitability_streak_passed)
        .filter(FundamentalCache.de_check_passed)
    )

    debug_final = query.all()
    print(f"DEBUG: Final Query Result Count: {len(debug_final)}")

    response = client.get("/api/dashboard/screener/results")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) > 0
    item = data["items"][0]
    assert "setup" in item
    assert item["setup"] is not None
    assert "stop_loss" in item["setup"]


def test_get_pipeline_latest(client):
    response = client.get("/api/dashboard/pipeline/latest")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "market_context" in data


def test_get_dashboard_changes(client):
    response = client.get("/api/dashboard/changes")
    assert response.status_code == 200
    data = response.json()
    assert "changes" in data
    assert "as_of" in data
    assert "prev_date" in data
    assert isinstance(data["changes"], list)
