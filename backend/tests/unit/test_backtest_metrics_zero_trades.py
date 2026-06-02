import pandas as pd

from app.backtest.engine import BacktestConfig, compute_metrics


def test_compute_metrics_zero_trades():
    """
    Test that compute_metrics returns all required keys even when there are zero trades.
    This prevents KeyErrors in the backtest runner.
    """
    config = BacktestConfig(
        date_from="2023-01-01",
        date_to="2023-12-31",
        starting_capital=100000,
        position_size=10000,
    )

    # Zero trades
    trades = []
    # Mock benchmark data
    benchmark_df = pd.DataFrame(
        index=pd.date_range("2023-01-01", periods=5, freq="D"),
        data={"Close": [100, 101, 102, 103, 104]},
    )

    metrics = compute_metrics(trades, benchmark_df, config)

    required_keys = [
        "total_trades",
        "winning_trades",
        "win_rate",
        "avg_return_pct",
        "median_return_pct",
        "best_trade_pct",
        "worst_trade_pct",
        "max_drawdown_pct",
        "sharpe_ratio",
        "total_return_pct",
        "gross_return_pct",
        "total_cost_drag_pct",
        "benchmark_return_pct",
        "equity_curve",
        "expectancy",
        "profit_factor",
        "avg_win_pct",
        "avg_loss_pct",
        "exit_breakdown",
    ]

    for key in required_keys:
        assert key in metrics, f"Missing required key in metrics: {key}"

    assert metrics["total_trades"] == 0
    assert metrics["gross_return_pct"] == 0.0
    assert metrics["total_cost_drag_pct"] == 0.0


if __name__ == "__main__":
    # If run directly, just run the test
    test_compute_metrics_zero_trades()
    print("Test passed: compute_metrics correctly handles zero trades.")
