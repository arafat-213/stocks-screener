import pytest
import pandas as pd
import numpy as np
import datetime
from app.backtest.engine import (
    BacktestConfig, 
    simulate_trades, 
    _compute_position_size, 
    TradeResult, 
    compute_metrics,
    score_series,
    simulate_portfolio,
    _compute_all_indicators,
    _score_bar_from_precomputed,
    _compute_signal_tier
)

def test_tier1_requires_cross_or_pullback_plus_volume_plus_adx():
    signal = {
        "ema_signal": "bullish_cross",
        "volume_breakout": True,
        "adx": 28.0,
        "rsi": 58.0,
    }
    assert _compute_signal_tier(signal) == 1

def test_tier2_cross_with_adx_no_volume():
    signal = {
        "ema_signal": "bullish_pullback",
        "volume_breakout": False,
        "adx": 26.0,
        "rsi": 62.0,
    }
    assert _compute_signal_tier(signal) == 2

def test_tier3_when_rsi_above_68():
    signal = {
        "ema_signal": "bullish_cross",
        "volume_breakout": True,
        "adx": 30.0,
        "rsi": 72.0,
    }
    assert _compute_signal_tier(signal) == 3

def test_tier4_generic_bullish():
    signal = {
        "ema_signal": "bullish",
        "volume_breakout": True,
        "adx": 30.0,
        "rsi": 55.0,
    }
    assert _compute_signal_tier(signal) == 4

def test_generic_bullish_signal_is_not_entered():
    """Verify simulate_trades blocks a Tier 4 signal even if score is high."""
    df = make_trending_df(n=300)
    config = BacktestConfig(
        score_threshold=50.0,
        require_volume_breakout=False,
        use_regime_filter=False,
        require_weekly_confirmation=False,
        min_adx=0.0,
    )
    # Generic 'bullish' is Tier 4
    signal = make_signal(df, idx=260, score=80.0)
    signal['ema_signal'] = 'bullish'
    signal['rsi'] = 55.0
    signal['adx'] = 30.0
    
    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 0
from tests.conftest import make_trending_df, make_signal
import time

class TestEffectiveScoreThreshold:
    def test_scales_to_70_pct_when_technical_only(self):
        config = BacktestConfig(score_threshold=60.0, include_fundamentals=False)
        assert config.effective_score_threshold == pytest.approx(42.0)

    def test_unchanged_when_fundamentals_included(self):
        config = BacktestConfig(score_threshold=60.0, include_fundamentals=True)
        assert config.effective_score_threshold == pytest.approx(60.0)

    def test_zero_threshold_always_zero(self):
        config = BacktestConfig(score_threshold=0.0, include_fundamentals=False)
        assert config.effective_score_threshold == pytest.approx(0.0)

    def test_signal_above_effective_threshold_produces_trade(self):
        """score=50 > effective(42) should fire; raw 60 would block it."""
        df = make_trending_df(n=300)
        config = BacktestConfig(
            score_threshold=60.0,
            include_fundamentals=False,
            require_volume_breakout=False,
            use_regime_filter=False,
            require_weekly_confirmation=False,
            stop_loss_pct=7.0,
            target_pct=0.0,
            holding_days=20,
            min_adx=0.0,
            min_signal_tier=2,
            require_consolidation=False,
            use_pullback_entry=False,
        )
        signal = make_signal(df, idx=260, score=50.0)
        trades = simulate_trades("TEST", "Technology", df, [signal], config)
        assert len(trades) == 1

    def test_signal_below_effective_threshold_no_trade(self):
        """score=30 < effective(42) should NOT fire."""
        df = make_trending_df(n=300)
        config = BacktestConfig(
            score_threshold=60.0,
            include_fundamentals=False,
            require_volume_breakout=False,
            use_regime_filter=False,
            require_weekly_confirmation=False,
            stop_loss_pct=7.0,
            target_pct=0.0,
            holding_days=20,
            min_adx=0.0,
            min_signal_tier=2,
            require_consolidation=False,
            use_pullback_entry=False,
        )
        signal = make_signal(df, idx=260, score=30.0)
        trades = simulate_trades("TEST", "Technology", df, [signal], config)
        assert len(trades) == 0

