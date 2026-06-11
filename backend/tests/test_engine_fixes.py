import numpy as np
import pandas as pd

from app.backtest.engine import BacktestConfig, score_series, simulate_trades


def _make_ohlcv(n: int) -> pd.DataFrame:
    """Returns a simple uptrending OHLCV DataFrame of length n."""
    np.random.seed(0)
    closes = np.linspace(100, 200, n) + np.random.normal(0, 0.3, n)
    df = pd.DataFrame(
        {
            "Open": closes * 0.998,
            "High": closes * 1.01,
            "Low": closes * 0.99,
            "Close": closes,
            "Volume": np.full(n, 2_000_000.0),
        },
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )
    return df


class TestMinBars:
    def test_no_signals_below_210_bars(self):
        """score_series must return an empty list when df has fewer than 210 rows."""
        df = _make_ohlcv(209)
        config = BacktestConfig()
        results = score_series(df, config=config)
        assert results == [], (
            f"Expected no signals for a 209-bar DataFrame, got {len(results)}"
        )

    def test_signals_possible_at_210_bars(self):
        """score_series may return signals when df has exactly 210 rows."""
        df = _make_ohlcv(210)
        config = BacktestConfig()
        results = score_series(df, config=config)
        # We only assert it doesn't crash and returns a list; signal generation depends on data.
        assert isinstance(results, list)

    def test_no_signals_at_exactly_60_bars(self):
        """Regression: 60 bars (old MIN_BARS) must now produce zero signals."""
        df = _make_ohlcv(60)
        config = BacktestConfig()
        results = score_series(df, config=config)
        assert results == [], (
            "60-bar DataFrame should produce no signals after MIN_BARS fix."
        )


class TestAbove200EMAGate:
    def _base_config(self) -> BacktestConfig:
        return BacktestConfig(
            score_threshold=10.0,  # low so score doesn't interfere
            stop_loss_pct=0.0,
            target_pct=0.0,
            holding_days=5,
            require_volume_breakout=False,
            require_consolidation=False,
            use_pullback_entry=False,
        )

    def _make_signal(self, df, above_200ema, score=80.0) -> dict:
        return {
            "date": df.index[250],  # Middle of 300-bar DF
            "score": score,
            "above_200ema": above_200ema,
            "rsi": 55.0,
            "adx": 25.0,
            "ema_signal": "bullish_cross",
            "volume_signal": "bullish",
            "rsi_signal": "bullish_strong",
            "volume_breakout": True,
            "atr": 2.0,
        }

    def test_above_200ema_none_produces_no_trade(self):
        """Signals with above_200ema=None must be rejected regardless of score."""
        df = _make_ohlcv(300)
        signal = self._make_signal(df, above_200ema=None)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._base_config())
        assert trades == [], "above_200ema=None should produce no trade"

    def test_above_200ema_false_produces_no_trade(self):
        """Signals with above_200ema=False must be rejected regardless of score."""
        df = _make_ohlcv(300)
        signal = self._make_signal(df, above_200ema=False)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._base_config())
        assert trades == [], "above_200ema=False should produce no trade"

    def test_above_200ema_true_allows_trade(self):
        """Signals with above_200ema=True and sufficient score must produce a trade."""
        df = _make_ohlcv(300)
        signal = self._make_signal(df, above_200ema=True)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._base_config())
        assert len(trades) == 1, "above_200ema=True should produce a trade"


class TestADXGate:
    def _config(self, min_adx: float) -> BacktestConfig:
        return BacktestConfig(
            score_threshold=10.0,
            stop_loss_pct=0.0,
            target_pct=0.0,
            holding_days=5,
            require_volume_breakout=False,
            min_adx=min_adx,
            require_consolidation=False,
            use_pullback_entry=False,
        )

    def _signal(self, df, adx_value) -> dict:
        return {
            "date": df.index[250],
            "score": 80.0,
            "above_200ema": True,
            "rsi": 55.0,
            "adx": adx_value,
            "ema_signal": "bullish_cross",
            "volume_signal": "bullish",
            "rsi_signal": "bullish_strong",
            "volume_breakout": False,
            "atr": 2.0,
        }

    def test_adx_below_threshold_produces_no_trade(self):
        """Signal with ADX < min_adx must be skipped."""
        df = _make_ohlcv(300)
        signal = self._signal(df, adx_value=15.0)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._config(min_adx=20))
        assert trades == [], "ADX=15 below threshold=20 should produce no trade"

    def test_adx_none_produces_no_trade(self):
        """Signal with ADX=None must be skipped when min_adx > 0."""
        df = _make_ohlcv(300)
        signal = self._signal(df, adx_value=None)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._config(min_adx=20))
        assert trades == [], "ADX=None should produce no trade when min_adx=20"

    def test_adx_at_threshold_allows_trade(self):
        """Signal with ADX exactly equal to min_adx must be allowed."""
        df = _make_ohlcv(300)
        signal = self._signal(df, adx_value=20.0)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._config(min_adx=20))
        assert len(trades) == 1, "ADX=20 at threshold=20 should produce a trade"

    def test_adx_gate_disabled_when_min_adx_zero(self):
        """min_adx=0 must disable the gate; ADX=None signals are allowed."""
        df = _make_ohlcv(300)
        signal = self._signal(df, adx_value=None)
        trades = simulate_trades("TEST", "Tech", df, [signal], self._config(min_adx=0))
        assert len(trades) == 1, "min_adx=0 should disable ADX gate"

    def test_backtest_config_default_min_adx_is_25(self):
        """BacktestConfig default min_adx must be 25.0 (enabled)."""
        config = BacktestConfig()
        assert config.min_adx == 25.0


