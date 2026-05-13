import pandas as pd
import numpy as np
import pytest
from app.backtest.engine import score_series, BacktestConfig, simulate_trades, compute_metrics, TradeResult

def create_dummy_df(n=200):
    np.random.seed(42)
    dates = pd.date_range(start='2020-01-01', periods=n)
    # Create somewhat realistic trending data to avoid all NaNs/zeros
    close = 100 + np.cumsum(np.random.randn(n))
    df = pd.DataFrame({
        'Open': close * 0.99,
        'High': close * 1.01,
        'Low': close * 0.98,
        'Close': close,
        'Volume': np.random.uniform(1000, 5000, n)
    }, index=dates)
    return df

def test_score_series_returns_list():
    df = create_dummy_df(100)
    results = score_series(df)
    assert isinstance(results, list)
    # MIN_BARS = 60, so for 100 bars we expect 100 - 60 = 40 results
    assert len(results) == 40
    if len(results) > 0:
        first = results[0]
        assert "score" in first
        assert "is_bullish" in first
        assert "date" in first
        assert "rsi" in first
        assert "adx" in first
        assert "close" in first

def test_score_series_no_future_leak():
    # Use more bars to let indicators stabilize a bit
    df = create_dummy_df(300)
    results_full = score_series(df)
    
    # Take a point in the middle (e.g., index 150)
    # result index will be 150 - 60 = 90
    test_idx = 150
    result_idx = test_idx - 60
    expected_score_at_test = results_full[result_idx]['score']
    
    # Score truncated df (only up to test_idx)
    df_truncated = df.iloc[:test_idx+1]
    results_truncated = score_series(df_truncated)
    actual_score_at_test = results_truncated[-1]['score']
    
    # They should be identical if no future leak occurs
    # Note: EMA/RSI are recursive, but if the full history from start is present in both, 
    # they should be identical.
    assert abs(expected_score_at_test - actual_score_at_test) < 1e-6

def test_score_series_with_fundamentals():
    class MockFundCache:
        def __init__(self):
            self.roe = 0.20
            self.roce = 0.20
            self.de_ratio = 0.1
            self.pe = 15
            self.pledged = 0
            
    fund_cache = MockFundCache()
    # Mocking calculate_fundamental_score behavior:
    # ROE > 15% -> 5pts
    # ROCE > 15% -> 5pts
    # DE < 0.5 -> 5pts
    # (PE and Pledged need to be in an info dict or handled by cache)
    
    # Wait, looking at scorer.py:
    # pe = to_float(info.get('forwardPE') or info.get('trailingPE'))
    # pledged = to_float(info.get('pledgedPercent'))
    
    # So pe and pledged are ONLY from info.
    
    config = BacktestConfig(include_fundamentals=True)
    # Use trending data to avoid hard filters (RSI > 70, ADX < 20, etc.)
    dates = pd.date_range(start='2020-01-01', periods=200)
    close = np.linspace(100, 200, 200)
    df = pd.DataFrame({
        'Open': close * 0.99,
        'High': close * 1.01,
        'Low': close * 0.98,
        'Close': close,
        'Volume': [5000] * 200
    }, index=dates)
    
    # results = score_series(df, fund_cache=fund_cache, config=config)
    # calculate_fundamental_score(None, fund_cache=fund_cache) will be called.
    # It will get roe, roce, de from fund_cache.
    # It will get pe, pledged from None (info), which results in 0.
    # So fund_score should be 5+5+5 = 15.
    
    results = score_series(df, fund_cache=fund_cache, config=config)
    
    # Check if scores are higher than default
    results_no_fund = score_series(df)
    
    for r_fund, r_no_fund in zip(results, results_no_fund):
        # Only check where filters didn't trigger
        if r_fund['score'] > 0:
            assert r_fund['score'] == r_no_fund['score'] + 15.0

def test_score_series_min_bars():
    df = create_dummy_df(50)
    results = score_series(df)
    assert len(results) == 0

def test_simulate_trades_entry_is_next_day_open():
    df = create_dummy_df(100)
    # Force a signal at index 60
    scored_dates = [{
        "date": df.index[60],
        "score": 100.0,
        "rsi": 50.0,
        "adx": 20.0,
        "ema_signal": "bullish"
    }]
    config = BacktestConfig(score_threshold=80.0, holding_days=5)
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)
    
    assert len(trades) == 1
    trade = trades[0]
    assert trade.signal_date == df.index[60].date()
    assert trade.entry_date == df.index[61].date()
    assert trade.entry_price == float(df.iloc[61]['Open'])

