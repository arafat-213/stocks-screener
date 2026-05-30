import datetime

from app.core.cache import response_cache
from app.db import models


def setup_pagination_data(db):
    now = datetime.datetime.utcnow()
    test_date = datetime.datetime(now.year, now.month, now.day)

    # Create multiple stocks across different sectors
    sectors = ["Technology", "Finance", "Healthcare"]
    for i in range(15):
        symbol = f"STOCK{i}.NS"
        sector = sectors[i % 3]
        stock = models.Stock(
            symbol=symbol, name=f"Stock {i}", sector=sector, market_cap=1000.0
        )
        db.add(stock)

        timeframes = ["D", "W", "M"]
        confluence_count = (i % 3) + 1  # 1, 2, 3

        for j, tf in enumerate(timeframes):
            is_bullish = j < confluence_count

            # Default sort order:
            # i=14: conf=3, score=84
            # ...
            # i=0: conf=1, score=70

            # We want RSI to be REVERSED compared to default sort
            # So STOCK0 (last in default) should be FIRST in RSI sort
            rsi_val = 30.0 + (14 - i) * 2  # i=0 -> 58, i=14 -> 30

            sig = models.TechnicalSignal(
                symbol=symbol,
                date=test_date,
                timeframe=tf,
                is_bullish=is_bullish,
                entry_score=70.0 + i,  # Varied score: 70 to 84
                rsi=rsi_val,
                close_price=100.0 + i,
                price_change_pct=1.0,
            )
            db.add(sig)

        # PE should also be different.
        # i=0 (last in default) should be FIRST in PE sort (lowest PE)
        pe_val = 20.0 + i  # i=0 -> 20, i=14 -> 34

        fund = models.FundamentalData(
            symbol=symbol, date=test_date, pe=pe_val, market_cap=1000.0
        )
        db.add(fund)

        cache = models.FundamentalCache(
            symbol=symbol,
            profitability_streak_passed=True,
            de_check_passed=True,
            last_updated=test_date,
            roe=15.0,
        )
        db.add(cache)

    db.commit()


def test_screener_results_pagination(db, client):
    setup_pagination_data(db)
    response_cache.invalidate()

    response = client.get("/api/dashboard/screener/results")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert len(data["items"]) == 15


def test_screener_results_filtering(db, client):
    setup_pagination_data(db)
    response_cache.invalidate()

    response = client.get("/api/dashboard/screener/results?sector=Technology")
    assert response.status_code == 200
    assert response.json()["total"] == 5


def test_screener_results_ordering(db, client):
    setup_pagination_data(db)
    response_cache.invalidate()

    response = client.get("/api/dashboard/screener/results")
    assert response.status_code == 200
    items = response.json()["items"]

    # Default Sort (Confluence DESC, Score DESC)
    # STOCK14 (conf 3, score 84) is first
    # STOCK0 (conf 1, score 70) is last
    assert items[0]["symbol"] == "STOCK14.NS"
    assert items[-1]["symbol"] == "STOCK0.NS"


def test_screener_results_sorting_param(db, client):
    setup_pagination_data(db)
    response_cache.invalidate()

    # Sort by RSI DESC
    # i=0 has RSI 58 (Highest)
    # i=14 has RSI 30 (Lowest)
    response = client.get("/api/dashboard/screener/results?sort_by=rsi")
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["symbol"] == "STOCK0.NS"
    assert items[-1]["symbol"] == "STOCK14.NS"

    # Sort by PE ASC (lower is better)
    # i=0 has PE 20 (Lowest)
    # i=14 has PE 34 (Highest)
    response = client.get("/api/dashboard/screener/results?sort_by=pe")
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["symbol"] == "STOCK0.NS"
    assert items[-1]["symbol"] == "STOCK14.NS"

    # Sort by Score DESC
    # i=14 has score 84 (Highest)
    response = client.get("/api/dashboard/screener/results?sort_by=score")
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["symbol"] == "STOCK14.NS"
    assert items[-1]["symbol"] == "STOCK0.NS"
