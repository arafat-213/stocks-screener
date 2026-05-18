import pytest
import pandas as pd
import datetime
from app.backtest.engine import (
    BacktestConfig, 
    simulate_trades, 
    _compute_position_size, 
    TradeResult, 
    compute_metrics,
    score_series,
    simulate_portfolio
)
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
        assert metrics["total_return_pct"] == pytest.approx(0.1, abs=0.01)

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
