import datetime
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_ta_classic  # noqa
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import TechnicalSignal
from app.db.session import SessionLocal
from app.pipeline.utils import resample_ohlcv

# Setup basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
CACHE_DIR = os.environ.get(
    "CACHE_DIR", str(Path(__file__).resolve().parent.parent / "data")
)
OHLCV_DIR = Path(CACHE_DIR) / "ohlcv"
BATCH_SIZE = 5000  # Number of rows to bulk insert at a time


def calculate_historical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies the same pandas-ta logic from scorer.py but across the entire dataframe.
    """
    if len(df) < 14:  # Minimum length for most indicators
        return pd.DataFrame()

    df = df.copy()

    # EMAs
    df.ta.ema(length=5, append=True)
    df.ta.ema(length=13, append=True)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=26, append=True)
    df.ta.ema(length=200, append=True)

    # MACD & RSI
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.rsi(length=14, append=True)

    # ATR & ADX
    df.ta.atr(length=14, append=True)
    df.ta.adx(length=14, append=True)

    # Volume SMA
    if "Volume" in df.columns:
        df["VOL_SMA_20"] = df["Volume"].rolling(window=20).mean()
    else:
        df["VOL_SMA_20"] = np.nan

    # Momentum (1m, 3m, 6m, 12m) assuming approx trading days (21, 63, 126, 252)
    df["momentum_1m"] = df["Close"].pct_change(periods=21) * 100
    df["momentum_3m"] = df["Close"].pct_change(periods=63) * 100
    df["momentum_6m"] = df["Close"].pct_change(periods=126) * 100
    df["momentum_12m"] = df["Close"].pct_change(periods=252) * 100

    # 52 Week High/Low (approx 252 trading days)
    df["week52_high"] = df["High"].rolling(window=252).max()
    df["week52_low"] = df["Low"].rolling(window=252).min()
    df["pct_from_52w_high"] = (
        (df["Close"] - df["week52_high"]) / df["week52_high"]
    ) * 100
    df["pct_from_52w_low"] = ((df["Close"] - df["week52_low"]) / df["week52_low"]) * 100

    # EMA Slope 20
    if "EMA_20" in df.columns:
        df["ema_slope_20"] = (df["EMA_20"] - df["EMA_20"].shift(5)) / 5
    else:
        df["ema_slope_20"] = np.nan

    # Resistance: Highest close in the year prior to the last 20 bars (240 bar window)
    if len(df) >= 260:
        df["res_rolling"] = df["Close"].shift(20).rolling(window=240).max()
        df["pct_from_resistance"] = (df["Close"] / df["res_rolling"] - 1) * 100
    else:
        df["pct_from_resistance"] = np.nan

    # Booleans/Signals
    if "EMA_200" in df.columns:
        df["above_200ema"] = df["Close"] > df["EMA_200"]
    else:
        df["above_200ema"] = False

    # MACD crosses
    if "MACD_12_26_9" in df.columns and "MACDs_12_26_9" in df.columns:
        df["macd_cross_up"] = (df["MACD_12_26_9"] > df["MACDs_12_26_9"]) & (
            df["MACD_12_26_9"].shift(1) <= df["MACDs_12_26_9"].shift(1)
        )
        df["macd_cross_down"] = (df["MACD_12_26_9"] < df["MACDs_12_26_9"]) & (
            df["MACD_12_26_9"].shift(1) >= df["MACDs_12_26_9"].shift(1)
        )
    else:
        df["macd_cross_up"] = False
        df["macd_cross_down"] = False

    # Setup score defaults to map later
    df["entry_score"] = 0.0

    # Forward fill NaNs created by rolling windows where appropriate, or leave as NaN

    return df


def generate_signals(df: pd.DataFrame, symbol: str, timeframe: str) -> list:
    """
    Converts a processed DataFrame into a list of TechnicalSignal dictionaries for bulk insert.
    """
    signals = []

    if "EMA_26" not in df.columns:
        return signals

    valid_df = df[df["EMA_26"].notna()].copy()

    if valid_df.empty:
        return signals

    for i in range(1, len(valid_df)):
        date = valid_df.index[i]
        row = valid_df.iloc[i]
        prev = valid_df.iloc[i - 1]

        score = 0.0
        ema_signal = "neutral"
        volume_signal = "neutral"
        rsi_signal = "neutral"
        is_bullish = False

        ema5 = row.get("EMA_5")
        ema13 = row.get("EMA_13")
        ema20 = row.get("EMA_20")
        ema26 = row.get("EMA_26")
        price = row.get("Close")
        macd_line = row.get("MACD_12_26_9")
        signal_line = row.get("MACDs_12_26_9")
        rsi = row.get("RSI_14")
        prev_rsi = prev.get("RSI_14")

        # Volume Breakout
        volume_breakout = False
        volume = row.get("Volume")
        sma20_vol = row.get("VOL_SMA_20")
        is_green = row.get("Close", 0) > row.get("Open", float("inf"))
        if pd.notna(volume) and pd.notna(sma20_vol):
            if volume > 2.0 * sma20_vol and is_green:
                volume_breakout = True

        if timeframe == "D":
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
                score += 20
                ema_signal = "bullish_cross"
            elif pullback_to_ema20:
                score += 15
                ema_signal = "bullish_pullback"
            elif (
                pd.notna(ema5)
                and pd.notna(ema13)
                and pd.notna(ema26)
                and ema5 > ema13 > ema26
                and price > ema26
            ):
                score += 8
                ema_signal = "bullish"
            elif (
                pd.notna(ema5)
                and pd.notna(ema13)
                and pd.notna(ema26)
                and ema5 < ema13 < ema26
            ):
                ema_signal = "bearish"

            # MACD
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
                    score += 8
                elif fresh_macd_cross:
                    score += 15
                elif macd_line > signal_line and macd_line > 0:
                    score += 10
                elif macd_line > signal_line and macd_line < 0:
                    score += 5

            # RSI
            if pd.notna(rsi) and pd.notna(prev_rsi):
                start_idx = max(0, i - 5)
                recent_rsi = valid_df["RSI_14"].iloc[start_idx : i + 1]
                was_oversold = any(recent_rsi < 30)
                recovering = (
                    was_oversold and rsi > 30 and pd.notna(ema20) and price > ema20
                )
                crossing_50 = prev_rsi <= 50 and rsi > 50

                if recovering and fresh_ema_cross:
                    score += 15
                    rsi_signal = "bullish_recovery_confirmed"
                elif recovering:
                    score += 15
                    rsi_signal = "bullish_recovery"
                elif crossing_50:
                    score += 10
                    rsi_signal = "bullish_crossing"
                elif 50 < rsi <= 65:
                    score += 5
                    rsi_signal = "bullish_strong"
                elif 65 < rsi <= 68:
                    rsi_signal = "bullish_extended"

            # Volume Score
            if volume_breakout:
                score += 15
                volume_signal = "bullish"

            # Trend Quality
            trend_pts = 0
            adx = row.get("ADX_14")
            if pd.notna(adx):
                if adx >= 35:
                    trend_pts += 3
                elif adx >= 25:
                    trend_pts += 2
                elif adx >= 20:
                    trend_pts += 1
            momentum_3m = row.get("momentum_3m")
            if pd.notna(momentum_3m):
                if momentum_3m > 15:
                    trend_pts += 2
                elif momentum_3m > 5:
                    trend_pts += 1
            score += min(trend_pts, 5)

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
                and rsi > 45
            )

        elif timeframe == "W":
            is_bullish = (
                pd.notna(rsi) and rsi > 50 and pd.notna(ema26) and price > ema26
            )
            score = 70.0 if is_bullish else 0.0
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
            score = 70.0 if is_bullish else 0.0
            ema_signal = "bullish" if is_bullish else "neutral"

        # Consolidation check (approximate lookback without circular dependency)
        is_consolidating = None
        if timeframe == "D" and i >= 15:
            # Replicating engine._is_consolidating logic
            lookback_df = valid_df.iloc[i - 15 : i + 1]
            max_h = lookback_df["High"].max()
            min_l = lookback_df["Low"].min()
            if min_l > 0:
                range_pct = ((max_h - min_l) / min_l) * 100
                is_consolidating = bool(range_pct <= 12.0)

        signal_dict = {
            "symbol": symbol,
            "date": date.to_pydatetime() if hasattr(date, "to_pydatetime") else date,
            "timeframe": timeframe,
            "is_bullish": bool(is_bullish),
            "entry_score": float(score),
            "rsi": float(rsi) if pd.notna(rsi) else 0.0,
            "macd": float(macd_line) if pd.notna(macd_line) else 0.0,
            "ema_signal": ema_signal,
            "volume_signal": volume_signal,
            "rsi_signal": rsi_signal,
            "atr": float(row.get("ATRr_14")) if pd.notna(row.get("ATRr_14")) else None,
            "close_price": float(price) if pd.notna(price) else None,
            "pct_from_resistance": float(row.get("pct_from_resistance"))
            if pd.notna(row.get("pct_from_resistance"))
            else None,
            "momentum_1m": float(row.get("momentum_1m"))
            if pd.notna(row.get("momentum_1m"))
            else None,
            "momentum_3m": float(row.get("momentum_3m"))
            if pd.notna(row.get("momentum_3m"))
            else None,
            "momentum_6m": float(row.get("momentum_6m"))
            if pd.notna(row.get("momentum_6m"))
            else None,
            "momentum_12m": float(row.get("momentum_12m"))
            if pd.notna(row.get("momentum_12m"))
            else None,
            "adx": float(row.get("ADX_14")) if pd.notna(row.get("ADX_14")) else None,
            "above_200ema": bool(row.get("above_200ema"))
            if pd.notna(row.get("above_200ema"))
            else None,
            "ema_slope_20": float(row.get("ema_slope_20"))
            if pd.notna(row.get("ema_slope_20"))
            else None,
            "ema5_level": float(ema5) if pd.notna(ema5) else None,
            "ema13_level": float(ema13) if pd.notna(ema13) else None,
            "ema20_level": float(ema20) if pd.notna(ema20) else None,
            "ema26_level": float(ema26) if pd.notna(ema26) else None,
            "pct_from_52w_high": float(row.get("pct_from_52w_high"))
            if pd.notna(row.get("pct_from_52w_high"))
            else None,
            "pct_from_52w_low": float(row.get("pct_from_52w_low"))
            if pd.notna(row.get("pct_from_52w_low"))
            else None,
            "week52_high": float(row.get("week52_high"))
            if pd.notna(row.get("week52_high"))
            else None,
            "week52_low": float(row.get("week52_low"))
            if pd.notna(row.get("week52_low"))
            else None,
            "volume_breakout": volume_breakout,
            "is_consolidating": is_consolidating,
            "scored_at": datetime.datetime.now(datetime.timezone.utc),
        }

        signals.append(TechnicalSignal(**signal_dict))

    return signals


def backfill_history():
    """
    Iterates over all Parquet files, calculates historical signals, and bulk inserts them.
    """
    if not OHLCV_DIR.exists():
        logger.error(f"OHLCV directory not found at {OHLCV_DIR}")
        return

    parquet_files = list(OHLCV_DIR.glob("*.parquet"))
    total_files = len(parquet_files)

    logger.info(
        f"Found {total_files} symbols in cache. Starting historical backfill..."
    )

    db: Session = SessionLocal()

    try:
        for idx, file_path in enumerate(parquet_files, 1):
            symbol = (
                file_path.stem.replace("_", "^")
                if "_" in file_path.stem and "NS" not in file_path.stem
                else file_path.stem.replace("_", "/")
            )

            # Check if this symbol already has a deep history (e.g. > 100 records for 'D')
            existing_count = (
                db.query(func.count(TechnicalSignal.id))
                .filter(
                    TechnicalSignal.symbol == symbol, TechnicalSignal.timeframe == "D"
                )
                .scalar()
            )

            if existing_count > 500:  # Assuming they already have >2 years of history
                logger.info(
                    f"[{idx}/{total_files}] Skipping {symbol} - already has {existing_count} daily signals."
                )
                continue

            logger.info(f"[{idx}/{total_files}] Processing {symbol}...")

            try:
                df = pd.read_parquet(file_path)
                if df.empty:
                    continue

                # Ensure datetime index
                if hasattr(df.index, "tzinfo") and df.index.tzinfo is not None:
                    df.index = df.index.tz_localize(None)

                # Calculate Daily
                df_daily = calculate_historical_indicators(df)
                signals_d = generate_signals(df_daily, symbol, "D")

                # Calculate Weekly
                df_weekly_raw = resample_ohlcv(df, "W")
                df_weekly = calculate_historical_indicators(df_weekly_raw)
                signals_w = generate_signals(df_weekly, symbol, "W")

                # Calculate Monthly
                df_monthly_raw = resample_ohlcv(df, "ME")
                df_monthly = calculate_historical_indicators(df_monthly_raw)
                signals_m = generate_signals(df_monthly, symbol, "M")

                all_signals = signals_d + signals_w + signals_m

                # Delete any existing records for this symbol to avoid UniqueConstraint errors
                # and ensure a clean backfill
                db.query(TechnicalSignal).filter(
                    TechnicalSignal.symbol == symbol
                ).delete()

                # Bulk save
                db.bulk_save_objects(all_signals)
                db.commit()

                logger.info(
                    f"  -> Inserted {len(signals_d)} D, {len(signals_w)} W, {len(signals_m)} M records."
                )

            except Exception as e:
                db.rollback()
                logger.error(f"  -> Error processing {symbol}: {e}")

    finally:
        db.close()
        logger.info("Historical backfill complete.")


if __name__ == "__main__":
    backfill_history()
