import pandas as pd

from app.backtest.engine import TradeResult, compute_metrics
from app.core.trading_config import UnifiedTradingConfig as BacktestConfig


def test_compute_metrics_max_drawdown_duration():
    # Setup trades and benchmark data to create a known drawdown period
    # Capital = 100,000. Trade 1 profit at t=2. Trade 2 loss at t=5.
    config = BacktestConfig(starting_capital=100000.0, position_size=10000.0)

    # 10 days of benchmark data (flat)
    dates = pd.date_range("2023-01-01", periods=10)
    benchmark_df = pd.DataFrame({"Close": [100.0] * 10}, index=dates)

    # Trade 1: Entry at 2023-01-01, Exit at 2023-01-02, +10% profit
    # Trade 2: Entry at 2023-01-04, Exit at 2023-01-05, -20% loss
    trades = [
        TradeResult(
            symbol="T1.NS",
            sector="S",
            signal_date=dates[0].date(),
            entry_date=dates[0].date(),
            exit_date=dates[1].date(),
            exit_reason="target",
            signal_score=100,
            entry_price=100,
            exit_price=110,
            return_pct=10.0,
            rsi_at_signal=50,
            adx_at_signal=30,
            ema_signal="",
        ),
        TradeResult(
            symbol="T2.NS",
            sector="S",
            signal_date=dates[3].date(),
            entry_date=dates[3].date(),
            exit_date=dates[4].date(),
            exit_reason="stop_loss",
            signal_score=100,
            entry_price=100,
            exit_price=80,
            return_pct=-20.0,
            rsi_at_signal=50,
            adx_at_signal=30,
            ema_signal="",
        ),
    ]

    # Equity Curve expected:
    # 2023-01-01: 100,000 (Start)
    # 2023-01-02: 100,000 + (10% - 0.25% cost)*10,000 = 100,000 + 975 = 100,975 (New Peak)
    # 2023-01-03: 100,975
    # 2023-01-04: 100,975
    # 2023-01-05: 100,975 + (-20% - 0.25% cost)*10,000 = 100,975 - 2025 = 98,950 (Below Peak)
    # 2023-01-06: 98,950
    # 2023-01-07: 98,950
    # 2023-01-08: 98,950
    # 2023-01-09: 98,950
    # 2023-01-10: 98,950

    # Drawdown expected: 8 days
    # Day 1: 100,000 (Equal to peak, but loop says not > peak, so current_dd_duration=1)
    # Day 2: 100,975 (New peak, current_dd_duration=0)
    # Day 3: 100,975 (Equal to peak, current_dd_duration=1)
    # Day 4: 100,975 (Equal to peak, current_dd_duration=2)
    # Day 5: 98,950 (Below peak, current_dd_duration=3)
    # Day 6: 98,950 (Below peak, current_dd_duration=4)
    # Day 7: 98,950 (Below peak, current_dd_duration=5)
    # Day 8: 98,950 (Below peak, current_dd_duration=6)
    # Day 9: 98,950 (Below peak, current_dd_duration=7)
    # Day 10: 98,950 (Below peak, current_dd_duration=8)

    metrics = compute_metrics(trades, benchmark_df, config)

    assert "max_drawdown_duration" in metrics
    assert metrics["max_drawdown_duration"] == 8


def test_compute_metrics_zero_trades_has_duration():
    config = BacktestConfig()
    metrics = compute_metrics([], pd.DataFrame(), config)
    assert "max_drawdown_duration" in metrics
    assert metrics["max_drawdown_duration"] == 0