def test_simulate_trades_stop_loss_triggered():
    df = create_dummy_df(100)
    # Ensure a massive drop after entry to trigger SL
    # Entry will be at index 61
    df.iloc[62, df.columns.get_loc('Low')] = 50.0 # Huge drop
    
    scored_dates = [{
        "date": df.index[60],
        "score": 100.0,
        "rsi": 50.0,
        "adx": 20.0,
        "ema_signal": "bullish"
    }]
    config = BacktestConfig(score_threshold=80.0, holding_days=10, stop_loss_pct=5.0)
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)
    
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == 'stop_loss'
    assert trade.return_pct <= -5.0

def test_simulate_trades_target_triggered():
    df = create_dummy_df(100)
    # Ensure a massive rise after entry to trigger Target
    # Entry will be at index 61
    df.iloc[62, df.columns.get_loc('High')] = 200.0 # Huge rise
    
    scored_dates = [{
        "date": df.index[60],
        "score": 100.0,
        "rsi": 50.0,
        "adx": 20.0,
        "ema_signal": "bullish"
    }]
    config = BacktestConfig(score_threshold=80.0, holding_days=10, target_pct=10.0)
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)
    
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == 'target'
    assert trade.return_pct >= 10.0

def test_simulate_trades_date_filters():
    df = create_dummy_df(100)
    # 3 signals at different dates
    scored_dates = [
        {"date": df.index[60], "score": 100.0, "rsi": 50, "adx": 20, "ema_signal": "bullish"},
        {"date": df.index[70], "score": 100.0, "rsi": 50, "adx": 20, "ema_signal": "bullish"},
        {"date": df.index[80], "score": 100.0, "rsi": 50, "adx": 20, "ema_signal": "bullish"}
    ]
    
    # Filter for middle signal only
    config = BacktestConfig(
        score_threshold=80.0, 
        date_from=df.index[65].date(),
        date_to=df.index[75].date()
    )
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)
    
    assert len(trades) == 1
    assert trades[0].signal_date == df.index[70].date()

def test_compute_metrics_all_winners():
    trades = [
        TradeResult(
            symbol="T1.NS", sector="S1", signal_date=None, entry_date=None, 
            exit_date=pd.Timestamp('2020-01-10').date(), exit_reason='target',
            signal_score=90.0, entry_price=100.0, exit_price=110.0, return_pct=10.0,
            rsi_at_signal=0, adx_at_signal=0, ema_signal=""
        ),
        TradeResult(
            symbol="T2.NS", sector="S2", signal_date=None, entry_date=None, 
            exit_date=pd.Timestamp('2020-01-15').date(), exit_reason='holding_period',
            signal_score=85.0, entry_price=100.0, exit_price=105.0, return_pct=5.0,
            rsi_at_signal=0, adx_at_signal=0, ema_signal=""
        )
    ]
    benchmark_df = pd.DataFrame({
        'Close': [10000, 10100, 10200]
    }, index=pd.to_datetime(['2020-01-10', '2020-01-15', '2020-01-20']))
    
    config = BacktestConfig(starting_capital=20000.0, position_size=10000.0)
    metrics = compute_metrics(trades, benchmark_df, config)
    
    assert metrics['total_trades'] == 2
    assert metrics['winning_trades'] == 2
    assert metrics['win_rate'] == 1.0  # Scale 0-1
    assert metrics['avg_return_pct'] == 7.5
    assert metrics['total_return_pct'] == 7.5 # (1500 / 20000) * 100 = 7.5
    assert len(metrics['equity_curve']) == 3
    # Initial capital = 2 * 10000 = 20000
    # First point: date 2020-01-10, cumulative PL = +1000 (10% of 10000)
    assert metrics['equity_curve'][0]['equity'] == 21000.0

def test_backtest_config_new_defaults():
    config = BacktestConfig()
    assert config.trailing_stop_pct == 0.0
    assert config.require_volume_breakout is False
    assert config.use_regime_filter is True

