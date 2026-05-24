import pytest
from unittest.mock import MagicMock, patch
from app.backtest.engine import run_backtest, BacktestConfig
from app.db.models import BacktestRun

def test_run_backtest_with_screen_filter(db):
    # Setup
    run_id = "test-screen-filter"
    run = BacktestRun(run_id=run_id, status="pending", config="{}")
    db.add(run)
    
    from app.db.models import ScreenResult
    from datetime import date
    
    # Add historical screen results
    db.add(ScreenResult(screen_slug="52w-high", symbol="RELIANCE.NS", computed_at=date(2024, 1, 1), timeframe="D", rank=1, score_used=80))
    db.add(ScreenResult(screen_slug="52w-high", symbol="TCS.NS", computed_at=date(2024, 1, 1), timeframe="D", rank=2, score_used=75))
    db.commit()

    config = BacktestConfig(
        screen_slug="52w-high",
        symbol_limit=10,
        date_from=date(2023, 1, 1),
        date_to=date(2024, 12, 31)
    )

    # Mock SCREEN_REGISTRY to avoid KeyErrors
    with patch("app.backtest.engine.SCREEN_REGISTRY", {
        "52w-high": {"fn": MagicMock()}
    }):
        with patch("app.backtest.engine._ohlcv_cache.get", return_value=None): # skip benchmark
             with patch("app.backtest.engine.fetch_stock_data", return_value=(None, None)):
                  with patch("app.backtest.engine.compute_metrics") as mock_metrics:
                       mock_metrics.return_value = {
                           "total_trades": 0, "winning_trades": 0, "win_rate": 0.0,
                           "avg_return_pct": 0.0, "median_return_pct": 0.0,
                           "best_trade_pct": 0.0, "worst_trade_pct": 0.0,
                           "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0,
                           "total_return_pct": 0.0, "benchmark_return_pct": 0.0,
                           "equity_curve": [], "expectancy": 0.0, "profit_factor": 0.0,
                           "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
                           "exit_breakdown": {}, "gross_return_pct": 0.0, "total_cost_drag_pct": 0.0
                       }
                       run_backtest(db, run_id, config)

    # Verify
    updated_run = db.query(BacktestRun).filter_by(run_id=run_id).first()
    assert updated_run.symbols_total == 2
