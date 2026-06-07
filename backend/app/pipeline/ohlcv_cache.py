import logging
import os
import tempfile
from pathlib import Path

import pandas as pd
import yfinance as yf

from app.pipeline.fetcher import fetch_stock_data, get_ticker_symbol

logger = logging.getLogger(__name__)

_OHLCV_SUBDIR = "ohlcv"


class OHLCVCache:
    """
    Persistent per-symbol OHLCV cache backed by Parquet files.

    Directory layout:
        <cache_dir>/ohlcv/<SYMBOL>.parquet
    """

    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = os.environ.get(
                "CACHE_DIR",
                str(Path(__file__).resolve().parent.parent.parent / "data"),
            )
        self._root = Path(cache_dir) / _OHLCV_SUBDIR
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Data Access                                                       #
    # ------------------------------------------------------------------ #

    def get(
        self,
        symbol: str,
        append_ns: bool = True,
        period: str = "3y",
        force_refresh: bool = False,
    ) -> pd.DataFrame | None:
        path = self._file_path(symbol)

        if not force_refresh and path.exists():
            try:
                cached_df = pd.read_parquet(path)

                # --- BACKFILL CHECK ---
                requested_start = self._get_requested_start(period)
                actual_start = cached_df.index[0]
                if hasattr(actual_start, "tzinfo") and actual_start.tzinfo is not None:
                    actual_start = actual_start.tz_convert(None)

                # If requested start is significantly older than actual start, backfill
                if requested_start < actual_start - pd.Timedelta(days=7):
                    cached_df = self._backfill_fetch(
                        symbol, cached_df, requested_start, append_ns, path
                    )
                # ----------------------

                if self._is_fresh(cached_df):
                    logger.info("ohlcv_cache: HIT %s (rows=%d)", symbol, len(cached_df))
                    return cached_df
                # Stale — incremental fetch handled in Task 4
                return self._incremental_fetch(symbol, cached_df, append_ns, path)
            except Exception as exc:
                logger.warning(
                    "ohlcv_cache: corrupt file for %s (%s), re-fetching", symbol, exc
                )
                path.unlink(missing_ok=True)

        # Cold miss or force_refresh
        return self._full_fetch(symbol, append_ns, period, path)

    def _get_requested_start(self, period: str) -> pd.Timestamp:
        """Converts yfinance period string into a naive pd.Timestamp."""
        now = pd.Timestamp.now().floor("D")
        if period == "ytd":
            return pd.Timestamp(now.year, 1, 1)
        if period == "max":
            return pd.Timestamp(1970, 1, 1)

        num_str = "".join(filter(str.isdigit, period))
        num = int(num_str) if num_str else 1
        unit = "".join(filter(str.isalpha, period)).lower()

        if unit == "d":
            return now - pd.DateOffset(days=num)
        if unit == "mo":
            return now - pd.DateOffset(months=num)
        if unit == "y":
            return now - pd.DateOffset(years=num)

        return now - pd.DateOffset(years=3)  # Default

    def _is_fresh(self, df: pd.DataFrame) -> bool:
        if df.empty:
            return False

        max_age_hours = int(os.environ.get("OHLCV_CACHE_MAX_AGE_HOURS", "24"))
        last_ts = df.index[-1]

        # tz_convert(None) converts to UTC first, then drops tz — correct behaviour.
        # tz_localize(None) would strip the label without converting, giving wrong times
        # if the stored timestamps are not already in UTC.
        if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is not None:
            last_ts = last_ts.tz_convert(None)

        # Ensure now is naive UTC to match last_ts
        now_utc_naive = pd.Timestamp.now(tz="UTC").tz_convert(None)
        age_hours = (now_utc_naive - last_ts).total_seconds() / 3600

        # 1. Standard age check
        if age_hours < max_age_hours:
            return True

        # 2. Weekend bypass: If it's Saturday (5) or Sunday (6) in UTC,
        # and we already have data from the most recent Friday (4), we are fresh.
        now_weekday = now_utc_naive.weekday()
        if now_weekday in [5, 6]:
            days_since_friday = now_weekday - 4
            expected_friday = (
                now_utc_naive - pd.Timedelta(days=days_since_friday)
            ).date()
            if last_ts.date() >= expected_friday:
                return True

        return False

    def _full_fetch(
        self, symbol: str, append_ns: bool, period: str, path: Path
    ) -> pd.DataFrame | None:
        logger.info("ohlcv_cache: MISS %s — full fetch", symbol)
        df, _ = fetch_stock_data(
            symbol, append_ns=append_ns, period=period, fetch_info=False
        )
        if df is None or df.empty:
            return None

        # Fix Timezone Fragility
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)

        self._write_atomic(df, path)
        return df

    def _backfill_fetch(
        self,
        symbol: str,
        cached_df: pd.DataFrame,
        requested_start: pd.Timestamp,
        append_ns: bool,
        path: Path,
    ) -> pd.DataFrame:
        actual_start = cached_df.index[0]
        if hasattr(actual_start, "tzinfo") and actual_start.tzinfo is not None:
            actual_start = actual_start.tz_convert(None)

        start_str = requested_start.strftime("%Y-%m-%d")
        # Go up to the start of current cache to bridge the gap
        end_str = (actual_start + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info(
            "ohlcv_cache: BACKFILL %s — %s → %s",
            symbol,
            start_str,
            end_str,
        )

        ticker_sym = get_ticker_symbol(symbol) if append_ns else symbol
        try:
            ticker = yf.Ticker(ticker_sym)
            head = ticker.history(start=start_str, end=end_str)
        except Exception as exc:
            logger.warning("ohlcv_cache: backfill fetch failed for %s: %s", symbol, exc)
            return cached_df

        if head is None or head.empty:
            logger.info("ohlcv_cache: no backfill data for %s", symbol)
            return cached_df

        if head.index.tz is not None:
            head.index = head.index.tz_convert(None)
        if cached_df.index.tz is not None:
            cached_df.index = cached_df.index.tz_convert(None)

        combined = pd.concat([head, cached_df])
        # deduplicate: keep original cached rows in case of overlap
        combined = combined[~combined.index.duplicated(keep="last")]
        combined.sort_index(inplace=True)

        self._write_atomic(combined, path)
        logger.info("ohlcv_cache: backfilled %d rows for %s", len(head), symbol)
        return combined

    def _incremental_fetch(
        self, symbol: str, cached_df: pd.DataFrame, append_ns: bool, path: Path
    ) -> pd.DataFrame | None:
        last_date = cached_df.index[-1]
        if hasattr(last_date, "tzinfo") and last_date.tzinfo is not None:
            last_date = last_date.tz_convert(None)

        start_str = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        end_str = (pd.Timestamp.now("UTC") + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info(
            "ohlcv_cache: STALE %s — incremental fetch %s → %s",
            symbol,
            start_str,
            end_str,
        )

        ticker_sym = get_ticker_symbol(symbol) if append_ns else symbol
        try:
            ticker = yf.Ticker(ticker_sym)
            tail = ticker.history(start=start_str, end=end_str)
        except Exception as exc:
            logger.warning(
                "ohlcv_cache: incremental fetch failed for %s: %s", symbol, exc
            )
            return cached_df

        if tail is None or tail.empty:
            logger.info("ohlcv_cache: no new data for %s, serving cached rows", symbol)
            return cached_df

        if tail.index.tz is not None:
            tail.index = tail.index.tz_convert(None)
        if cached_df.index.tz is not None:
            cached_df.index = cached_df.index.tz_convert(None)

        # --- SANITY CHECK (a) ---
        last_close = float(cached_df["Close"].iloc[-1])
        new_price = float(tail["Open"].iloc[0])

        gap_pct = abs((new_price - last_close) / last_close)
        if gap_pct > 0.20:
            logger.error(
                "ohlcv_cache: SANITY CHECK FAILED for %s. Gap is %.2f%% (Last Close: %.2f, New Open: %.2f). "
                "Potential bad data or unadjusted split. Skipping merge to prevent cache corruption.",
                symbol,
                gap_pct * 100,
                last_close,
                new_price,
            )
            return cached_df
        # ------------------------

        combined = pd.concat([cached_df, tail])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined.sort_index(inplace=True)

        self._write_atomic(combined, path)
        logger.info("ohlcv_cache: wrote %d rows for %s", len(combined), symbol)
        return combined

    def _write_atomic(self, df: pd.DataFrame, path: Path) -> None:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".parquet.tmp")
        os.close(fd)
        try:
            df.to_parquet(tmp)
            os.replace(tmp, path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise

    # ------------------------------------------------------------------ #
    # Management                                                        #
    # ------------------------------------------------------------------ #

    def stats(self) -> dict:
        files = list(self._root.glob("*.parquet"))
        if not files:
            return {"total_files": 0, "total_size_mb": 0.0, "oldest_file_date": None}
        total_bytes = sum(f.stat().st_size for f in files)
        oldest_mtime = min(f.stat().st_mtime for f in files)
        oldest_str = pd.Timestamp(oldest_mtime, unit="s").strftime("%Y-%m-%d")
        return {
            "total_files": len(files),
            "total_size_mb": round(total_bytes / 1_048_576, 4),
            "oldest_file_date": oldest_str,
        }

    def invalidate(self, symbol: str) -> None:
        path = self._file_path(symbol)
        if path.exists():
            path.unlink()
            logger.info("ohlcv_cache: invalidated %s", symbol)

    def invalidate_all(self) -> None:
        for path in self._root.glob("*.parquet"):
            path.unlink()
        logger.info("ohlcv_cache: invalidated all files")

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def exists(self, symbol: str) -> bool:
        return self._file_path(symbol).exists()

    def get_modified_time(self, symbol: str) -> float:
        path = self._file_path(symbol)
        if path.exists():
            return path.stat().st_mtime
        return 0.0

    def _file_path(self, symbol: str) -> Path:
        safe = (
            symbol.replace("^", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(":", "_")
        )
        return self._root / f"{safe}.parquet"