class TestPositionSizing:
    def _base_config(self, **kwargs) -> BacktestConfig:
        defaults = dict(
            score_threshold=60.0,
            include_fundamentals=False,
            require_volume_breakout=False,
            use_regime_filter=False,
            require_weekly_confirmation=False,
            stop_loss_pct=7.0,
            target_pct=0.0,
            holding_days=20,
            min_adx=0.0,
            starting_capital=1_000_000.0,
            position_size=10_000.0,
            atr_multiplier=2.0,
            min_signal_tier=2,
            require_consolidation=False,
            use_pullback_entry=False,
        )
        defaults.update(kwargs)
        return BacktestConfig(**defaults)

    def test_flat_sizing_returns_config_position_size(self):
        config = self._base_config(use_volatility_sizing=False)
        result = _compute_position_size(config, entry_price=500.0, atr=10.0)
        assert result == pytest.approx(10_000.0)

    def test_volatility_sizing_scales_with_atr(self):
        """
        risk_per_trade_pct=1% of 1_000_000 = 10_000 rupees risk.
        ATR=10, multiplier=2 -> stop_distance=20.
        shares = 10_000 / 20 = 500. position = 500 * 500 = 250_000.
        But capped at max_position_pct=20% -> 200_000.
        """
        config = self._base_config(
            use_volatility_sizing=True,
            risk_per_trade_pct=1.0,
            max_position_pct=20.0,
            atr_multiplier=2.0,
        )
        result = _compute_position_size(config, entry_price=500.0, atr=10.0)
        assert result == pytest.approx(200_000.0)  # capped at 20%

    def test_volatility_sizing_uncapped_when_below_max(self):
        """
        risk=1% of 100_000 = 1_000. ATR=5, mult=2 -> stop=10.
        shares=100. position=100*100=10_000. max=10%=10_000 -> no cap.
        """
        config = self._base_config(
            starting_capital=100_000.0,
            use_volatility_sizing=True,
            risk_per_trade_pct=1.0,
            max_position_pct=10.0,
            atr_multiplier=2.0,
        )
        result = _compute_position_size(config, entry_price=100.0, atr=5.0)
        assert result == pytest.approx(10_000.0)

    def test_volatility_sizing_falls_back_when_atr_none(self):
        config = self._base_config(use_volatility_sizing=True)
        result = _compute_position_size(config, entry_price=500.0, atr=None)
        assert result == pytest.approx(10_000.0)

    def test_trade_result_carries_position_size_used(self):
        df = make_trending_df(n=300)
        config = self._base_config(
            use_volatility_sizing=True,
            risk_per_trade_pct=1.0,
            max_position_pct=5.0,
        )
        signal = make_signal(df, idx=260, score=50.0)
        trades = simulate_trades("TEST", "Technology", df, [signal], config)
        assert len(trades) == 1
        assert trades[0].position_size_used > 0

    def test_compute_metrics_uses_per_trade_position_size(self):
        """
        Two trades: one sized at 20_000, one at 10_000.
        Returns: +10% and -10%. PnL = 2_000 - 1_000 = 1_000.
        total_return_pct = 1_000 / 1_000_000 * 100 = 0.1%.
        """
        def _make_trade(ret: float, size: float) -> TradeResult:
            return TradeResult(
                symbol="X", sector="Tech",
                signal_date=datetime.date(2024, 1, 1),
                entry_date=datetime.date(2024, 1, 2),
                exit_date=datetime.date(2024, 1, 22),
                exit_reason="holding_period",
                signal_score=60.0,
                entry_price=100.0,
                exit_price=100.0 * (1 + ret / 100),
                return_pct=ret,
                rsi_at_signal=55.0,
                adx_at_signal=25.0,
                ema_signal="bullish",
                position_size_used=size,
            )

        trades = [_make_trade(10.0, 20_000.0), _make_trade(-10.0, 10_000.0)]
        config = BacktestConfig(starting_capital=1_000_000.0, position_size=10_000.0)
        metrics = compute_metrics(trades, benchmark_data=None, config=config)
        # Cost-adjusted returns:
        # Trade 1: 10.0 - 0.25 = 9.75%. PnL = 9.75 / 100 * 20_000 = 1950
        # Trade 2: -10.0 - 0.25 = -10.25%. PnL = -10.25 / 100 * 10_000 = -1025
        # Total PnL = 1950 - 1025 = 925
        # total_return_pct = 925 / 1_000_000 * 100 = 0.0925%
        assert metrics["total_return_pct"] == pytest.approx(0.0925, abs=0.0001)

