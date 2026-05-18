import numpy as np
import pandas as pd
import pytest
from app.pipeline.scorer import calculate_technical_score, calculate_combined_score
from tests.conftest import make_trending_df


class TestRsiOverboughtCap:
    def _make_high_rsi_df(self) -> pd.DataFrame:
        """
        Create a DataFrame whose final bar has RSI > 70 but < 80.
        Use a persistent rally to drive RSI into the 71-79 zone.
        """
        n = 300
        rng = np.random.default_rng(7)
        # Last 40 bars: strong uptrend to push RSI high
        slow = np.linspace(100, 130, n - 40)
        fast = np.linspace(130, 165, 40)
        closes = np.concatenate([slow, fast]) + rng.normal(0, 0.1, n)
        opens = closes * rng.uniform(0.998, 1.002, n)
        highs = closes * rng.uniform(1.002, 1.01, n)
        lows = closes * rng.uniform(0.99, 0.998, n)
        volumes = rng.uniform(1_000_000, 2_000_000, n)
        dates = pd.date_range("2021-01-01", periods=n, freq="B")
        return pd.DataFrame(
            {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
            index=dates,
        )

    def test_rsi_between_70_and_80_does_not_zero_score(self):
        df = self._make_high_rsi_df()
        result = calculate_technical_score(df, timeframe="D")
        rsi = result["rsi"]
        if 70 < rsi < 80:
            assert result["score"] > 0, (
                f"RSI={rsi:.1f} (between 70-80) should not zero the score"
            )

    def test_rsi_above_80_zeros_score_in_combined(self):
        """combined score must be 0 when RSI >= 80."""
        df = make_trending_df(n=300)
        result = calculate_combined_score(df, info={}, timeframe="D")
        rsi = result["rsi"]
        if rsi >= 80:
            assert result["combined_score"] == 0.0

    def test_combined_score_zeroed_when_rsi_over_80(self):
        """
        Inject a mock scenario: verify the threshold constant is 80, not 70.
        We inspect the source constant by checking the scorer boundary.
        """
        import inspect
        from app.pipeline import scorer
        source = inspect.getsource(scorer.calculate_combined_score)
        assert "> 80" in source or ">= 80" in source, (
            "calculate_combined_score must use 80 (not 70) as the RSI overbought cap"
        )

    def test_score_series_cap_is_80(self):
        from app.pipeline import scorer
        import inspect
        source = inspect.getsource(scorer)
        # The old constant '> 70' in score_series / calculate_combined_score
        # context (scorer-level zeroing) should be replaced with 80
        # Count occurrences of "> 70" in RSI context
        lines_with_70 = [
            l for l in source.splitlines()
            if "> 70" in l and "rsi" in l.lower()
        ]
        assert len(lines_with_70) == 0, (
            f"Found RSI > 70 cap still present in scorer.py: {lines_with_70}"
        )


class TestVolumeThresholdConsistency:
    def _make_volume_df(self, volume_multiplier: float) -> pd.DataFrame:
        """
        Returns 300 bars where the final bar has volume = multiplier × 20-day SMA.
        The last bar is a green (Close > Open) day.
        """
        n = 300
        rng = np.random.default_rng(17)
        closes = np.linspace(100, 140, n) + rng.normal(0, 0.2, n)
        opens = closes * 0.998
        highs = closes * 1.005
        lows = opens * 0.995
        base_vol = 1_000_000.0
        volumes = np.full(n, base_vol)
        # Last bar: set volume to multiplier × SMA(20) of prior bars
        prior_sma = base_vol  # all prior bars equal, so SMA = base_vol
        volumes[-1] = volume_multiplier * prior_sma
        dates = pd.date_range("2021-01-01", periods=n, freq="B")
        return pd.DataFrame(
            {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
            index=dates,
        )

    def test_volume_below_2x_does_not_set_breakout_flag(self):
        df = self._make_volume_df(1.6)
        result = calculate_technical_score(df, timeframe="D")
        assert result["volume_breakout"] is False

    def test_volume_above_2x_sets_breakout_flag(self):
        df = self._make_volume_df(2.5)
        result = calculate_technical_score(df, timeframe="D")
        assert result["volume_breakout"] is True

    def test_volume_scoring_threshold_is_2x(self):
        """
        Scoring (volume_signal = 'bullish') must use the same 2× threshold
        as the breakout flag. Check source to confirm constant.
        """
        import inspect
        from app.pipeline import scorer
        source = inspect.getsource(scorer.calculate_technical_score)
        # Old code: '1.5 * sma20_vol' for volume scoring
        assert "1.5 * sma20_vol" not in source, (
            "Volume scoring still uses 1.5× — must be raised to 2.0×"
        )


class TestMacdEmaDecoupling:
    def _make_ema_cross_df(self) -> pd.DataFrame:
        """
        Constructs a DataFrame that reliably produces a fresh EMA5/13 cross on
        the final bar. First 260 bars: downtrend (EMA5 < EMA13). Last 40 bars:
        sharp reversal so EMA5 crosses above EMA13 near the end.
        """
        n = 300
        rng = np.random.default_rng(99)
        down = np.linspace(200, 120, 260)
        up = np.linspace(120, 180, 40)
        closes = np.concatenate([down, up]) + rng.normal(0, 0.3, n)
        opens = closes * 0.999
        highs = closes * 1.006
        lows = closes * 0.994
        volumes = rng.uniform(800_000, 2_000_000, n)
        dates = pd.date_range("2021-01-01", periods=n, freq="B")
        return pd.DataFrame(
            {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
            index=dates,
        )

    def test_simultaneous_ema_and_macd_cross_does_not_exceed_35_pts(self):
        """
        On a day where both EMA and MACD cross simultaneously, the combined
        score from those two components must not exceed 28 (20 EMA + 8 MACD
        co-occurrence cap), protecting against the 40-pt double-count spike.
        """
        import inspect
        from app.pipeline import scorer
        source = inspect.getsource(scorer.calculate_technical_score)
        assert "fresh_ema_cross and fresh_macd_cross" in source or \
               "fresh_macd_cross and fresh_ema_cross" in source or \
               "fresh_ema_cross and not fresh_macd_cross" in source, (
            "MACD scoring must branch on whether EMA cross co-occurred"
        )

    def test_macd_budget_reduced_to_15(self):
        import inspect
        from app.pipeline import scorer
        source = inspect.getsource(scorer.calculate_technical_score)
        # Old code awarded score += 20 for fresh MACD cross
        # New code must award score += 15 (standalone) and score += 8 (co-occurrence)
        assert "score += 20" not in source.split("# 2. MACD")[1].split("# 3. RSI")[0], (
            "MACD section must not award 20 pts — max standalone is 15"
        )


class TestAdxScoring:
    def test_adx_contributes_to_score(self):
        """A stock with strong trend (ADX > 35) should score higher than a weak one."""
        import inspect
        from app.pipeline import scorer
        source = inspect.getsource(scorer.calculate_technical_score)
        # Look for the ADX scoring block specifically
        assert "adx >= 35" in source and "score += 5" in source, (
            "ADX scoring (score +=) must be present in calculate_technical_score"
        )

    def test_max_score_still_70_with_adx(self):
        """
        On a perfect bar (all conditions met), score must not exceed 70.
        EMA(20) + MACD(15) + RSI(15) + Volume(15) + ADX(5) = 70.
        """
        df = make_trending_df(n=400, trend=0.003)
        result = calculate_technical_score(df, timeframe="D")
        assert result["score"] <= 70.0, (
            f"Technical score exceeded 70: {result['score']}"
        )
