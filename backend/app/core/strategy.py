from typing import Any, Dict, Optional

import pandas as pd
import pandas_ta_classic  # noqa: F401

from app.core.trading_config import UnifiedTradingConfig


class TechnicalStrategy:
    """
    Centralized source of truth for all technical signal logic.
    Used by both the Live Pipeline and the Backtest Engine.
    """

    def __init__(self, config: Optional[UnifiedTradingConfig] = None):
        self.config = config or UnifiedTradingConfig()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates all TA indicators required for scoring.
        """
        # Ensure we don't modify the original dataframe in a way that affects caller
        df = df.copy()

        # Calculate Indicators using pandas-ta
        df.ta.ema(length=5, append=True)
        df.ta.ema(length=13, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=26, append=True)
        df.ta.ema(length=200, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.atr(length=14, append=True)
        df.ta.adx(length=14, append=True)

        # Use explicit name for volume SMA to avoid collision with price SMA
        if "Volume" in df.columns:
            df["VOL_SMA_20"] = df["Volume"].rolling(window=20).mean()
        else:
            df["VOL_SMA_20"] = pd.Series(dtype="float64")

        # EMA Slope (20 periods)
        ema20_col = "EMA_20"
        if ema20_col in df.columns:
            df["EMA_SLOPE_20"] = (df[ema20_col] - df[ema20_col].shift(5)) / 5.0

        # New Vectorized Components
        df["WEEK52_HIGH"] = df["Close"].rolling(window=252, min_periods=1).max()
        df["WEEK52_LOW"] = df["Close"].rolling(window=252, min_periods=1).min()

        # Resistance: Highest close in the year prior to the last 20 bars
        # Original: df["Close"].iloc[i - 259 : i - 19].max()
        # Vectorized: shift(20) then rolling(240)
        df["RESISTANCE_LEVEL"] = (
            df["Close"].shift(20).rolling(window=240, min_periods=1).max()
        )

        # Momentum
        for period, shift in [("1M", 21), ("3M", 63), ("6M", 126), ("12M", 252)]:
            df[f"MOMENTUM_{period}"] = (
                df["Close"] / df["Close"].shift(shift) - 1
            ) * 100

        return df

    def calculate_signals(self, df: pd.DataFrame, timeframe: str = "D") -> pd.DataFrame:
        """Computes boolean signal series for the entire dataframe."""
        # Ensure indicators exist
        if "EMA_5" not in df.columns:
            df = self.calculate_indicators(df)

        # Check for mandatory columns; if missing (e.g. not enough data), return empty signals
        required = [
            "EMA_5",
            "EMA_13",
            "EMA_20",
            "EMA_26",
            "RSI_14",
            "MACD_12_26_9",
            "MACDs_12_26_9",
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            df["SIGNAL_EMA_CROSS"] = False
            df["SIGNAL_PULLBACK_20"] = False
            df["SIGNAL_MACD_BULLISH"] = False
            df["IS_OVEREXTENDED"] = False
            df["IS_BULLISH"] = False
            return df

        ema5 = df["EMA_5"]
        ema13 = df["EMA_13"]
        ema20 = df["EMA_20"]
        ema26 = df["EMA_26"]
        price = df["Close"]
        macd = df["MACD_12_26_9"]
        signal = df["MACDs_12_26_9"]
        rsi = df["RSI_14"]

        # 1. Fresh EMA Cross
        df["SIGNAL_EMA_CROSS"] = (
            (ema5 > ema13) & (ema5.shift(1) <= ema13.shift(1))
        ).fillna(False)

        # 2. Pullback to EMA 20
        df["SIGNAL_PULLBACK_20"] = (
            (ema5 > ema13) & (ema13 > ema26) & (abs(price - ema20) / ema20 < 0.02)
        ).fillna(False)

        # 3. MACD Signal
        df["SIGNAL_MACD_BULLISH"] = (macd > signal).fillna(False)

        # 4. Overextended
        df["IS_OVEREXTENDED"] = (rsi > self.config.rsi_overbought_threshold).fillna(
            False
        )

        # 5. is_bullish (Vectorized version of the logic in evaluate)
        if timeframe == "D":
            df["IS_BULLISH"] = (
                (
                    df["SIGNAL_EMA_CROSS"]
                    | df["SIGNAL_PULLBACK_20"]
                    | ((ema5 > ema13) & (ema13 > ema26))
                )
                & df["SIGNAL_MACD_BULLISH"]
                & (rsi > self.config.rsi_min)
            ).fillna(False)

            # Hard Filters (Must match evaluate)
            df["IS_BULLISH"] &= rsi <= self.config.rsi_max

            if "EMA_200" in df.columns:
                df["IS_BULLISH"] &= price > df["EMA_200"]

            if "ADX_14" in df.columns:
                df["IS_BULLISH"] &= df["ADX_14"] >= self.config.min_adx

        elif timeframe == "W":
            df["IS_BULLISH"] = ((rsi > 50) & (price > ema26)).fillna(False)
        elif timeframe == "M":
            df["IS_BULLISH"] = (
                (rsi > 50) & ((price > ema13) | (price > ema26))
            ).fillna(False)
        else:
            # Fallback to Daily logic
            df["IS_BULLISH"] = (
                (
                    df["SIGNAL_EMA_CROSS"]
                    | df["SIGNAL_PULLBACK_20"]
                    | ((ema5 > ema13) & (ema13 > ema26))
                )
                & df["SIGNAL_MACD_BULLISH"]
                & (rsi > self.config.rsi_min)
            ).fillna(False)

        return df

    def evaluate(
        self, df: pd.DataFrame, timeframe: str = "D", i: int = -1, skip_ta: bool = False
    ) -> Dict[str, Any]:
        """
        Calculates technical sub-score (Max 100 pts) based on UnifiedTradingConfig weights.
        - i: index of the bar to score (default -1 for latest)
        - skip_ta: if True, assumes indicators are already present in df
        """
        if len(df) < 1:
            return {
                "score": 0.0,
                "rsi": 0.0,
                "macd": 0.0,
                "ema_signal": "neutral",
                "volume_signal": "neutral",
                "rsi_signal": "neutral",
                "is_bullish": False,
                "ema5_level": None,
                "ema13_level": None,
                "ema20_level": None,
                "ema26_level": None,
                "atr": None,
                "momentum_1m": None,
                "momentum_3m": None,
                "momentum_6m": None,
                "momentum_12m": None,
                "adx": None,
                "above_200ema": None,
                "ema_slope_20": None,
                "week52_high": None,
                "week52_low": None,
                "pct_from_52w_high": None,
                "pct_from_52w_low": None,
                "resistance_level": None,
                "pct_from_resistance": None,
                "volume_breakout": False,
            }

        if not skip_ta:
            df = self.calculate_indicators(df)

        if i < 0:
            i = len(df) + i

        # Safety check
        if i < 0 or i >= len(df):
            return self.evaluate(pd.DataFrame())

        latest = df.iloc[i]
        prev = df.iloc[i - 1] if i > 0 else latest

        score = 0.0
        ema_signal = "neutral"
        volume_signal = "neutral"
        rsi_signal = "neutral"
        is_bullish = False
        is_overextended = False

        ema5 = latest.get("EMA_5")
        ema13 = latest.get("EMA_13")
        ema20 = latest.get("EMA_20")
        ema26 = latest.get("EMA_26")
        ema200 = latest.get("EMA_200")
        price = latest.get("Close")
        macd_line = latest.get("MACD_12_26_9")
        signal_line = latest.get("MACDs_12_26_9")
        rsi = latest.get("RSI_14")
        prev_rsi = prev.get("RSI_14")
        atr = latest.get("ATRr_14")
        adx = latest.get("ADX_14")
        ema_slope_20 = latest.get("EMA_SLOPE_20")

        # Weights from config
        w_ema = self.config.ema_weight
        w_macd = self.config.macd_weight
        w_rsi = self.config.rsi_weight
        w_volume = self.config.volume_weight
        w_trend = self.config.trend_weight
        w_ema200 = self.config.ema200_weight

        # Momentum (lookback from full df)
        momentum_1m = latest.get("MOMENTUM_1M")
        momentum_3m = latest.get("MOMENTUM_3M")
        momentum_6m = latest.get("MOMENTUM_6M")
        momentum_12m = latest.get("MOMENTUM_12M")

        # Above 200 EMA
        above_200ema = (price > ema200) if pd.notna(ema200) else None
        if above_200ema:
            score += w_ema200

        # 52-Week High/Low and Resistance
        week52_high = latest.get("WEEK52_HIGH")
        week52_low = latest.get("WEEK52_LOW")
        pct_from_52w_high = None
        pct_from_52w_low = None
        resistance_level = latest.get("RESISTANCE_LEVEL")
        pct_from_resistance = None

        if pd.notna(week52_high):
            pct_from_52w_high = (price / week52_high - 1) * 100
        if pd.notna(week52_low):
            pct_from_52w_low = (price / week52_low - 1) * 100

        # Resistance
        if pd.notna(resistance_level):
            pct_from_resistance = (price / resistance_level - 1) * 100

        # Volume Breakout (2x 20-day SMA on green day)
        volume_breakout = False
        volume = latest.get("Volume")
        sma20_vol = latest.get("VOL_SMA_20")
        is_green = (
            (latest.get("Close") > latest.get("Open"))
            if pd.notna(latest.get("Close")) and pd.notna(latest.get("Open"))
            else False
        )
        if pd.notna(volume) and pd.notna(sma20_vol) and sma20_vol > 0:
            if volume > 2.0 * sma20_vol and is_green:
                volume_breakout = True

        min_bars = 24 if timeframe == "M" else 60
        if i >= min_bars - 1:
            if timeframe == "D":
                # 1. EMA Alignment (Tiered Scoring)
                prev_ema5 = prev.get("EMA_5")
                prev_ema13 = prev.get("EMA_13")

                fresh_ema_cross = (
                    pd.notna(ema5)
                    and pd.notna(ema13)
                    and pd.notna(prev_ema5)
                    and pd.notna(prev_ema13)
                    and ema5 > ema13
                    and prev_ema5 <= prev_ema13
                )

                pullback_to_ema20 = (
                    pd.notna(ema20)
                    and pd.notna(price)
                    and pd.notna(ema5)
                    and pd.notna(ema13)
                    and pd.notna(ema26)
                    and ema5 > ema13 > ema26
                    and abs(price - ema20) / ema20 < 0.02
                )

                if fresh_ema_cross:
                    score += w_ema
                    ema_signal = "bullish_cross"
                elif pullback_to_ema20:
                    score += w_ema * (21.5 / 28.5)
                    ema_signal = "bullish_pullback"
                elif (
                    pd.notna(ema5)
                    and pd.notna(ema13)
                    and pd.notna(ema26)
                    and ema5 > ema13 > ema26
                    and price > ema26
                ):
                    score += w_ema * (11.5 / 28.5)
                    ema_signal = "bullish"
                elif (
                    pd.notna(ema5)
                    and pd.notna(ema13)
                    and pd.notna(ema26)
                    and ema5 < ema13 < ema26
                ):
                    ema_signal = "bearish"

                # 2. MACD (decoupled from EMA cross)
                prev_macd = prev.get("MACD_12_26_9")
                prev_signal_line = prev.get("MACDs_12_26_9")

                if pd.notna(macd_line) and pd.notna(signal_line):
                    fresh_macd_cross = (
                        pd.notna(prev_macd)
                        and pd.notna(prev_signal_line)
                        and macd_line > signal_line
                        and prev_macd <= prev_signal_line
                    )
                    if fresh_macd_cross and fresh_ema_cross:
                        # Correlated same-day event: award partial credit only
                        score += w_macd * (11.5 / 21.5)
                    elif fresh_macd_cross:
                        score += w_macd
                    elif macd_line > signal_line and macd_line > 0:
                        score += w_macd * (14.5 / 21.5)
                    elif macd_line > signal_line and macd_line < 0:
                        score += w_macd * (7.0 / 21.5)

                # 3. RSI 14
                if pd.notna(rsi) and pd.notna(prev_rsi):
                    # Check for recovery in last N days
                    lookback = self.config.rsi_recovery_lookback
                    recent_rsi = df["RSI_14"].iloc[max(0, i - (lookback - 1)) : i + 1]
                    was_oversold = any(recent_rsi < 30)

                    recovering = (
                        was_oversold and rsi > 30 and pd.notna(ema20) and price > ema20
                    )
                    crossing_50 = prev_rsi <= 50 and rsi > 50

                    if recovering and fresh_ema_cross:
                        score += w_rsi
                        rsi_signal = "bullish_recovery_confirmed"
                    elif recovering:
                        score += w_rsi
                        rsi_signal = "bullish_recovery"
                    elif crossing_50:
                        score += w_rsi * (14.5 / 21.5)
                        rsi_signal = "bullish_crossing"
                    elif 50 < rsi <= 65:
                        score += w_rsi * (7.0 / 21.5)
                        rsi_signal = "bullish_strong"
                    elif 65 < rsi <= 68:
                        rsi_signal = "bullish_extended"

                # 4. Volume
                if volume_breakout:
                    score += w_volume
                    volume_signal = "bullish"

                # 5. Trend Quality: ADX + 3-Month Momentum
                trend_pts = 0
                if pd.notna(adx):
                    if adx >= 35:
                        trend_pts += w_trend * (4.5 / 7.0)
                    elif adx >= 25:
                        trend_pts += w_trend * (3.0 / 7.0)
                    elif adx >= 20:
                        trend_pts += w_trend * (1.5 / 7.0)
                if momentum_3m is not None:
                    if momentum_3m > 15:
                        trend_pts += w_trend * (3.0 / 7.0)
                    elif momentum_3m > 5:
                        trend_pts += w_trend * (1.5 / 7.0)
                score += min(trend_pts, w_trend)

                # Define is_bullish for D
                is_bullish = (
                    (
                        fresh_ema_cross
                        or pullback_to_ema20
                        or (
                            pd.notna(ema5)
                            and pd.notna(ema13)
                            and pd.notna(ema26)
                            and ema5 > ema13 > ema26
                        )
                    )
                    and pd.notna(macd_line)
                    and pd.notna(signal_line)
                    and macd_line > signal_line
                    and pd.notna(rsi)
                    and rsi > self.config.rsi_min
                )

                if pd.notna(rsi) and rsi > self.config.rsi_overbought_threshold:
                    is_overextended = True

                # Hard Filters (Task 2 Enhancements)
                if pd.notna(rsi) and rsi > self.config.rsi_max:
                    score = 0.0
                    is_bullish = False

                if pd.notna(ema200) and price < ema200:
                    score = 0.0
                    is_bullish = False

                if pd.notna(adx) and adx < self.config.min_adx:
                    score = 0.0
                    is_bullish = False

            elif timeframe == "W":
                is_bullish = (
                    pd.notna(rsi) and rsi > 50 and pd.notna(ema26) and price > ema26
                )
                score = 100.0 if is_bullish else 0.0
                ema_signal = "bullish" if is_bullish else "neutral"

            elif timeframe == "M":
                is_bullish = (
                    pd.notna(rsi)
                    and rsi > 50
                    and (
                        (pd.notna(ema13) and price > ema13)
                        or (pd.notna(ema26) and price > ema26)
                    )
                )
                score = 100.0 if is_bullish else 0.0
                ema_signal = "bullish" if is_bullish else "neutral"

        # Ensure final score is in range 0-100
        score = max(0.0, min(100.0, score))

        return {
            "score": float(score),
            "is_overextended": bool(is_overextended),
            "rsi": float(rsi) if pd.notna(rsi) else 0.0,
            "macd": float(macd_line) if pd.notna(macd_line) else 0.0,
            "ema_signal": ema_signal,
            "volume_signal": volume_signal,
            "rsi_signal": rsi_signal,
            "is_bullish": bool(is_bullish),
            "ema5_level": float(ema5) if pd.notna(ema5) else None,
            "ema13_level": float(ema13) if pd.notna(ema13) else None,
            "ema20_level": float(ema20) if pd.notna(ema20) else None,
            "ema26_level": float(ema26) if pd.notna(ema26) else None,
            "atr": float(atr) if pd.notna(atr) else None,
            "momentum_1m": float(momentum_1m) if momentum_1m is not None else None,
            "momentum_3m": float(momentum_3m) if momentum_3m is not None else None,
            "momentum_6m": float(momentum_6m) if momentum_6m is not None else None,
            "momentum_12m": float(momentum_12m) if momentum_12m is not None else None,
            "adx": float(adx) if pd.notna(adx) else None,
            "above_200ema": bool(above_200ema) if above_200ema is not None else None,
            "ema_slope_20": float(ema_slope_20) if ema_slope_20 is not None else None,
            "week52_high": week52_high,
            "week52_low": week52_low,
            "pct_from_52w_high": float(pct_from_52w_high)
            if pct_from_52w_high is not None
            else None,
            "pct_from_52w_low": float(pct_from_52w_low)
            if pct_from_52w_low is not None
            else None,
            "resistance_level": resistance_level,
            "pct_from_resistance": float(pct_from_resistance)
            if pct_from_resistance is not None
            else None,
            "volume_breakout": bool(volume_breakout),
        }