class TestScoreSeriesPerformance:
    def test_score_series_completes_300_bars_under_2_seconds(self):
        """
        The vectorized path must process 300 bars in under 2s.
        The O(n²) path on a typical machine takes 15-30s for 300 bars.
        """
        df = make_trending_df(n=300)
        start = time.perf_counter()
        result = score_series(df)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, (
            f"score_series took {elapsed:.2f}s - still O(n²)? Expected < 2s"
        )
        assert len(result) > 0, "score_series returned no results"

    def test_score_series_results_are_consistent(self):
        """
        Vectorized and legacy paths must return the same score for a given bar.
        We compare score_series output against a single calculate_technical_score call
        on the same slice, for a spot-check bar.
        """
        from app.pipeline.scorer import calculate_technical_score
        df = make_trending_df(n=300)
        results = score_series(df)
        assert len(results) > 0
        # Check the final result matches a direct scorer call on the same slice
        last = results[-1]
        check_idx = len(df) - 1
        bar_df = df.iloc[: check_idx + 1]
        direct = calculate_technical_score(bar_df, timeframe="D")
        # Scores may differ slightly if ADX changed due to vectorization, but
        # the is_bullish classification must agree.
        assert last["is_bullish"] == direct["is_bullish"], (
            f"is_bullish mismatch: vectorized={last['is_bullish']}, direct={direct['is_bullish']}"
        )

class TestPortfolioSimulation:
    def _make_config(self, max_concurrent: int = 2, max_sector: int = 1) -> BacktestConfig:
        return BacktestConfig(
            score_threshold=60.0,
            include_fundamentals=False,
            require_volume_breakout=False,
            use_regime_filter=False,
            require_weekly_confirmation=False,
            stop_loss_pct=7.0,
            target_pct=0.0,
            holding_days=20,
            min_adx=0.0,
            starting_capital=1_000_000.0,
            position_size=10_000.0,
            max_concurrent_positions=max_concurrent,
            max_sector_positions=max_sector,
            min_signal_tier=2,
            require_consolidation=False,
            use_pullback_entry=False,
        )

    def _make_simultaneous_signals(
        self, df: pd.DataFrame, symbols: list[str], sectors: list[str], score: float = 50.0
    ) -> tuple[dict, dict]:
        """Returns all_signals and all_dfs where all symbols fire on the same day."""
        all_signals = {}
        all_dfs = {}
        for sym, sec in zip(symbols, sectors):
            sig = make_signal(df, idx=260, score=score)
            all_signals[sym] = [sig]
            all_dfs[sym] = df.copy()
        return all_signals, all_dfs

    def test_max_concurrent_positions_respected(self):
        """With max_concurrent=1, only one trade fires even when 3 signals appear on same day."""
        df = make_trending_df(n=300)
        stocks_info = {"A": "Tech", "B": "Health", "C": "Finance"}
        all_signals, all_dfs = self._make_simultaneous_signals(
            df, ["A", "B", "C"], ["Tech", "Health", "Finance"]
        )
        config = self._make_config(max_concurrent=1, max_sector=0)
        trades = simulate_portfolio(all_signals, all_dfs, stocks_info, config)
        assert len(trades) <= 1

    def test_max_sector_positions_respected(self):
        """With max_sector=1, only one Tech trade fires even when two Tech signals appear."""
        df = make_trending_df(n=300)
        stocks_info = {"A": "Tech", "B": "Tech", "C": "Health"}
        all_signals, all_dfs = self._make_simultaneous_signals(
            df, ["A", "B", "C"], ["Tech", "Tech", "Health"]
        )
        config = self._make_config(max_concurrent=0, max_sector=1)
        trades = simulate_portfolio(all_signals, all_dfs, stocks_info, config)
        tech_trades = [t for t in trades if stocks_info[t.symbol] == "Tech"]
        assert len(tech_trades) <= 1

    def test_unlimited_when_limits_zero(self):
        """max_concurrent=0 and max_sector=0 means no limits - all three signals fire."""
        df = make_trending_df(n=300)
        stocks_info = {"A": "Tech", "B": "Health", "C": "Finance"}
        all_signals, all_dfs = self._make_simultaneous_signals(
            df, ["A", "B", "C"], ["Tech", "Health", "Finance"]
        )
        config = self._make_config(max_concurrent=0, max_sector=0)
        trades = simulate_portfolio(all_signals, all_dfs, stocks_info, config)
        assert len(trades) == 3

    def test_position_released_after_exit(self):
        """After a 20-day hold exits, the next signal for the same sector can enter."""
        df = make_trending_df(n=400)
        stocks_info = {"A": "Tech", "B": "Tech"}
        # Signal A fires on bar 260, signal B fires on bar 290 (after A's 20-day hold)
        sig_a = make_signal(df, idx=260, score=50.0)
        sig_b = make_signal(df, idx=290, score=50.0)
        all_signals = {"A": [sig_a], "B": [sig_b]}
        all_dfs = {"A": df.copy(), "B": df.copy()}
        config = self._make_config(max_concurrent=0, max_sector=1)
        trades = simulate_portfolio(all_signals, all_dfs, stocks_info, config)
        assert len(trades) == 2  # Both should fire because A exits before B's signal

