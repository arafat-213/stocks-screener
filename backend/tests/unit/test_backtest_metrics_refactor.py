import pytest
import pandas as pd
import numpy as np
import datetime
from app.backtest.engine import compute_metrics, BacktestConfig, TradeResult

def test_benchmark_return_calculation():
    """Verify benchmark return is calculated correctly from the start and end of provided benchmark_df."""
    trades = [
        TradeResult(
            symbol="TEST.NS", sector="Tech", 
            signal_date=datetime.date(2023, 1, 1),
            entry_date=datetime.date(2023, 1, 2),
            exit_date=datetime.date(2023, 1, 10),
            exit_reason="holding_period", signal_score=70.0,
            entry_price=100.0, exit_price=110.0, return_pct=10.0,
            rsi_at_signal=50.0, adx_at_signal=20.0, ema_signal="bullish"
        )
    ]
    
    benchmark_dates = pd.date_range(start="2023-01-01", end="2023-01-15", freq='D')
    # Price goes from 100 to 114
    benchmark_df = pd.DataFrame({
        "Close": [100.0 + i for i in range(len(benchmark_dates))]
    }, index=benchmark_dates)
    
    config = BacktestConfig(starting_capital=1000000.0, position_size=10000.0)
    
    metrics = compute_metrics(trades, benchmark_df, config)
    
    # benchmark_return_pct should be ((100+14) - 100) / 100 * 100 = 14%
    assert metrics['benchmark_return_pct'] == pytest.approx(14.0)
    # Equity curve should have same length as benchmark_df
    assert len(metrics['equity_curve']) == 15

def test_benchmark_slicing_logic_simulation():
    """Verify the slicing logic used in run_backtest to ensure benchmark aligns with trades."""
    benchmark_dates = pd.date_range(start="2023-01-01", end="2023-01-31", freq='D')
    benchmark_df = pd.DataFrame({"Close": [100.0]*len(benchmark_dates)}, index=benchmark_dates)
    
    trades = [
        TradeResult(
            symbol="T.NS", sector="S", signal_date=datetime.date(2023, 1, 5),
            entry_date=datetime.date(2023, 1, 6), exit_date=datetime.date(2023, 1, 15),
            exit_reason="hp", signal_score=70.0, entry_price=100.0, exit_price=105.0,
            return_pct=5.0, rsi_at_signal=0, adx_at_signal=0, ema_signal=""
        )
    ]
    
    # Logic from run_backtest:
    first_entry = min(t.entry_date for t in trades)
    config = BacktestConfig(date_from=None, date_to=None)
    
    effective_from = config.date_from or first_entry
    effective_to = config.date_to or datetime.date(2023, 1, 20) # Mocking today()
    
    sliced_bench = benchmark_df[
        (benchmark_df.index.date >= effective_from) &
        (benchmark_df.index.date <= effective_to)
    ]
    
    assert sliced_bench.index[0].date() == datetime.date(2023, 1, 6)
    assert sliced_bench.index[-1].date() == datetime.date(2023, 1, 20)

def test_total_vs_avg_return():
    """
    Verify total_return_pct vs avg_return_pct.
    Total Return % should depend on capital and position size.
    Avg Return % should be simple average of trade returns (cost-adjusted).
    """
    # starting_capital = 1,000,000
    # position_size = 100,000
    # 2 trades, each with 10% return
    # ROUND_TRIP_COST_PCT = 0.25
    # Cost-adjusted return = 9.75%
    # Total PnL = 9.75% of 100,000 + 9.75% of 100,000 = 9,750 + 9,750 = 19,500
    # Total Return % = 19,500 / 1,000,000 * 100 = 1.95%
    # Avg Return % = (9.75% + 9.75%) / 2 = 9.75%
    
    trades = [
        TradeResult(
            symbol="A.NS", sector="S", signal_date=datetime.date(2023,1,1),
            entry_date=datetime.date(2023,1,2), exit_date=datetime.date(2023,1,10),
            exit_reason="hp", signal_score=70.0, entry_price=100.0, exit_price=110.0,
            return_pct=10.0, rsi_at_signal=0, adx_at_signal=0, ema_signal=""
        ),
        TradeResult(
            symbol="B.NS", sector="S", signal_date=datetime.date(2023,1,1),
            entry_date=datetime.date(2023,1,2), exit_date=datetime.date(2023,1,10),
            exit_reason="hp", signal_score=70.0, entry_price=100.0, exit_price=110.0,
            return_pct=10.0, rsi_at_signal=0, adx_at_signal=0, ema_signal=""
        )
    ]
    
    config = BacktestConfig(starting_capital=1000000.0, position_size=100000.0)
    metrics = compute_metrics(trades, None, config)
    
    assert metrics['avg_return_pct'] == 9.75
    assert metrics['total_return_pct'] == 1.95

def test_sharpe_ratio_correctness():
    """Verify Sharpe ratio calculation for predictable high-growth and volatile curves."""
    benchmark_dates = pd.date_range(start="2023-01-01", periods=20, freq='D')
    benchmark_df = pd.DataFrame({"Close": [100.0]*20}, index=benchmark_dates)
    
    # Case 1: High constant returns (high Sharpe) - need variation for std > 0
    trades_up = []
    for i in range(1, 20):
        ret = 1.0 + (i * 0.01) # 1.01, 1.02, ... 1.19
        trades_up.append(TradeResult(
            symbol=f"T{i}.NS", sector="S", signal_date=benchmark_dates[0].date(),
            entry_date=benchmark_dates[0].date(), exit_date=benchmark_dates[i].date(),
            exit_reason="hp", signal_score=70.0, entry_price=100.0, 
            exit_price=100.0 * (1 + ret/100), return_pct=ret,
            rsi_at_signal=0, adx_at_signal=0, ema_signal=""
        ))
    
    config = BacktestConfig(starting_capital=10000.0, position_size=1000.0)
    metrics_up = compute_metrics(trades_up, benchmark_df, config)
    
    # Daily returns will be positive and consistent
    assert metrics_up['sharpe_ratio'] > 5.0

    # Case 2: Volatile returns alternating between +1% and -1% (low Sharpe)
    trades_vol = []
    for i in range(1, 20):
        ret = 1.0 if i % 2 != 0 else -1.0
        trades_vol.append(TradeResult(
            symbol=f"T{i}.NS", sector="S", signal_date=benchmark_dates[0].date(),
            entry_date=benchmark_dates[0].date(), exit_date=benchmark_dates[i].date(),
            exit_reason="hp", signal_score=70.0, entry_price=100.0, 
            exit_price=100.0 * (1 + ret/100), return_pct=ret,
            rsi_at_signal=0, adx_at_signal=0, ema_signal=""
        ))
        
    metrics_vol = compute_metrics(trades_vol, benchmark_df, config)
    # Mean is near 0, Sharpe should be low
    assert abs(metrics_vol['sharpe_ratio']) < 5.0
