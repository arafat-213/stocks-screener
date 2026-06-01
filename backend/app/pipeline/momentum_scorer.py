from typing import Optional

import pandas as pd
import pandas_ta_classic  # noqa: F401


class MomentumScorer:
    def __init__(self):
        pass

    def to_float(self, val) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
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

        return df

    def calculate_score(
        self, df: pd.DataFrame, timeframe: str = "D", i: int = -1, skip_ta: bool = False
    ) -> dict:
        """
        Calculates technical sub-score (Max 100 pts)
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
            df = self.calculate_technical_indicators(df)

        if i < 0:
            i = len(df) + i

        # Safety check
        if i < 0 or i >= len(df):
            return self.calculate_score(pd.DataFrame())

        latest = df.iloc[i]
        prev = df.iloc[i - 1] if i > 0 else latest

        score = 0
        ema_signal = "neutral"
        volume_signal = "neutral"
        rsi_signal = "neutral"
        is_bullish = False

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

        # Momentum (lookback from full df)
        momentum_1m = (
            ((price / df["Close"].iloc[i - 21] - 1) * 100) if i >= 21 else None
        )
        momentum_3m = (
            ((price / df["Close"].iloc[i - 63] - 1) * 100) if i >= 63 else None
        )
        momentum_6m = (
            ((price / df["Close"].iloc[i - 126] - 1) * 100) if i >= 126 else None
        )
        momentum_12m = (
            ((price / df["Close"].iloc[i - 252] - 1) * 100) if i >= 252 else None
        )

        # Above 200 EMA
        above_200ema = (price > ema200) if pd.notna(ema200) else None

        # 52-Week High/Low and Resistance
        week52_high = None
        week52_low = None
        pct_from_52w_high = None
        pct_from_52w_low = None
        resistance_level = None
        pct_from_resistance = None

        if i >= 251:
            recent_252 = df["Close"].iloc[i - 251 : i + 1]
            week52_high = float(recent_252.max())
            week52_low = float(recent_252.min())
            pct_from_52w_high = (price / week52_high - 1) * 100
            pct_from_52w_low = (price / week52_low - 1) * 100

        # Resistance: Highest close in the year prior to the last 20 bars
        if i >= 259:
            resistance_level = float(df["Close"].iloc[i - 259 : i - 19].max())
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
                    score += 28.5
                    ema_signal = "bullish_cross"
                elif pullback_to_ema20:
                    score += 21.5
                    ema_signal = "bullish_pullback"
                elif (
                    pd.notna(ema5)
                    and pd.notna(ema13)
                    and pd.notna(ema26)
                    and ema5 > ema13 > ema26
                    and price > ema26
                ):
                    score += 11.5
                    ema_signal = "bullish"
                elif (
                    pd.notna(ema5)
                    and pd.notna(ema13)
                    and pd.notna(ema26)
                    and ema5 < ema13 < ema26
                ):
                    ema_signal = "bearish"

                # 2. MACD (21.5 pts — decoupled from EMA cross)
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
                        score += 11.5
                    elif fresh_macd_cross:
                        score += 21.5
                    elif macd_line > signal_line and macd_line > 0:
                        score += 14.5
                    elif macd_line > signal_line and macd_line < 0:
                        score += 7.0

                # 3. RSI 14 (21.5 pts)
                if pd.notna(rsi) and pd.notna(prev_rsi):
                    # Check for recovery in last 5 days
                    recent_rsi = df["RSI_14"].iloc[max(0, i - 4) : i + 1]
                    was_oversold = any(recent_rsi < 30)

                    recovering = (
                        was_oversold and rsi > 30 and pd.notna(ema20) and price > ema20
                    )
                    crossing_50 = prev_rsi <= 50 and rsi > 50

                    if recovering and fresh_ema_cross:
                        score += 21.5
                        rsi_signal = "bullish_recovery_confirmed"
                    elif recovering:
                        score += 21.5
                        rsi_signal = "bullish_recovery"
                    elif crossing_50:
                        score += 14.5
                        rsi_signal = "bullish_crossing"
                    elif 50 < rsi <= 65:
                        score += 7.0
                        rsi_signal = "bullish_strong"
                    elif 65 < rsi <= 68:
                        rsi_signal = "bullish_extended"

                # 4. Volume (21.5 pts)
                if volume_breakout:
                    score += 21.5
                    volume_signal = "bullish"

                # 5. Trend Quality: ADX + 3-Month Momentum (max 7 pts)
                trend_pts = 0
                if pd.notna(adx):
                    if adx >= 35:
                        trend_pts += 4.5
                    elif adx >= 25:
                        trend_pts += 3.0
                    elif adx >= 20:
                        trend_pts += 1.5
                if momentum_3m is not None:
                    if momentum_3m > 15:
                        trend_pts += 3.0
                    elif momentum_3m > 5:
                        trend_pts += 1.5
                score += min(trend_pts, 7.0)

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
                    and rsi > 35
                )

                # Hard Filters applied directly to score and is_bullish
                if not above_200ema:
                    score = 0
                    is_bullish = False
                if pd.notna(rsi) and rsi > 80:
                    score = 0

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

        # Hard Filter: RSI must not be overbought (> 80)
        if rsi is not None and rsi > 80:
            score = 0.0

        # Ensure final score is in range 0-100
        score = max(0.0, min(100.0, score))

        return {
            "score": float(score),
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
