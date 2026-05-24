import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
from app.db import models
import datetime

def test_get_open_trades_with_live_pnl(client, db):
    # Add a dummy open trade
    trade = models.TradeJournal(
        symbol="RELIANCE.NS",
        entry_price=2500.0,
        shares=10,
        position_value=25000.0,
        stop_loss=2400.0,
        target=2700.0,
        status='open',
        entry_date=datetime.date.today()
    )
    db.add(trade)
    db.commit()

    response = client.get("/api/journal/open")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    # Current price might vary as it's fetched live, but keys should exist
    assert "unrealized_pnl" in data[0]
    assert "live_return_pct" in data[0]
    assert "current_price" in data[0]

def test_get_closed_trades(client, db):
    # Add a dummy closed trade
    trade = models.TradeJournal(
        symbol="TCS.NS",
        entry_price=3000.0,
        shares=5,
        position_value=15000.0,
        stop_loss=2800.0,
        target=3500.0,
        exit_price=3200.0,
        exit_date=datetime.date.today(),
        pnl=1000.0,
        return_pct=6.67,
        status='closed'
    )
    db.add(trade)
    db.commit()

    response = client.get("/api/journal/closed")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["status"] == "closed"
    assert data[0]["pnl"] == 1000.0

def test_close_trade(client, db):
    # Add an open trade
    trade = models.TradeJournal(
        symbol="INFY.NS",
        entry_price=1500.0,
        shares=10,
        position_value=15000.0,
        stop_loss=1400.0,
        target=1700.0,
        status='open',
        entry_date=datetime.date.today() - datetime.timedelta(days=5)
    )
    db.add(trade)
    db.commit()
    trade_id = trade.id

    close_data = {
        "exit_price": 1600.0,
        "exit_date": str(datetime.date.today()),
        "exit_reason": "target"
    }
    response = client.patch(f"/api/journal/{trade_id}/close", json=close_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "closed"
    assert data["pnl"] == 1000.0
    assert abs(data["return_pct"] - 6.666) < 0.01
    assert data["holding_days"] == 5

def test_get_journal_stats(client, db):
    # Add one winner and one loser
    trade1 = models.TradeJournal(
        symbol="W1.NS", entry_price=100, shares=10, exit_price=110, 
        position_value=1000.0, stop_loss=90.0, target=120.0,
        status='closed', pnl=100, return_pct=10, exit_date=datetime.date.today()
    )
    trade2 = models.TradeJournal(
        symbol="L1.NS", entry_price=100, shares=10, exit_price=90, 
        position_value=1000.0, stop_loss=90.0, target=120.0,
        status='closed', pnl=-100, return_pct=-10, exit_date=datetime.date.today()
    )
    db.add_all([trade1, trade2])
    db.commit()

    response = client.get("/api/journal/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_trades"] == 2
    assert data["win_rate"] == 50.0
    assert data["total_pnl"] == 0.0
