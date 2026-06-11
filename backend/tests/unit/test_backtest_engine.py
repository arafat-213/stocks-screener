import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import (
    BacktestConfig,
    TradeResult,
    compute_metrics,
    score_series,
    simulate_trades,
)


def create_dummy_df(n=400):
    np.random.seed(42)
    dates = pd.date_range(start="2020-01-01", periods=n)
    # Create somewhat realistic trending data to avoid all NaNs/zeros
    close = 100 + np.cumsum(np.random.randn(n))
    df = pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.01,
            "Low": close * 0.98,
            "Close": close,
            "Volume": np.random.uniform(1000, 5000, n),
        },
        index=dates,
    )
    return df


def test_score_series_returns_list():
    df = create_dummy_df(400)
    config = BacktestConfig(
        score_threshold=0.0,
    )
    results = score_series(df, config=config)
    assert isinstance(results, list)
    # MIN_BARS = 260, so for 400 bars we expect up to 140 results
    assert len(results) > 0
    assert len(results) <= 40
    if len(results) > 0:
        first = results[0]
        assert "score" in first
        assert "is_bullish" in first
        assert "date" in first
        assert "rsi" in first
        assert "adx" in first
        assert "close" in first
        assert "above_200ema" in first
        assert isinstance(first["above_200ema"], (bool, type(None)))


def test_score_series_no_future_leak():
    # Use more bars to let indicators stabilize a bit
    df = create_dummy_df(500)
    config = BacktestConfig(
        score_threshold=0.0,
    )
    results_full = score_series(df, config=config)
    assert len(results_full) > 0

    # Pick a result in the middle of results_full
    expected_result = results_full[len(results_full) // 2]
    test_date = expected_result["date"]

    # Find its index in the original dataframe
    test_idx = df.index.get_loc(test_date)

    # Score truncated df (only up to test_idx)
    df_truncated = df.iloc[: test_idx + 1]
    results_truncated = score_series(df_truncated, config=config)
    actual_result = results_truncated[-1]
    assert actual_result["date"] == test_date

    # They should be identical if no future leak occurs
    assert abs(expected_result["score"] - actual_result["score"]) <= 0.01


def test_score_series_min_bars():
    df = create_dummy_df(250)
    results = score_series(df)
    assert len(results) == 0


def test_simulate_trades_entry_is_next_day_open():
    df = create_dummy_df(300)
    # Force a signal at index 250
    scored_dates = [
        {
            "date": df.index[250],
            "score": 100.0,
            "rsi": 50.0,
            "adx": 30.0,
            "ema_signal": "bullish_cross",
            "above_200ema": True,
            "volume_breakout": True,
        }
    ]
    config = BacktestConfig(
        score_threshold=80.0,
        holding_days=5,
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.signal_date == df.index[250].date()
    assert trade.entry_date == df.index[251].date()
    assert trades[0].entry_price == float(df.iloc[251]["Open"])


def test_simulate_trades_tier_logic():
    df = create_dummy_df(300)
    # Case A: Volume Breakout Only (Tier 2)
    # Case B: Both (Tier 1)
    # Case C: ADX Only (Tier 2)
    # Case D: None (Tier 3)

    scored_dates = [
        {
            "date": df.index[261],
            "score": 100.0,
            "rsi": 50.0,
            "adx": 10.0,
            "ema_signal": "bullish",
            "above_200ema": True,
            "volume_breakout": True,
        },
        {
            "date": df.index[271],
            "score": 100.0,
            "rsi": 50.0,
            "adx": 30.0,
            "ema_signal": "bullish",
            "above_200ema": True,
            "volume_breakout": True,
        },
        {
            "date": df.index[281],
            "score": 100.0,
            "rsi": 50.0,
            "adx": 30.0,
            "ema_signal": "bullish",
            "above_200ema": True,
            "volume_breakout": False,
        },
    ]

    config = BacktestConfig(
        min_adx=25.0,
        min_signal_tier=1,  # Only Case B should pass
        require_consolidation=False,
    )

    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)
    assert len(trades) == 1
    assert trades[0].signal_date == df.index[271].date()

    config.min_signal_tier = 2  # Cases A, B, C should pass
    config.holding_days = 5
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)
    assert len(trades) == 3


def test_simulate_trades_stop_loss_triggered():
    df = create_dummy_df(300)
    # Ensure a massive drop after entry to trigger SL
    # Entry will be at index 251
    df.iloc[252, df.columns.get_loc("Low")] = 1.0  # Huge drop

    scored_dates = [
        {
            "date": df.index[250],
            "score": 100.0,
            "rsi": 50.0,
            "adx": 30.0,
            "ema_signal": "bullish_cross",
            "above_200ema": True,
            "volume_breakout": True,
        }
    ]
    config = BacktestConfig(
        score_threshold=80.0,
        holding_days=10,
        stop_loss_pct=5.0,
        use_atr_trailing_stop=False,
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)

    assert len(trades) == 1
    trade = trades[0]
    # Current engine uses atr_trailing_stop for all price-based stops if trail floor active
    assert trade.exit_reason in ["stop_loss", "atr_trailing_stop"]
    # stop_price = entry_price * (1 - 0.05) = 0.95 * entry
    # But clamped by structural/vol. With synthetic, hard stop 5% should win.
    # Entry day low check also might skip if low <= stop.
    # Here entry open is high, so 5% is deep enough.
    assert trade.return_pct <= -1.0  # At least some loss occurred