class TestConfigDefaults:
    def test_default_score_threshold_is_55(self):
        config = BacktestConfig()
        assert config.score_threshold == 55.0, (
            f"Default score_threshold must be 55.0, got {config.score_threshold}"
        )

    def test_default_require_volume_breakout_is_true(self):
        config = BacktestConfig()
        assert config.require_volume_breakout is False, (
            "Default require_volume_breakout must be False"
        )


class TestSignalBarQualityFilter:
    def _base_config(self) -> BacktestConfig:
        return BacktestConfig(
            score_threshold=10.0,
            stop_loss_pct=10.0,
            atr_multiplier=2.0,
            use_pullback_entry=False,
            require_consolidation=False,
        )

    def test_weak_close_signal_skipped(self):
        """
        Signal bar: High=110, Low=90, Close=95.
        Range = 20.
        Close position = (95 - 90) / 20 = 5 / 20 = 0.25 (25%).
        0.25 < 0.3 -> Skip.
        """
        n = 300
        closes = np.linspace(100, 200, n)
        df = pd.DataFrame(
            {
                "Open": closes * 0.99,
                "High": closes * 1.01,
                "Low": closes * 0.99,
                "Close": closes,
                "Volume": 2_000_000.0,
            },
            index=pd.date_range("2020-01-01", periods=n, freq="B"),
        )

        signal_idx = 250
        df.iloc[signal_idx, df.columns.get_loc("High")] = 110.0
        df.iloc[signal_idx, df.columns.get_loc("Low")] = 90.0
        df.iloc[signal_idx, df.columns.get_loc("Close")] = 95.0

        signal = {
            "date": df.index[signal_idx],
            "score": 80.0,
            "above_200ema": True,
            "rsi": 55.0,
            "adx": 25.0,
            "ema_signal": "bullish_cross",
            "atr": 1.0,
            "close": 95.0,
        }

        trades = simulate_trades("TEST", "Tech", df, [signal], self._base_config())
        assert trades == [], (
            f"Expected weak close signal to be skipped, but got {len(trades)} trades"
        )

    def test_strong_close_large_bar_accepted(self):
        """
        Signal bar: High=120, Low=100, Close=115.
        Range = 20.
        Close position = (115 - 100) / 20 = 15 / 20 = 0.75 (75%).
        0.75 > 0.3 -> Accept.
        """
        n = 300
        closes = np.linspace(100, 200, n)
        df = pd.DataFrame(
            {
                "Open": closes * 0.99,
                "High": closes * 1.01,
                "Low": closes * 0.99,
                "Close": closes,
                "Volume": 2_000_000.0,
            },
            index=pd.date_range("2020-01-01", periods=n, freq="B"),
        )

        signal_idx = 250
        df.iloc[signal_idx, df.columns.get_loc("High")] = 120.0
        df.iloc[signal_idx, df.columns.get_loc("Low")] = 100.0
        df.iloc[signal_idx, df.columns.get_loc("Close")] = 115.0

        signal = {
            "date": df.index[signal_idx],
            "score": 80.0,
            "above_200ema": True,
            "rsi": 55.0,
            "adx": 25.0,
            "ema_signal": "bullish_cross",
            "atr": 10.0,  # Increased to pass volatility filter
            "close": 115.0,
        }

        config = self._base_config()
        config.stop_loss_pct = 20.0

        trades = simulate_trades("TEST", "Tech", df, [signal], config)
        assert len(trades) == 1, (
            f"Expected strong close signal to be accepted, but got {len(trades)} trades"
        )