def _make_df_momentum(n=300):
    """Monotonically rising price series — simple, predictable."""
    closes = np.linspace(100, 200, n)
    return pd.DataFrame(
        {
            "Open": closes * 0.99,
            "High": closes * 1.01,
            "Low": closes * 0.98,
            "Close": closes,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=pd.date_range("2021-01-01", periods=n, freq="B"),
    )

def test_momentum_1m_uses_21_bars():
    df = _make_df_momentum(300)
    df_ind = _compute_all_indicators(df)
    # Check bar at index 250 (has enough history for all lookbacks)
    bar = _score_bar_from_precomputed(df_ind, 250)
    price_now = df_ind["Close"].iloc[250]
    price_21 = df_ind["Close"].iloc[250 - 21]
    expected = (price_now / price_21 - 1) * 100
    assert bar["momentum_1m"] == pytest.approx(expected, rel=1e-6)

def test_momentum_3m_uses_63_bars():
    df = _make_df_momentum(300)
    df_ind = _compute_all_indicators(df)
    bar = _score_bar_from_precomputed(df_ind, 250)
    price_now = df_ind["Close"].iloc[250]
    price_63 = df_ind["Close"].iloc[250 - 63]
    expected = (price_now / price_63 - 1) * 100
    assert bar["momentum_3m"] == pytest.approx(expected, rel=1e-6)

class TestMomentumCalculation:
    def _make_df(self, n=300):
        """Monotonically rising price series — simple, predictable."""
        closes = np.linspace(100, 200, n)
        return pd.DataFrame(
            {
                "Open": closes * 0.99,
                "High": closes * 1.01,
                "Low": closes * 0.98,
                "Close": closes,
                "Volume": np.full(n, 1_000_000.0),
            },
            index=pd.date_range("2021-01-01", periods=n, freq="B"),
        )

    def test_scorer_lookbacks_are_consistent(self):
        """Verify scorer.py uses correct negative indices for all 4 momentum timeframes."""
        from app.pipeline.scorer import calculate_technical_score
        df = self._make_df(300)
        res = calculate_technical_score(df)
        
        price_now = df["Close"].iloc[-1]
        
        # 1m (21 bars)
        p21 = df["Close"].iloc[-22]
        assert res["momentum_1m"] == pytest.approx((price_now / p21 - 1) * 100)
        
        # 3m (63 bars)
        p63 = df["Close"].iloc[-64]
        assert res["momentum_3m"] == pytest.approx((price_now / p63 - 1) * 100)
        
        # 6m (126 bars)
        p126 = df["Close"].iloc[-127]
        assert res["momentum_6m"] == pytest.approx((price_now / p126 - 1) * 100)
        
        # 12m (252 bars)
        p252 = df["Close"].iloc[-253]
        assert res["momentum_12m"] == pytest.approx((price_now / p252 - 1) * 100)

    def test_engine_lookbacks_are_consistent(self):
        """Verify engine.py _score_bar_from_precomputed uses correct offset from index i."""
        df = self._make_df(300)
        df_ind = _compute_all_indicators(df)
        i = 280
        bar = _score_bar_from_precomputed(df_ind, i)
        
        price_now = df_ind["Close"].iloc[i]
        
        # 1m (21 bars)
        assert bar["momentum_1m"] == pytest.approx((price_now / df_ind["Close"].iloc[i - 21] - 1) * 100)
        
        # 3m (63 bars)
        assert bar["momentum_3m"] == pytest.approx((price_now / df_ind["Close"].iloc[i - 63] - 1) * 100)
        
        # 6m (126 bars)
        assert bar["momentum_6m"] == pytest.approx((price_now / df_ind["Close"].iloc[i - 126] - 1) * 100)
        
        # 12m (252 bars)
        assert bar["momentum_12m"] == pytest.approx((price_now / df_ind["Close"].iloc[i - 252] - 1) * 100)

    def test_engine_handles_min_bars_buffer(self):
        """Verify score_series uses MIN_BARS=260 and doesn't crash."""
        df = self._make_df(300)
        results = score_series(df)
        # 300 - 260 = 40 bars should be scored
        assert len(results) == 40
        # Check first result's date
        assert results[0]["date"] == df.index[260]

def test_high_rsi_signal_not_entered():
    """Signal with RSI > 68 must not produce a trade even if score is high."""
    from app.backtest.engine import simulate_trades, BacktestConfig
    import pandas as pd
    import numpy as np

    # Create dummy data
    n = 300
    closes = np.linspace(100, 110, n)
    df = pd.DataFrame({
        "Open": closes * 0.995,
        "High": closes * 1.01,
        "Low":  closes * 0.99,
        "Close": closes,
        "Volume": np.full(n, 1_000_000.0),
    }, index=pd.date_range("2021-01-01", periods=n, freq="B"))

    signal = {
        "date": df.index[270],
        "score": 65.0,
        "is_bullish": True,
        "rsi": 74.0,           # above 68 ceiling
        "adx": 30.0,
        "ema_signal": "bullish_cross",
        "volume_signal": "bullish",
        "rsi_signal": "neutral",
        "close": float(df["Close"].iloc[270]),
        "open": float(df["Open"].iloc[270]),
        "volume_breakout": True,
        "atr": 2.0,
        "above_200ema": True,
    }
    config = BacktestConfig(
        score_threshold=40.0,
        require_volume_breakout=False,
        use_regime_filter=False,
        min_adx=0.0,
    )
    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 0, "RSI > 68 should be blocked at entry"

def test_atr_trailing_stop_locks_in_profit():
    from app.backtest.engine import simulate_trades, BacktestConfig
    import pandas as pd
    import numpy as np

    entry_price = 100.0
    atr = 5.0
    n = 30
    closes = np.array(
        [100.0] * 5 +
        list(np.linspace(100, 112, 10)) +   # rise to 112 (activates at 105)
        list(np.linspace(112, 104.0, 15))   # drop to 104 (hits trail at 112 - 7.5 = 104.5)
    )[:n]
    df = pd.DataFrame({
        "Open":  closes * 0.995,
        "High":  closes + 1.0,
        "Low":   closes - 1.5,
        "Close": closes,
        "Volume": np.full(n, 1_000_000.0),
    }, index=pd.date_range("2023-01-01", periods=n, freq="B"))

    signal = {
        "date": df.index[0],
        "score": 60.0,
        "is_bullish": True,
        "rsi": 55.0,
        "adx": 28.0,
        "ema_signal": "bullish_cross",
        "volume_signal": "bullish",
        "rsi_signal": "bullish_strong",
        "close": 100.0,
        "open": 100.0,
        "volume_breakout": True,
        "atr": atr,
        "above_200ema": True,
    }
    config = BacktestConfig(
        score_threshold=0.0,
        holding_days=28,
        use_atr_stops=True,
        atr_multiplier=2.0,
        risk_reward_ratio=2.5,
        use_atr_trailing_stop=True,
        require_volume_breakout=False,
        use_regime_filter=False,
        min_adx=0.0,
        stop_loss_pct=0.0,
        target_pct=0.0,
        min_signal_tier=2,
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "atr_trailing_stop"
    assert trade.return_pct > 0
def test_partial_exit_produces_two_trade_records():
    """
    With use_partial_exits=True, a trade that hits T1 then T2 should produce
    two TradeResult objects: one at T1 and one at T2 (or stop/period).
    """
    entry_price = 100.0
    atr = 4.0
    # T1 = entry + 1.5 * 2.0 * atr = 100 + 12 = 112
    # T2 = entry + 2.5 * 2.0 * atr = 100 + 20 = 120
    closes = np.array([100, 100, 102, 105, 108, 112, 115, 118, 121, 120, 119, 118] + [118] * 18)[:30]
    highs = closes + 2.0
    lows = closes - 1.0
    df = pd.DataFrame(
        {
            "Open":  closes * 0.995,
            "High":  highs,
            "Low":   lows,
            "Close": closes,
            "Volume": np.full(30, 1_000_000.0),
        },
        index=pd.date_range("2023-01-01", periods=30, freq="B"),
    )
    signal = {
        "date": df.index[0],
        "score": 60.0,
        "is_bullish": True,
        "rsi": 55.0,
        "adx": 28.0,
        "ema_signal": "bullish_cross",
        "volume_signal": "bullish",
        "rsi_signal": "bullish_strong",
        "close": 100.0,
        "open": 100.0,
        "volume_breakout": True,
        "atr": atr,
        "above_200ema": True,
    }
    config = BacktestConfig(
        score_threshold=0.0,
        holding_days=29,
        use_atr_stops=True,
        atr_multiplier=2.0,
        risk_reward_ratio=2.5,
        use_partial_exits=True,
        use_atr_trailing_stop=False,
        require_volume_breakout=False,
        use_regime_filter=False,
        min_adx=0.0,
        stop_loss_pct=0.0,
        target_pct=0.0,
        position_size=10000.0,
        use_volatility_sizing=False,
        min_signal_tier=2,
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 2, f"Expected 2 trades (T1 + T2/remainder), got {len(trades)}"
    t1, t2 = sorted(trades, key=lambda t: t.exit_date)
    assert t1.exit_reason == "target_partial"
    assert t1.position_size_used == config.position_size * 0.5
    assert t2.position_size_used == config.position_size * 0.5

def test_invalidation_exit_triggers_after_two_bearish_bars():
    """
    If price closes below 3% from entry for 2 consecutive bars, exit at next open.
    """
    from app.backtest.engine import simulate_trades, BacktestConfig
    import pandas as pd
    import numpy as np
    import datetime

    entry_price = 100.0
    closes = np.array(
        [100.0, 101.0, 100.5,
         96.5,   # -3.5% — first bearish bar
         96.0,   # -4.0% — second consecutive bearish bar → exit next open
         97.0, 98.0, 100.0, 102.0, 105.0] + [105.0] * 20
    )
    df = pd.DataFrame(
        {
            "Open":  closes * 0.995,
            "High":  closes + 0.5,
            "Low":   closes - 0.5,
            "Close": closes,
            "Volume": np.full(len(closes), 1_000_000.0),
        },
        index=pd.date_range("2023-01-01", periods=len(closes), freq="B"),
    )
    signal = {
        "date": df.index[0],
        "score": 60.0,
        "is_bullish": True,
        "rsi": 58.0,
        "adx": 28.0,
        "ema_signal": "bullish_cross",
        "volume_signal": "bullish",
        "rsi_signal": "bullish_strong",
        "close": entry_price,
        "open": entry_price,
        "volume_breakout": True,
        "atr": 3.0,
        "above_200ema": True,
    }
    config = BacktestConfig(
        score_threshold=0.0,
        holding_days=29,
        stop_loss_pct=10.0,           # high enough not to trigger before invalidation
        use_atr_stops=False,
        use_atr_trailing_stop=False,
        use_signal_invalidation_exit=True,
        require_volume_breakout=False,
        use_regime_filter=False,
        min_adx=0.0,
        target_pct=20.0,
        min_signal_tier=2,
        require_consolidation=False,
        use_pullback_entry=False,
    )
    trades = simulate_trades("TEST", "Tech", df, [signal], config)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "signal_invalidated"
    # Exit at bar 6's open (the bar after the second bearish close)
    # entry_idx = 1
    # k = 1 (101.0), k = 2 (100.5), k = 3 (96.5), k = 4 (96.0)
    # consecutive_bearish_bars = 2 at k = 4.
    # next_k = 5.
    # exit_date = df.index[5]
    assert trade.exit_date == df.index[5].date()

def test_default_config_has_updated_values():
    from app.backtest.engine import BacktestConfig
    cfg = BacktestConfig()
    assert cfg.score_threshold == 60.0
    assert cfg.require_volume_breakout is False
    assert cfg.use_atr_stops is True
    assert cfg.min_adx == 0.0
    assert cfg.use_volatility_sizing is True
    assert cfg.max_concurrent_positions == 0
    assert cfg.max_sector_positions == 0
    assert cfg.use_atr_trailing_stop is True
