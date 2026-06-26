"""short_rate.py — the defensive-asset (liquid / overnight fund) level series.

v5/00 §3a: the un-deployed ``(1 − f)`` of capital earns a **real short-rate** series,
not a flat 0%. We use the **Nifty 1D Rate Index** (NSE's overnight-rate index — the
canonical liquid/overnight-fund proxy). It is published on the niftyindices *price*
endpoint as a cumulative CLOSE level; its ``pct_change`` is the realised daily
overnight return, so it slots into the overlay simulator's defensive leg exactly like
the equity TRI slots into the equity leg.

Why this is "real, not a thumb on the scale" (v5/00 §3a): the defensive yield enters
**both** the overlay and the static-matched comparator (§5), so its *level* cancels
from the binding comparison — it only ever helps the overlay against the *reported*
buy-and-hold. A 0%-cash floor is kept as a reported diagnostic (§6).

Loader mirrors ``benchmark.load_price_index`` exactly (injectable ``_fetch_fn``,
atomic parquet cache, fail-loud-on-empty) — **no live API in pytest** (CLAUDE.md §5):
tests inject a stub fetch; the one-off real fetch is a cache-miss script run.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from app.backtest_v2.benchmark import (
    _DEFAULT_CACHE_DIR,
    FetchFn,
    _api_date,
    _fetch_price,
    _read_cache,
    _rows_to_price_series,
    _slug,
    _write_atomic,
)

log = logging.getLogger(__name__)

# Exact niftyindices index name (case-insensitive on their side; price endpoint).
DEFENSIVE_INDEX_NAME = "Nifty 1D Rate Index"


def load_defensive_index(
    start: date | str,
    end: date | str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
    _fetch_fn: FetchFn | None = None,
) -> pd.Series:
    """Load the Nifty 1D Rate Index CLOSE level (DatetimeIndex → float), caching to disk.

    Mirrors ``benchmark.load_price_index`` (different index name + cache slug). The
    returned level series compounds the overnight rate; daily defensive return =
    ``series.pct_change()``.

    Args:
        start/end: inclusive date range.
        cache_dir: parquet cache directory (gitignored).
        _fetch_fn: injectable fetch; defaults to the real niftyindices price POST.
                   Pass a stub in tests (no live network).
    """
    start_str = _api_date(start)
    end_str = _api_date(end)
    slug = "rate_" + _slug(DEFENSIVE_INDEX_NAME)
    cache_key = f"{slug}_{start_str.replace('-', '')}_{end_str.replace('-', '')}"
    cache_path = Path(cache_dir) / f"{cache_key}.parquet"

    if cache_path.exists():
        log.debug("short_rate: cache hit %s", cache_path.name)
        return _read_cache(cache_path)

    fetch = _fetch_fn or _fetch_price
    log.info(
        "short_rate: fetching %s [%s → %s]", DEFENSIVE_INDEX_NAME, start_str, end_str
    )
    rows = fetch(DEFENSIVE_INDEX_NAME, start_str, end_str)
    series = _rows_to_price_series(rows)
    if series.empty:
        # Never persist an empty fetch — see benchmark.load_tri for the rationale.
        raise ValueError(
            f"short_rate: fetch for {DEFENSIVE_INDEX_NAME!r} [{start_str} → {end_str}] "
            "returned zero rows — not caching. Check the index name / network."
        )
    _write_atomic(series, cache_path)
    log.info("short_rate: cached %d rows → %s", len(series), cache_path.name)
    return series
