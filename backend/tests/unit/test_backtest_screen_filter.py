import pytest
from unittest.mock import MagicMock, patch
from app.backtest.engine import run_backtest, BacktestConfig
from app.db.models import BacktestRun

def test_run_backtest_with_screen_filter(db):
    # Setup
    run_id = "test-screen-filter"
    run = BacktestRun(run_id=run_id, status="pending", config="{}")
    db.add(run)
    db.commit()

    config = BacktestConfig(
        screen_slug="52w-high",
        symbol_limit=10
    )

    # Mock screen function returning only 2 symbols
    mock_screen_fn = MagicMock(return_value=[("RELIANCE.NS", 80), ("TCS.NS", 75)])
    
    with patch("app.backtest.engine.SCREEN_REGISTRY", {
        "52w-high": {"fn": mock_screen_fn}
    }):
        with patch("app.backtest.engine.fetch_stock_data", return_value=(MagicMock(), {})):
             with patch("app.backtest.engine.score_series", return_value=[]):
                  run_backtest(db, run_id, config)

    # Verify
    updated_run = db.query(BacktestRun).filter_by(run_id=run_id).first()
    assert updated_run.symbols_total == 2
    mock_screen_fn.assert_called_once()
