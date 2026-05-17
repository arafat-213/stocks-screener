import os
import logging
import tempfile
from pathlib import Path
import pandas as pd

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
                if self._is_fresh(cached_df):
                    logger.info("ohlcv_cache: HIT %s (rows=%d)", symbol, len(cached_df))
                    return cached_df
                # Stale — incremental fetch handled in Task 4
                return self._incremental_fetch(symbol, cached_df, append_ns, path)
            except Exception as exc:
                logger.warning("ohlcv_cache: corrupt file for %s (%s), re-fetching", symbol, exc)
                path.unlink(missing_ok=True)

        # Cold miss or force_refresh
        return self._full_fetch(symbol, append_ns, period, path)

    def _is_fresh(self, df: pd.DataFrame) -> bool:
        if df.empty:
            return False
        max_age_hours = int(os.environ.get("OHLCV_CACHE_MAX_AGE_HOURS", "24"))
        last_ts = df.index[-1]
        if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is not None:
            last_ts = last_ts.tz_localize(None)
        age_hours = (pd.Timestamp.utcnow().tz_localize(None) - last_ts).total_seconds() / 3600
        return age_hours < max_age_hours

    def _full_fetch(
        self, symbol: str, append_ns: bool, period: str, path: Path
    ) -> pd.DataFrame | None:
        from app.pipeline.fetcher import fetch_stock_data
        logger.info("ohlcv_cache: MISS %s — full fetch", symbol)
        df, _ = fetch_stock_data(symbol, append_ns=append_ns, period=period, fetch_info=False)
        if df is None or df.empty:
            return None
        self._write_atomic(df, path)
        return df

    def _incremental_fetch(
        self, symbol: str, cached_df: pd.DataFrame, append_ns: bool, path: Path
    ) -> pd.DataFrame | None:
        # Stub for Task 4
        return cached_df

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

    def _file_path(self, symbol: str) -> Path:
        safe = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self._root / f"{safe}.parquet"