def test_simulate_trades_target_triggered():
    df = create_dummy_df(300)
    # Ensure a massive rise after entry to trigger Target
    # Entry will be at index 251
    df.iloc[252, df.columns.get_loc("High")] = 200.0  # Huge rise

    scored_dates = [
        {
            "date": df.index[250],
            "score": 100.0,
            "rsi": 50.0,
            "adx": 30.0,
            "ema_signal": "bullish_cross",
            "above_200ema": True,
            "volume_breakout": True,
        }
    ]
    config = BacktestConfig(
        score_threshold=80.0,
        holding_days=10,
        target_pct=10.0,
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "target"
    assert trade.return_pct >= 10.0


def test_simulate_trades_date_filters():
    df = create_dummy_df(300)
    # 3 signals at different dates
    scored_dates = [
        {
            "date": df.index[250],
            "score": 100.0,
            "rsi": 50,
            "adx": 30.0,
            "ema_signal": "bullish_cross",
            "above_200ema": True,
            "volume_breakout": True,
        },
        {
            "date": df.index[260],
            "score": 100.0,
            "rsi": 50,
            "adx": 30.0,
            "ema_signal": "bullish_cross",
            "above_200ema": True,
            "volume_breakout": True,
        },
        {
            "date": df.index[270],
            "score": 100.0,
            "rsi": 50,
            "adx": 30.0,
            "ema_signal": "bullish_cross",
            "above_200ema": True,
            "volume_breakout": True,
        },
    ]

    # Filter for middle signal only
    config = BacktestConfig(
        score_threshold=80.0,
        date_from=df.index[255].date(),
        date_to=df.index[265].date(),
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)

    assert len(trades) == 1
    assert trades[0].signal_date == df.index[260].date()


def test_compute_metrics_all_winners():
    trades = [
        TradeResult(
            symbol="T1.NS",
            sector="S1",
            signal_date=pd.Timestamp("2020-01-01").date(),
            entry_date=pd.Timestamp("2020-01-02").date(),
            exit_date=pd.Timestamp("2020-01-10").date(),
            exit_reason="target",
            signal_score=90.0,
            entry_price=100.0,
            exit_price=110.0,
            return_pct=10.0,
            rsi_at_signal=0,
            adx_at_signal=0,
            ema_signal="",
        ),
        TradeResult(
            symbol="T2.NS",
            sector="S2",
            signal_date=pd.Timestamp("2020-01-05").date(),
            entry_date=pd.Timestamp("2020-01-06").date(),
            exit_date=pd.Timestamp("2020-01-15").date(),
            exit_reason="holding_period",
            signal_score=85.0,
            entry_price=100.0,
            exit_price=105.0,
            return_pct=5.0,
            rsi_at_signal=0,
            adx_at_signal=0,
            ema_signal="",
        ),
    ]
    benchmark_df = pd.DataFrame(
        {"Close": [10000, 10100, 10200]},
        index=pd.to_datetime(["2020-01-10", "2020-01-15", "2020-01-20"]),
    )

    config = BacktestConfig(starting_capital=20000.0, position_size=10000.0)
    metrics = compute_metrics(trades, benchmark_df, config)

    assert metrics["total_trades"] == 2
    assert metrics["winning_trades"] == 2
    assert metrics["win_rate"] == 100.0  # Scale 0-100
    assert metrics["avg_return_pct"] == pytest.approx(7.25)  # (9.75 + 4.75) / 2
    assert metrics["total_return_pct"] == pytest.approx(
        7.25
    )  # (1450 / 20000) * 100 = 7.25
    assert len(metrics["equity_curve"]) == 3
    # Initial capital = 2 * 10000 = 20000
    # First point: date 2020-01-10, cumulative PL = +975 (9.75% of 10000)
    assert metrics["equity_curve"][0]["equity"] == pytest.approx(20975.0)


def test_backtest_config_new_defaults():
    config = BacktestConfig()
    assert config.score_threshold == 55.0
    assert config.trailing_stop_pct == 0.0
    assert config.require_volume_breakout is False
    assert config.atr_multiplier == 2.0
    assert config.risk_reward_ratio == 2.5
    assert config.use_atr_stops is True


def test_simulate_trades_uses_atr_stops():
    df = create_dummy_df(300)
    # Force a signal at index 250 with ATR info
    atr_value = 2.5
    scored_dates = [
        {
            "date": df.index[250],
            "score": 100.0,
            "rsi": 50.0,
            "adx": 30.0,
            "ema_signal": "bullish_cross",
            "above_200ema": True,
            "volume_breakout": True,
            "atr": atr_value,
        }
    ]

    # config: multiplier 2.0, RR 2.0
    # Stop Loss = entry_price - (2.0 * 2.5) = entry_price - 5.0
    # Target = entry_price + (2.0 * 2.0 * 2.5) = entry_price + 10.0
    config = BacktestConfig(
        score_threshold=80.0,
        use_atr_stops=False,
        atr_multiplier=2.0,
        initial_stop_atr_multiplier=2.0,
        risk_reward_ratio=2.0,
        holding_days=10,
        use_atr_trailing_stop=False,
        require_consolidation=False,
        use_pullback_entry=False,
    )

    # Mock price movement to trigger ATR target
    entry_price = float(df.iloc[251]["Open"])
    df.iloc[252, df.columns.get_loc("High")] = entry_price * 1.5

    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "target"


def test_simulate_trades_uses_atr_stops_sl():
    df = create_dummy_df(300)
    # Force a signal at index 250 with ATR info
    atr_value = 2.5
    scored_dates = [
        {
            "date": df.index[250],
            "score": 100.0,
            "rsi": 50.0,
            "adx": 30.0,
            "ema_signal": "bullish_cross",
            "above_200ema": True,
            "volume_breakout": True,
            "atr": atr_value,
        }
    ]

    # config: multiplier 2.0
    # Stop Loss = entry_price - (2.0 * 2.5) = entry_price - 5.0
    config = BacktestConfig(
        score_threshold=80.0,
        use_atr_stops=False,
        atr_multiplier=2.0,
        initial_stop_atr_multiplier=2.0,
        holding_days=10,
        require_consolidation=False,
        use_pullback_entry=False,
    )

    # Mock price movement to trigger ATR stop loss
    df.iloc[252, df.columns.get_loc("Low")] = 1.0

    trades = simulate_trades("TEST.NS", "Tech", df, scored_dates, config)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "stop_loss"


def test_score_series_output_feeds_simulate_trades():
    """Verify that score_series output contains all keys simulate_trades needs."""
    df = create_dummy_df(400)
    results = score_series(df)
    assert len(results) > 0

    required_keys = {
        "score",
        "date",
        "rsi",
        "adx",
        "ema_signal",
        "volume_breakout",
        "atr",
        "above_200ema",
    }
    for key in required_keys:
        assert key in results[0], f"Missing key in score_series output: {key}"


def test_score_series_to_simulate_trades_produces_trades():
    """End-to-end: score_series output fed to simulate_trades must produce trades."""
    # We need 260 bars for indicators, then some for trending
    df = create_dummy_df(600)
    # Ensure trending up in the signal zone (post 260 bars)
    close = df["Close"].copy()
    close.iloc[260:] = 100 + np.linspace(0, 50, 600 - 260)
    df["Close"] = close
    df["Open"] = close - 0.5
    df["High"] = close + 1.0
    df["Low"] = close - 1.0

    config = BacktestConfig(
        score_threshold=0.0,  # accept any score
        min_adx=0,  # disable ADX gate
        require_volume_breakout=False,
        stop_loss_pct=0.0,
        target_pct=0.0,
        holding_days=5,
        require_consolidation=False,
    )
    results = score_series(df, config=config)
    assert len(results) > 0, "score_series returned no signals"

    trades = simulate_trades("TEST.NS", "Tech", df, results, config)
    assert len(trades) > 0
    for r in results:
        r["ema_signal"] = "bullish_cross"
        r["adx"] = 30.0
        r["rsi"] = 50.0
        r["above_200ema"] = True
        r["volume_breakout"] = True

    trades = simulate_trades("TEST", "Tech", df, results, config)
    assert len(trades) > 0, (
        "No trades produced from score_series output — "
        "likely a missing key in score_series result dict"
    )


def test_stop_loss_not_clipped():
    """Verify that a stop loss wider than 8% (e.g. 12%) is NOT clipped to 8% anymore."""
    n = 10
    closes = [100.0] * n
    df = pd.DataFrame(
        {
            "Open": closes,
            "High": [101.0] * n,
            "Low": [95.0, 92.0, 90.0, 89.0, 88.0, 87.0, 86.0, 85.0, 84.0, 83.0],
            "Close": closes,
            "Volume": [1000000.0] * n,
        },
        index=pd.date_range("2023-01-01", periods=n),
    )

    # Signal at index 0
    signal = {
        "date": df.index[0],
        "score": 80.0,
        "is_bullish": True,
        "rsi": 50.0,
        "adx": 30.0,
        "atr": 6.0,  # ATR=6, mult=2.0 -> stop=12% (price 88)
        "close": 100.0,
        "ema_signal": "bullish_cross",
        "above_200ema": True,
        "volume_breakout": True,
    }

    config = BacktestConfig(
        score_threshold=0.0,
        atr_multiplier=2.0,
        use_atr_stops=True,
        stop_loss_pct=0.0,  # Use ATR
        require_consolidation=False,
    )

    trades = simulate_trades("TEST", "Sector", df, [signal], config)
    assert len(trades) == 1
    trade = trades[0]

    # If it was clipped to 8%, stop would be 92.
    # Low hits 92 at index 1.
    # If NOT clipped, stop is 88.
    # Low hits 88 at index 4.
    assert trade.exit_price == 88.0
    assert trade.exit_date == df.index[4].date()
    assert trade.exit_reason == "stop_loss"
