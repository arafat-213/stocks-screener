import numpy as np
import pandas as pd
import pytest

from app.core.strategy import TechnicalStrategy

# Use TechnicalStrategy directly for tests
strategy = TechnicalStrategy()


def _make_base_df(n: int = 300) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "Open": np.full(n, 100.0),
            "High": np.full(n, 105.0),
            "Low": np.full(n, 95.0),
            "Close": np.full(n, 100.0),
            "Volume": np.full(n, 1_000_000.0),
        },
        index=pd.date_range("2022-01-01", periods=n, freq="B"),
    )
    return df


class TestMACDScoring:
    def test_macd_positive_territory_scores_well(self):
        """MACD > signal AND MACD > 0 (no fresh cross) should score 14.5 pts."""
        df = _make_base_df()
        # Add necessary columns for evaluate(skip_ta=True)
        df["EMA_200"] = 50.0  # Above 200 EMA
        df["MACD_12_26_9"] = 2.0
        df["MACDs_12_26_9"] = 1.0
        df["RSI_14"] = 55.0

        result = strategy.evaluate(df, timeframe="D", skip_ta=True)

        # 14.5 pts for MACD + some trend pts
        assert result["macd"] == 2.0
        assert result["score"] >= 14.5

    def test_macd_negative_territory_scores_lower_than_positive(self):
        """MACD > signal AND MACD < 0 must produce 7.0 pts."""
        df_pos = _make_base_df()
        df_pos["EMA_200"] = 50.0
        df_pos["MACD_12_26_9"] = 2.0
        df_pos["MACDs_12_26_9"] = 1.0
        df_pos["RSI_14"] = 55.0

        df_neg = _make_base_df()
        df_neg["EMA_200"] = 50.0
        df_neg["MACD_12_26_9"] = -1.0
        df_neg["MACDs_12_26_9"] = -2.0
        df_neg["RSI_14"] = 55.0

        res_pos = strategy.evaluate(df_pos, timeframe="D", skip_ta=True)
        res_neg = strategy.evaluate(df_neg, timeframe="D", skip_ta=True)

        assert res_pos["score"] > res_neg["score"]
        # Pos: 14.5 MACD, Neg: 7.0 MACD. Difference should be 7.5
        assert res_pos["score"] - res_neg["score"] == pytest.approx(7.5)


class TestEMAScoring:
    def test_fresh_ema_cross_scores_full_weight(self):
        """EMA5 crossing EMA13 must score full weight (28.5 pts)."""
        df = _make_base_df()
        df["EMA_200"] = 50.0
        df["EMA_5"] = 110.0
        df["EMA_13"] = 105.0
        df["EMA_26"] = 100.0
        df["RSI_14"] = 55.0
        # Prev values for cross detection
        df.loc[df.index[-2], "EMA_5"] = 104.0
        df.loc[df.index[-2], "EMA_13"] = 105.0
        df.loc[df.index[-2], "RSI_14"] = 54.0

        result = strategy.evaluate(df, timeframe="D", skip_ta=True)
        assert result["ema_signal"] == "bullish_cross"
        assert result["score"] >= 28.5

    def test_ema_pullback_scores_21_5(self):
        """Pullback to EMA20 in an uptrend must score 21.5 pts."""
        df = _make_base_df()
        df["EMA_200"] = 50.0
        df["EMA_5"] = 120.0
        df["EMA_13"] = 115.0
        df["EMA_20"] = 110.0
        df["EMA_26"] = 105.0
        df["Close"] = 111.0  # Within 2% of EMA20 (110)
        df["RSI_14"] = 55.0

        result = strategy.evaluate(df, timeframe="D", skip_ta=True)
        assert result["ema_signal"] == "bullish_pullback"
        assert result["score"] >= 21.5


class TestDecoupling:
    def test_macd_ema_correlated_event_penalty(self):
        """When MACD and EMA cross on same day, they should score less than sum of weights."""
        df = _make_base_df()
        df["EMA_200"] = 50.0
        df["EMA_5"] = 110.0
        df["EMA_13"] = 105.0
        df["EMA_26"] = 100.0
        df["MACD_12_26_9"] = 1.0
        df["MACDs_12_26_9"] = 0.5
        df["RSI_14"] = 55.0

        # Prev values for cross detection
        df.loc[df.index[-2], "EMA_5"] = 104.0
        df.loc[df.index[-2], "EMA_13"] = 105.0
        df.loc[df.index[-2], "MACD_12_26_9"] = 0.4
        df.loc[df.index[-2], "MACDs_12_26_9"] = 0.5

        result = strategy.evaluate(df, timeframe="D", skip_ta=True)

        # Expected: EMA(28.5) + MACD correlated(11.5) + RSI strong(7.0) + EMA200(7.0) = 54.0
        assert result["ema_signal"] == "bullish_cross"
        assert result["score"] == pytest.approx(54.0)


class TestRSIScoring:
    def test_rsi_component_never_exceeds_weighted_max(self):
        """
        The RSI sub-component must never contribute more than its weight (default 21.5).
        """
        df = _make_base_df()
        df["EMA_200"] = 50.0
        df["RSI_14"] = 60.0  # Bullish strong (7.0 pts)

        result = strategy.evaluate(df, timeframe="D", skip_ta=True)
        # 7.0 (RSI) + 7.0 (EMA200) = 14.0
        assert result["score"] == pytest.approx(14.0)

        df["RSI_14"] = 85.0  # Overbought state
        result = strategy.evaluate(df, timeframe="D", skip_ta=True)
        # Score is no longer zeroed, but is_overextended is True
        assert result["is_overextended"] is True
        assert result["score"] > 0.0

    def test_rsi_recovery_confirmed_by_ema_cross(self):
        """RSI recovery + EMA cross scores full RSI weight."""
        df = _make_base_df()
        df["EMA_200"] = 50.0
        df["EMA_5"] = 110.0
        df["EMA_13"] = 105.0
        df["EMA_21"] = 108.0
        df["Close"] = 115.0
        df["RSI_14"] = 35.0
        # Prev values
        df.loc[df.index[-2], "EMA_5"] = 104.0
        df.loc[df.index[-2], "EMA_13"] = 105.0
        df.loc[df.index[-2], "RSI_14"] = 25.0
        # Oversold in last 5 days
        df.loc[df.index[-3], "RSI_14"] = 25.0

        result = strategy.evaluate(df, timeframe="D", skip_ta=True)
        # EMA Cross (28.5) + RSI Recovery (21.5) + EMA200 (7.0) = 57.0
        assert result["ema_signal"] == "bullish_cross"
        assert result["rsi_signal"] == "bullish_recovery_confirmed"
        assert result["score"] == pytest.approx(57.0)
