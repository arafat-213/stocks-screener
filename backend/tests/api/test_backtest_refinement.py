from app.db import models
import uuid
import json
import datetime

def test_serialize_run_structure(client, db):
    # Create a dummy run
    run_id = str(uuid.uuid4())
    config = {
        "score_threshold": 60,
        "holding_days": 20,
        "stop_loss_pct": 7,
        "target_pct": 0,
        "include_fundamentals": False
    }
    db_run = models.BacktestRun(
        run_id=run_id,
        status="complete",
        config=json.dumps(config),
        symbols_total=10,
        symbols_done=10,
        total_trades=5,
        win_rate=0.6,
        avg_return_pct=2.5,
        equity_curve_json=json.dumps([{"date": "2024-01-01", "equity": 10000}])
    )
    db.add(db_run)
    db.commit()

    response = client.get(f"/api/backtest/{run_id}")
    assert response.status_code == 200
    data = response.json()
    
    # Check top level structure
    assert "run_id" in data
    assert "status" in data
    assert "config" in data
    assert "progress" in data
    assert "metrics" in data
    assert "equity_curve" in data
    
    # Check progress
    assert data["progress"]["symbols_done"] == 10
    assert data["progress"]["symbols_total"] == 10
    assert data["progress"]["pct"] == 100.0
    
    # Check metrics
    assert data["metrics"]["total_trades"] == 5
    assert data["metrics"]["win_rate"] == 0.6
    assert data["metrics"]["avg_return_pct"] == 2.5
    
    # Check config is parsed
    assert data["config"]["score_threshold"] == 60

def test_get_backtest_trades_sorting(client, db):
    run_id = str(uuid.uuid4())
    db_run = models.BacktestRun(run_id=run_id, status="complete", config="{}")
    db.add(db_run)
    
    # Create trades with different dates and returns
    t1 = models.BacktestTrade(
        run_id=run_id, symbol="S1", signal_date=datetime.date(2024, 1, 1),
        entry_date=datetime.date(2024, 1, 2), exit_date=datetime.date(2024, 1, 10),
        exit_reason="holding_period", signal_score=70, entry_price=100, exit_price=110, return_pct=10
    )
    t2 = models.BacktestTrade(
        run_id=run_id, symbol="S2", signal_date=datetime.date(2024, 1, 5),
        entry_date=datetime.date(2024, 1, 6), exit_date=datetime.date(2024, 1, 15),
        exit_reason="holding_period", signal_score=80, entry_price=100, exit_price=120, return_pct=20
    )
    db.add_all([t1, t2])
    db.commit()

    # Sort by return_pct desc
    response = client.get(f"/api/backtest/{run_id}/trades?sort_by=return_pct&sort_dir=desc")
    assert response.status_code == 200
    trades = response.json()["trades"]
    assert trades[0]["symbol"] == "S2"
    assert trades[0]["return_pct"] == 20
    
    # Sort by return_pct asc
    response = client.get(f"/api/backtest/{run_id}/trades?sort_by=return_pct&sort_dir=asc")
    assert response.status_code == 200
    trades = response.json()["trades"]
    assert trades[0]["symbol"] == "S1"
    assert trades[0]["return_pct"] == 10

def test_backtest_request_validation(client):
    # Test target_pct > 200 fails
    payload = {
        "target_pct": 201
    }
    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 422
    
    # Test target_pct <= 200 passes
    payload = {
        "target_pct": 200
    }
    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 200
