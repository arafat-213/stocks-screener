from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
import pytest

client = TestClient(app)

def test_list_backtest_runs():
    response = client.get("/api/backtest/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_start_backtest():
    payload = {
        "score_threshold": 70,
        "holding_days": 10,
        "stop_loss_pct": 5,
        "target_pct": 15,
        "include_fundamentals": False,
        "symbol_limit": 5
    }
    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "pending"

def test_get_backtest_details_not_found():
    response = client.get("/api/backtest/non-existent-id")
    assert response.status_code == 404
