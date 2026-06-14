"""T6 — Universe membership + liquidity: emit point-in-time universe_membership
and the adv_20 series with no lookahead.

Takes the output of T5 (adjust.py) and produces three artefacts:

  1. prices: PRICES_ADJUSTED_SCHEMA DataFrame — T5 output with ``adv_20``
     appended, completing the canonical schema.

  2. membership: UNIVERSE_MEMBERSHIP_SCHEMA — one row per (isin, date) the
     instrument appeared in the in-scope bhavcopy (EQ series, price > 0). This
     *is* the point-in-time universe: downstream asks "which ISINs were
     tradeable on date D?" by filtering this table.

  3. isin_symbol_map: ISIN_SYMBOL_MAP_SCHEMA — one row per (isin, symbol) pair
     with first_date / last_date, covering the period that symbol was in use for
     that ISIN. A rename produces two rows for the same ISIN, which lets T8
     verify ISIN continuity across the rename boundary.

No-lookahead guarantee (01_DATA_LAYER.md §7.4):
  * adv_20 at date D is the rolling median of traded_value over the 20 trading
    days ending at D (inclusive). A causal rolling window only ever reads
    backward — no future data is visible. Sorting by (isin, date) before the
    rolling transform enforces this.
  * membership and isin_symbol_map are derived solely from the rows already
    present in the input; no forward projection is performed.

adv_20 convention (01_DATA_LAYER.md §5.5):
  * 20-day rolling **median** of traded_value, per ISIN.
  * Median resists single-day volume/value spikes (mean would be inflated).
  * min_periods=1: rows early in an ISIN's history use whatever data is
    available rather than emitting NaN. This avoids spurious gaps at the
    start of newly-listed or newly-appearing ISINs, but makes the liquidity
    floor permissive for the first 19 trading days of any ISIN — adv_20
    reflects fewer than 20 days of history. Downstream (spec 02/04) should
    require a minimum age before applying the liquidity floor in rebalancing.
"""

import logging

import pandas as pd

from app.data.bhavcopy.store import (
    ISIN_SYMBOL_MAP_SCHEMA,
    PRICES_ADJUSTED_SCHEMA,
    UNIVERSE_MEMBERSHIP_SCHEMA,
)

logger = logging.getLogger(__name__)


def build_universe(
    adjusted_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build adv_20, point-in-time membership, and ISIN→symbol map.

    Parameters
    ----------
    adjusted_df:
        Output of ``adjust.adjust_prices()`` — all columns of
        ``PRICES_ADJUSTED_SCHEMA`` except ``adv_20``.

    Returns
    -------
    prices : pd.DataFrame
        Input with ``adv_20`` column appended. Schema is exactly
        ``PRICES_ADJUSTED_SCHEMA``.
    membership : pd.DataFrame
        One row per (isin, date) the instrument was present in the scoped
        bhavcopy. Schema: ``UNIVERSE_MEMBERSHIP_SCHEMA``.
    isin_symbol_map : pd.DataFrame
        One row per (isin, symbol) pair. Schema: ``ISIN_SYMBOL_MAP_SCHEMA``.
    """
    if adjusted_df.empty:
        return _empty_prices(), _empty_membership(), _empty_isin_map()

    # Sort by (isin, date) so each ISIN's rolling window is causal.
    df = adjusted_df.sort_values(["isin", "date"]).reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # adv_20: 20-day rolling median of traded_value, per ISIN, no lookahead
    # ------------------------------------------------------------------ #
    # groupby + transform applies the function independently to each ISIN
    # group. Because df is already sorted by date within each group, the
    # window at row i sees exactly the min(i+1, 20) preceding rows — never
    # any future row. min_periods=1 avoids NaN at the start of the history.
    adv20_series = df.groupby("isin", sort=False)["traded_value"].transform(
        lambda s: s.rolling(20, min_periods=1).median()
    )
    df = df.assign(adv_20=adv20_series)
    # Reorder columns to match PRICES_ADJUSTED_SCHEMA exactly (adv_20 sits
    # between traded_value and adj_factor in the canonical schema).
    df = df[list(PRICES_ADJUSTED_SCHEMA)]

    logger.debug(
        "build_universe: adv_20 computed for %d ISINs, %d rows",
        df["isin"].nunique(),
        len(df),
    )

    # ------------------------------------------------------------------ #
    # universe_membership: (isin, date) pairs present in the price data
    # ------------------------------------------------------------------ #
    membership = df[["isin", "date"]].drop_duplicates().reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # isin_symbol_map: first/last date per (isin, symbol) pair
    # ------------------------------------------------------------------ #
    # A rename of the NSE ticker for the same ISIN produces two rows here,
    # which is exactly what T8 criterion 3 checks.
    isin_symbol_map = (
        df.groupby(["isin", "symbol"], sort=False)["date"]
        .agg(first_date="min", last_date="max")
        .reset_index()
    )

    return df, membership, isin_symbol_map


# --------------------------------------------------------------------------- #
# Empty-frame helpers (used by build_universe on empty input)                 #
# --------------------------------------------------------------------------- #


def _empty_prices() -> pd.DataFrame:
    return pd.DataFrame(columns=list(PRICES_ADJUSTED_SCHEMA))


def _empty_membership() -> pd.DataFrame:
    return pd.DataFrame(columns=list(UNIVERSE_MEMBERSHIP_SCHEMA))


def _empty_isin_map() -> pd.DataFrame:
    return pd.DataFrame(columns=list(ISIN_SYMBOL_MAP_SCHEMA))
