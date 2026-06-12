import datetime

import pandas as pd

from app.backtest.engine import BacktestConfig, TradeResult, compute_metrics


def test_profit_factor_no_losses():
    # Setup: A few winning trades, no losses
    trades = [
        TradeResult(
            symbol="RELIANCE.NS",
            sector="Energy",
            signal_date=datetime.date(2024, 1, 1),
            entry_date=datetime.date(2024, 1, 2),
            exit_date=datetime.date(2024, 1, 10),
            exit_reason="target",
            signal_score=70.0,
            entry_price=2500.0,
            exit_price=2750.0,
            return_pct=10.0,
            rsi_at_signal=55.0,
            adx_at_signal=30.0,
            ema_signal="bullish_cross",
            position_size_used=10000.0,
        ),
        TradeResult(
            symbol="TCS.NS",
            sector="IT",
            signal_date=datetime.date(2024, 1, 5),
            entry_date=datetime.date(2024, 1, 6),
            exit_date=datetime.date(2024, 1, 15),
            exit_reason="target",
            signal_score=75.0,
            entry_price=3500.0,
            exit_price=3850.0,
            return_pct=10.0,
            rsi_at_signal=60.0,
            adx_at_signal=35.0,
            ema_signal="bullish_cross",
            position_size_used=10000.0,
        ),
    ]

    config = BacktestConfig(starting_capital=1000000.0)
    # Benchmark data not strictly needed for this metric but passed to avoid issues
    benchmark_data = pd.DataFrame()

    metrics = compute_metrics(trades, benchmark_data, config)

    # Current behavior (Bug): profit_factor is 0.0
    # Desired behavior: profit_factor should be 99.0 (infinite cap)
    assert metrics["profit_factor"] == 99.0, (
        f"Expected 99.0, got {metrics['profit_factor']}"
    )


def test_profit_factor_no_trades():
    metrics = compute_metrics([], pd.DataFrame(), BacktestConfig())
    assert metrics["profit_factor"] == 0.0
