"""T5 — Adjust: apply corporate-action back-adjustment to unified raw OHLCV rows.

Takes the output of T3 (parse.py) and T4 (corporate_actions.py) and produces
fully-adjusted prices ready for T6 (universe.py) to add ``adv_20``:

  * Signal prices (open/high/low/close): split+bonus-adjusted only. Dividend
    adjustment is deliberately excluded — dividends must not influence momentum
    signals (01_DATA_LAYER.md §4 rationale).

  * close_tr: total-return-adjusted close (split+bonus+dividend reinvested).
    Used exclusively for portfolio P&L / equity-curve calculation.

  * close_raw: original unadjusted traded close, retained for audit and for
    verifying the factor round-trip:
        close_raw × adj_factor  = close
        close_raw × tr_factor   = close_tr

  * adj_factor / tr_factor: cumulative back-adjustment factors at each date.
    Convention (T4): latest date → 1.0; earlier dates < 1.0 wherever CAs exist.
    Built by split_bonus_factor_series / tr_factor_series (corporate_actions.py).

  * traded_value: sourced directly from the bhavcopy for in-scope rows. If a row
    carries null or zero (should not occur in practice for EQ rows, but handled
    defensively per 01 §5.4), falls back to close_raw × volume.

Output schema: all columns in store.PRICES_ADJUSTED_SCHEMA **except** adv_20.
T6 (universe.py) appends adv_20 from the 20-day rolling median of traded_value.
"""

import logging

import numpy as np
import pandas as pd

from app.data.bhavcopy.corporate_actions import (
    CA_EVENT_COLUMNS,
    split_bonus_factor_series,
    tr_factor_series,
)

logger = logging.getLogger(__name__)

# T5 intermediate schema — all PRICES_ADJUSTED_SCHEMA columns except adv_20 (T6).
ADJUSTED_INTERMEDIATE_COLUMNS: list[str] = [
    "isin",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "close_raw",
    "close_tr",
    "volume",
    "traded_value",
    "adj_factor",
    "tr_factor",
    "series",
]

_EMPTY_EVENTS: pd.DataFrame = pd.DataFrame(columns=CA_EVENT_COLUMNS)


def adjust_prices(
    raw_df: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Apply CA back-adjustment factors to unified raw OHLCV rows.

    Parameters
    ----------
    raw_df:
        Unified raw schema from T3 — (isin, symbol, date, open, high, low,
        close, volume, traded_value, series). The ``close`` column is the
        unadjusted traded close that becomes ``close_raw`` in the output.
    events:
        CA events from T4 ``CorporateActions.events`` — (isin, ex_date, type,
        ratio, dividend, symbol, subject). Pass an empty DataFrame (or
        ``_EMPTY_EVENTS``) when no corporate actions apply.

    Returns
    -------
    pd.DataFrame
        One row per (isin, date) with columns matching
        ``ADJUSTED_INTERMEDIATE_COLUMNS``. The ``adv_20`` column is absent —
        T6 (universe.py) appends it from the rolling traded_value window.
    """
    if raw_df.empty:
        return _empty_adjusted()

    # Index CA events by ISIN once for O(1) per-ISIN lookup.
    events_by_isin: dict[str, pd.DataFrame] = {}
    if not events.empty:
        for isin_key, grp in events.groupby("isin", sort=False):
            events_by_isin[str(isin_key)] = grp

    parts: list[pd.DataFrame] = []

    for isin, grp in raw_df.groupby("isin", sort=False):
        grp = grp.sort_values("date").reset_index(drop=True)
        dates = pd.DatetimeIndex(grp["date"])
        close_raw = grp["close"].to_numpy(dtype="float64")

        # CA events for this ISIN — absent ISIN gets empty events → factors = 1.0.
        isin_events = events_by_isin.get(str(isin), _EMPTY_EVENTS)

        adj_arr = split_bonus_factor_series(isin_events, dates).to_numpy(
            dtype="float64"
        )
        tr_arr = tr_factor_series(isin_events, dates, close_raw).to_numpy(
            dtype="float64"
        )

        # traded_value: prefer bhavcopy value; fall back to close_raw × volume (01 §5.4).
        tv = grp["traded_value"].to_numpy(dtype="float64").copy()
        bad = ~np.isfinite(tv) | (tv == 0)
        if bad.any():
            vol = grp["volume"].to_numpy(dtype="float64")
            tv[bad] = close_raw[bad] * vol[bad]
            logger.debug(
                "adjust_prices: %d traded_value null/zero rows for %s — filled from close_raw×volume",
                int(bad.sum()),
                isin,
            )

        parts.append(
            pd.DataFrame(
                {
                    "isin": grp["isin"].to_numpy(),
                    "symbol": grp["symbol"].to_numpy(),
                    "date": grp["date"].to_numpy(),
                    "open": grp["open"].to_numpy(dtype="float64") * adj_arr,
                    "high": grp["high"].to_numpy(dtype="float64") * adj_arr,
                    "low": grp["low"].to_numpy(dtype="float64") * adj_arr,
                    "close": close_raw * adj_arr,
                    "close_raw": close_raw,
                    "close_tr": close_raw * tr_arr,
                    "volume": grp["volume"].to_numpy(),
                    "traded_value": tv,
                    "adj_factor": adj_arr,
                    "tr_factor": tr_arr,
                    "series": grp["series"].to_numpy(),
                }
            )
        )

    if not parts:
        return _empty_adjusted()

    return pd.concat(parts, ignore_index=True)


def _empty_adjusted() -> pd.DataFrame:
    return pd.DataFrame(columns=ADJUSTED_INTERMEDIATE_COLUMNS)
