from app.backtest.engine import BacktestConfig, compute_metrics


def test_compute_metrics_empty_trades_returns_all_keys():
    """
    Regression test for KeyError when trades list is empty.
    Verifies that compute_metrics returns all keys expected by run_backtest.
    """
    config = BacktestConfig()
    metrics = compute_metrics([], None, config)

    expected_keys = [
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

    for key in expected_keys:
        assert key in metrics, f"Missing key in compute_metrics output: {key}"
