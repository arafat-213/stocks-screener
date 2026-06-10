from datetime import date
from unittest.mock import patch

from app.db.models import TradeJournal, Watchlist


def test_get_action_center(client, db):
    # Seed data
    # 1. Watchlist candidate: price between low and high
    w1 = Watchlist(
        symbol="RELIANCE.NS",
        signal_date=date(2026, 6, 1),
        planned_entry_low=1000.0,
        planned_entry_high=1100.0,
        status="watching",
    )
    # 2. Open trade near SL: price within 1.5% of SL
    t1 = TradeJournal(
        symbol="TCS.NS",
        entry_price=3000.0,
        shares=10,
        position_value=30000.0,
        stop_loss=2900.0,
        status="open",
    )
    # 3. Open trade near target: price within 1.5% of target
    t2 = TradeJournal(
        symbol="INFY.NS",
        entry_price=1500.0,
        shares=20,
        position_value=30000.0,
        target=1600.0,
        status="open",
    )

    db.add_all([w1, t1, t2])
    db.commit()

    # Mock market prices
    # RELIANCE: 1050 (between 1000 and 1100) -> Candidate
    # TCS: 2920 -> (2920 - 2900) / 2900 * 100 = 0.69% <= 1.0% -> SL Risk
    # INFY: 1590 -> (1600 - 1590) / 1590 * 100 = 0.63% <= 1.0% -> Target Near

    mock_snapshots = [
        {"symbol": "RELIANCE.NS", "close": 1050.0, "change_pct": 0.5},
        {"symbol": "TCS.NS", "close": 2920.0, "change_pct": -0.5},
        {"symbol": "INFY.NS", "close": 1590.0, "change_pct": 1.0},
    ]

    with patch(
        "app.routers.dashboard.fetch_market_snapshots", return_value=mock_snapshots
    ):
        response = client.get("/api/dashboard/action-center")

    assert response.status_code == 200
    data = response.json()

    assert "entry_candidates" in data
    assert "sl_risk" in data
    assert "target_near" in data

    # RELIANCE: entry_low=1000, high=1100, price=1050
    assert any(
        item["symbol"] == "RELIANCE.NS"
        and item["current_price"] == 1050.0
        and "watchlist_id" in item
        and item["entry_low"] == 1000.0
        for item in data["entry_candidates"]
    )

    # TCS: price=2920, SL=2900, dist_pct = (2920-2900)/2900*100 = 0.69
    assert any(
        item["symbol"] == "TCS.NS"
        and item["current_price"] == 2920.0
        and item["dist_pct"] == 0.69
        and "id" in item
        for item in data["sl_risk"]
    )

    # INFY: price=1590, target=1600, dist_pct = (1600-1590)/1590*100 = 0.63
    assert any(
        item["symbol"] == "INFY.NS"
        and item["current_price"] == 1590.0
        and item["dist_pct"] == 0.63
        and "id" in item
        for item in data["target_near"]
    )
