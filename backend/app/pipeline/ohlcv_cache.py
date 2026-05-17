# backend/app/pipeline/ohlcv_cache.py
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
                os.path.join(os.path.dirname(__file__), "..", "..", "data"),
            )
        self._root = Path(cache_dir) / _OHLCV_SUBDIR
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _file_path(self, symbol: str) -> Path:
        safe = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self._root / f"{safe}.parquet"
