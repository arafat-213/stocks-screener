from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
from app.routers.backtest import BacktestRequest
from app.backtest.engine import BacktestConfig
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

def test_backtest_request_accepts_new_fields():
    payload = {
        "score_threshold": 50.0,
        "holding_days": 20,
        "stop_loss_pct": 7.0,
        "target_pct": 20.0,
        "atr_multiplier": 2.5,
        "risk_reward_ratio": 3.0,
        "use_atr_stops": True
    }
    request = BacktestRequest(**payload)
    assert request.atr_multiplier == 2.5
    assert request.risk_reward_ratio == 3.0
    assert request.use_atr_stops is True

def test_backtest_request_default_values():
    request = BacktestRequest()
    # Check that new fields have expected defaults
    assert request.atr_multiplier == 2.0
    assert request.risk_reward_ratio == 2.0
    assert request.use_atr_stops is False

def test_backtest_config_dataclass():
    config = BacktestConfig(
        atr_multiplier=3.5,
        risk_reward_ratio=2.5,
        use_atr_stops=True
    )
    assert config.atr_multiplier == 3.5
    assert config.risk_reward_ratio == 2.5
    assert config.use_atr_stops is True

def test_backtest_config_defaults():
    config = BacktestConfig()
    assert config.atr_multiplier == 2.0
    assert config.risk_reward_ratio == 2.0
    assert config.use_atr_stops is False
