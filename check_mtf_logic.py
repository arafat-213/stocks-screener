
import sys
import os
from unittest.mock import MagicMock

# Mock DB and models
sys.modules['app.db.models'] = MagicMock()
sys.modules['app.core.logging_manager'] = MagicMock()

from app.backtest.engine import run_backtest, BacktestConfig
from app.db.models import BacktestRun

def check_mtf_usage():
    db = MagicMock()
    run_id = "test-run"
    config = BacktestConfig(
        require_weekly_confirmation=True,
        require_monthly_confirmation=True,
        symbol_limit=1
    )

    # Mock run object
    run = MagicMock()
    db.query().filter_by().first.return_value = run

    # I want to see if simulate_portfolio is called with weekly_state_maps
    import app.backtest.engine as engine
    original_simulate_portfolio = engine.simulate_portfolio
    engine.simulate_portfolio = MagicMock()

    # Mock OHLCV
    engine._get_cached_ohlcv = MagicMock(return_value=pd.DataFrame({
        "Open": [100.0] * 500,
        "High": [105.0] * 500,
        "Low": [95.0] * 500,
        "Close": [102.0] * 500,
        "Volume": [1000] * 500,
    }, index=pd.date_range("2022-01-01", periods=500)))

    try:
        run_backtest(db, run_id, config)
    except Exception as e:
        print("Error during run_backtest:", e)

    args, kwargs = engine.simulate_portfolio.call_args
    print("weekly_state_maps passed to simulate_portfolio:", kwargs.get('weekly_state_maps'))
    print("monthly_state_maps passed to simulate_portfolio:", kwargs.get('monthly_state_maps'))

if __name__ == "__main__":
    import pandas as pd
    check_mtf_usage()
