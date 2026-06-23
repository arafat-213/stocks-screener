"""v4 / 01 Part B — India VIX ingestion (yfinance ``^INDIAVIX``).

``specs/v4/01_REGIME_DATA_LAYER.md`` §8.4 was revised 2026-06-23 (Arafat): the locked
NSE index-bhavcopy source is replaced by yfinance ``^INDIAVIX``. Justification (§13-style
deviation): India VIX is an index *level* — never restated, not adjustment- or
survivorship-sensitive — so the PIT-cleanliness argument that justified the bhavcopy path
does not apply (v1's sin was an adjustment bug, inapplicable to an unadjusted level). The
depth probe (2026-06-23) showed ``^INDIAVIX`` covers 2008→present with 99.3% of trading
days and 0 NaN — full depth for a one-line fetch.

Pattern: the fetched series is cached to ``india_vix.parquet`` (a *source cache*, like the
CA audit trail). ``market_internals`` reads that cache and merges it into its ``india_vix``
column during the build — so the build itself stays network-free for VIX, and refreshing
VIX is its own task. The live fetch is a one-off (CLAUDE.md §5: no live API in ``pytest`` —
``fetch_india_vix`` takes a ``_history`` injection point for tests).
"""

import logging

import pandas as pd

from app.data.bhavcopy import store as store_mod

logger = logging.getLogger(__name__)

TICKER = "^INDIAVIX"


def fetch_india_vix(_history: "pd.DataFrame | None" = None) -> pd.DataFrame:
    """Fetch the full ``^INDIAVIX`` daily-close history → frame ``[date, india_vix]``.

    ``_history`` injects a precomputed yfinance-style history frame (a ``Close`` column,
    a datetime index) so tests never touch the network. Fails loud on an empty source
    (CLAUDE.md Rule 12) rather than silently writing an empty VIX series.
    """
    if _history is None:  # pragma: no cover — live path exercised only by the backfill
        import yfinance as yf

        hist = yf.Ticker(TICKER).history(period="max", auto_adjust=False)
    else:
        hist = _history

    if hist is None or len(hist) == 0:
        raise ValueError(f"fetch_india_vix: empty history from {TICKER}")
    if "Close" not in hist.columns:
        raise ValueError(
            f"fetch_india_vix: no 'Close' column (got {list(hist.columns)})"
        )

    out = hist[["Close"]].copy()
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx
    out = out.reset_index()
    out.columns = ["date", "india_vix"]
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["india_vix"] = out["india_vix"].astype("float64")
    # Drop source NaNs (no fabricated levels), dedupe, sort — leaves real gaps as gaps.
    out = (
        out.dropna(subset=["india_vix"])
        .drop_duplicates(subset=["date"], keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    return out


def backfill_india_vix(
    root: "str | None" = None, _history: "pd.DataFrame | None" = None
) -> pd.DataFrame:
    """Fetch ``^INDIAVIX`` and write the ``india_vix.parquet`` source cache.

    Idempotent overwrite. After this, re-run ``market_internals.backfill_from_store``
    (or any ``run_build``) to fold VIX into the ``market_internals.india_vix`` column.
    """
    df = fetch_india_vix(_history=_history)
    store_mod.write_india_vix(df, root=root)
    logger.info(
        "india_vix: backfilled %d days (%s → %s)",
        len(df),
        df["date"].min().date(),
        df["date"].max().date(),
    )
    return df


if __name__ == "__main__":  # pragma: no cover — one-off live backfill entry point
    logging.basicConfig(level=logging.INFO)
    vix = backfill_india_vix()
    # Fold the freshly-cached VIX into market_internals immediately.
    from app.data.bhavcopy import market_internals as mi

    mi.backfill_from_store()
    print(
        f"india_vix: {len(vix)} days, {vix['date'].min().date()} → {vix['date'].max().date()}"
    )
