"""
benchmark.py — TRI loaders + regime price index (spec 03 T2).

Verified niftyindices download method (T0, 2026-06-15):
  - Endpoint (TRI):        POST getTotalReturnIndexString
  - Endpoint (price idx):  POST getHistoricaldatatabletoString
  - Warm-up GET required to establish session cookie before POST.
  - Dates in payload: "DD-Mon-YYYY" (e.g. "01-Jan-2024").

Public API
----------
load_tri(index_name, start, end, cache_dir, _fetch_fn) → pd.Series
    DatetimeIndex → TotalReturnsIndex float.  Pass one of the TRI_* constants.

load_price_index(start, end, cache_dir, _fetch_fn) → pd.Series
    DatetimeIndex → CLOSE float.  Nifty 50 price for regime 200-DMA.
    Distinct from TRI: do NOT feed into benchmark metrics (spec 03 §2.3).

align_benchmark(tri, date_from, trading_calendar, starting_capital) → pd.Series
    Calendar-align TRI, warmup-slice to date_from, rebase to starting_capital.

TRI constants (exact API name strings — case-sensitive)
--------------------------------------------------------
TRI_MOMENTUM_30        = "NIFTY200 Momentum 30"         # primary benchmark
TRI_MIDCAP_MOMENTUM_50 = "NIFTY MIDCAP150 Momentum 50"  # secondary
TRI_NIFTY_50           = "Nifty 50"                     # sanity floor

Cache
-----
Parquet files written atomically under cache_dir (default: backend/data/niftyindices/).
Second call with same (index_name, start, end) reads from disk — zero network.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRI_MOMENTUM_30 = "NIFTY200 Momentum 30"
TRI_MIDCAP_MOMENTUM_50 = "NIFTY MIDCAP150 Momentum 50"
TRI_NIFTY_50 = "Nifty 50"

_NIFTYINDICES_BASE = "https://www.niftyindices.com"
_TRI_ENDPOINT = f"{_NIFTYINDICES_BASE}/Backpage.aspx/getTotalReturnIndexString"
_PRICE_ENDPOINT = f"{_NIFTYINDICES_BASE}/Backpage.aspx/getHistoricaldatatabletoString"
_REFERER = f"{_NIFTYINDICES_BASE}/reports/historical-data"

# Default cache location (gitignored: backend/data/ is in .gitignore).
_DEFAULT_CACHE_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "niftyindices"
)

# Type alias for the injectable fetch function.
# Signature: (index_name: str, start: str, end: str) -> list[dict]
# start/end are "DD-Mon-YYYY" strings; returns the raw row list from the API.
FetchFn = Callable[[str, str, str], list[dict]]


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

_MONTH_ABBR = {
    "Jan": "01",
    "Feb": "02",
    "Mar": "03",
    "Apr": "04",
    "May": "05",
    "Jun": "06",
    "Jul": "07",
    "Aug": "08",
    "Sep": "09",
    "Oct": "10",
    "Nov": "11",
    "Dec": "12",
}


def _api_date(d: date | str) -> str:
    """Convert a date or ISO string to the niftyindices API format: DD-Mon-YYYY."""
    if isinstance(d, str):
        d = pd.Timestamp(d).date()
    return d.strftime("%d-") + d.strftime("%b-") + d.strftime("%Y")


def _parse_api_date(s: str) -> pd.Timestamp:
    """Parse 'DD Mon YYYY' (space-separated, as returned in API rows) to Timestamp."""
    parts = s.strip().split()
    if len(parts) == 3:
        day, mon, year = parts
        month = _MONTH_ABBR.get(mon, mon)
        return pd.Timestamp(f"{year}-{month}-{day}")
    # Fallback: let pandas try
    return pd.Timestamp(s)


def _slug(index_name: str) -> str:
    """Convert an index name to a safe filename slug."""
    return re.sub(r"[^a-z0-9]+", "_", index_name.lower()).strip("_")


# ---------------------------------------------------------------------------
# Network fetch (real implementation)
# ---------------------------------------------------------------------------


def _make_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update(
        {
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": _REFERER,
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
    )
    # Warm-up GET to establish session cookie (required by niftyindices).
    try:
        sess.get(_NIFTYINDICES_BASE, timeout=10)
    except requests.RequestException as exc:
        log.warning("niftyindices warm-up GET failed: %s", exc)
    return sess


_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SECS = [5, 15]  # delay before attempt 2, then attempt 3


def _call_with_retry(fn: Callable[[], list[dict]]) -> list[dict]:
    """Call fn(), retrying up to _RETRY_ATTEMPTS times on transient network errors."""
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return fn()
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            delay = _RETRY_BACKOFF_SECS[attempt]
            log.warning(
                "niftyindices fetch transient error (attempt %d/%d): %s — retrying in %ds",
                attempt + 1,
                _RETRY_ATTEMPTS,
                exc,
                delay,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable")  # mypy


def _fetch_tri(index_name: str, start: str, end: str) -> list[dict]:
    """Fetch TRI rows from niftyindices. Returns raw row dicts."""
    sess = _make_session()
    cinfo = json.dumps(
        {
            # The API's `name` field is the index name itself, not the method
            # name — sending the method name returns {"d":"[]"} silently.
            "name": index_name,
            "startDate": start,
            "endDate": end,
            "indexName": index_name,
        }
    )

    def _do() -> list[dict]:
        resp = sess.post(_TRI_ENDPOINT, json={"cinfo": cinfo}, timeout=30)
        resp.raise_for_status()
        return json.loads(resp.json()["d"])

    return _call_with_retry(_do)


def _fetch_price(index_name: str, start: str, end: str) -> list[dict]:
    """Fetch price index (OHLC) rows from niftyindices. Returns raw row dicts."""
    sess = _make_session()
    cinfo = json.dumps(
        {
            # The API's `name` field is the index name itself, not the method
            # name — sending the method name returns {"d":"[]"} silently.
            "name": index_name,
            "startDate": start,
            "endDate": end,
            "indexName": index_name,
        }
    )

    def _do() -> list[dict]:
        resp = sess.post(_PRICE_ENDPOINT, json={"cinfo": cinfo}, timeout=30)
        resp.raise_for_status()
        return json.loads(resp.json()["d"])

    return _call_with_retry(_do)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _rows_to_tri_series(rows: list[dict]) -> pd.Series:
    """Parse raw TRI row dicts into a sorted DatetimeIndex → float Series."""
    records = []
    for row in rows:
        dt = _parse_api_date(row["Date"])
        val = float(row["TotalReturnsIndex"])
        records.append((dt, val))
    if not records:
        return pd.Series(dtype=float)
    idx, vals = zip(*records)
    s = pd.Series(vals, index=pd.DatetimeIndex(idx), name="tri")
    return s.sort_index()


def _rows_to_price_series(rows: list[dict]) -> pd.Series:
    """Parse raw price index row dicts into a sorted DatetimeIndex → float Series."""
    records = []
    for row in rows:
        dt = _parse_api_date(row["HistoricalDate"])
        val = float(row["CLOSE"])
        records.append((dt, val))
    if not records:
        return pd.Series(dtype=float)
    idx, vals = zip(*records)
    s = pd.Series(vals, index=pd.DatetimeIndex(idx), name="price_close")
    return s.sort_index()


# ---------------------------------------------------------------------------
# Atomic cache write (borrowed pattern from OHLCVCache)
# ---------------------------------------------------------------------------


def _write_atomic(series: pd.Series, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".parquet.tmp")
    os.close(fd)
    try:
        series.to_frame().to_parquet(tmp)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_cache(path: Path) -> pd.Series:
    df = pd.read_parquet(path)
    return df.iloc[:, 0]


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_tri(
    index_name: str,
    start: date | str,
    end: date | str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
    _fetch_fn: FetchFn | None = None,
) -> pd.Series:
    """Load a TRI series (DatetimeIndex → float), caching to disk.

    Args:
        index_name: One of TRI_MOMENTUM_30, TRI_MIDCAP_MOMENTUM_50, TRI_NIFTY_50.
        start: Start date (inclusive).
        end: End date (inclusive).
        cache_dir: Directory for parquet cache files (gitignored).
        _fetch_fn: Injectable fetch; defaults to the real niftyindices POST.
                   Pass a stub in tests to avoid live network calls.

    Returns:
        Sorted DatetimeIndex → TotalReturnsIndex float.
    """
    start_str = _api_date(start)
    end_str = _api_date(end)
    slug = _slug(index_name)
    cache_key = f"{slug}_{start_str.replace('-', '')}_{end_str.replace('-', '')}"
    cache_path = Path(cache_dir) / f"{cache_key}.parquet"

    if cache_path.exists():
        log.debug("benchmark: TRI cache hit %s", cache_path.name)
        return _read_cache(cache_path)

    fetch = _fetch_fn or _fetch_tri
    log.info("benchmark: fetching TRI %s [%s → %s]", index_name, start_str, end_str)
    rows = fetch(index_name, start_str, end_str)
    series = _rows_to_tri_series(rows)
    if series.empty:
        # Never persist an empty fetch — a transient failure or a bad index
        # name would otherwise poison the cache forever (every later load
        # would hit the empty parquet). Fail loud and retry next time.
        raise ValueError(
            f"benchmark: TRI fetch for {index_name!r} [{start_str} → {end_str}] "
            "returned zero rows — not caching. Check the index name / network."
        )
    _write_atomic(series, cache_path)
    log.info("benchmark: cached %d TRI rows → %s", len(series), cache_path.name)
    return series


def load_price_index(
    start: date | str,
    end: date | str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
    _fetch_fn: FetchFn | None = None,
) -> pd.Series:
    """Load the Nifty 50 price index (DatetimeIndex → CLOSE float), caching to disk.

    This is the regime overlay signal (spec 03 §2.3) — distinct from TRI.
    Feed into engine.run(index_prices=...) for the 200-DMA regime filter.

    Returns:
        Sorted DatetimeIndex → CLOSE float.
    """
    index_name = "Nifty 50"
    start_str = _api_date(start)
    end_str = _api_date(end)
    slug = "price_" + _slug(index_name)
    cache_key = f"{slug}_{start_str.replace('-', '')}_{end_str.replace('-', '')}"
    cache_path = Path(cache_dir) / f"{cache_key}.parquet"

    if cache_path.exists():
        log.debug("benchmark: price index cache hit %s", cache_path.name)
        return _read_cache(cache_path)

    fetch = _fetch_fn or _fetch_price
    log.info(
        "benchmark: fetching price index %s [%s → %s]", index_name, start_str, end_str
    )
    rows = fetch(index_name, start_str, end_str)
    series = _rows_to_price_series(rows)
    if series.empty:
        # Never persist an empty fetch — see load_tri for the rationale.
        raise ValueError(
            f"benchmark: price fetch for {index_name!r} [{start_str} → {end_str}] "
            "returned zero rows — not caching. Check the index name / network."
        )
    _write_atomic(series, cache_path)
    log.info("benchmark: cached %d price rows → %s", len(series), cache_path.name)
    return series


# ---------------------------------------------------------------------------
# Alignment + rebase
# ---------------------------------------------------------------------------


def align_benchmark(
    tri: pd.Series,
    date_from: date | pd.Timestamp,
    trading_calendar: list[pd.Timestamp],
    starting_capital: float,
) -> pd.Series:
    """Align a TRI series to the backtest window, warmup-slice, and rebase.

    Steps (spec 03 §2.2):
      1. Forward-fill TRI onto the trading_calendar (handles index holidays).
      2. Slice to dates >= date_from (drops warmup; the v1 dilution bug).
      3. Rebase: value_t = (tri_t / tri_at_date_from) * starting_capital.

    Args:
        tri: DatetimeIndex → TRI float (from load_tri).
        date_from: First live-trading date (NOT the warmup start).
        trading_calendar: The engine's sorted list of trading Timestamps.
        starting_capital: Starting portfolio ₹ to rebase to.

    Returns:
        DatetimeIndex → ₹ equity-equivalent (same scale as strategy equity curve).
        Daily returns from this series are apples-to-apples with strategy returns.
    """
    date_from_ts = pd.Timestamp(date_from)
    cal_index = pd.DatetimeIndex(trading_calendar)

    # Forward-fill TRI onto the trading calendar.
    # combine_first + ffill aligns to cal_index, filling gaps with last known value.
    aligned = tri.reindex(cal_index.union(tri.index)).ffill().reindex(cal_index)

    # Warmup-slice: keep only dates >= date_from.
    aligned = aligned[aligned.index >= date_from_ts]

    if aligned.empty or pd.isna(aligned.iloc[0]):
        raise ValueError(
            f"align_benchmark: no TRI data at or after date_from={date_from_ts.date()}. "
            "Extend the TRI fetch range to cover the backtest start."
        )

    # Rebase to starting_capital at date_from.
    base_value = aligned.iloc[0]
    rebased = (aligned / base_value) * starting_capital
    return rebased
