"""v4 / 01 — Market-internals derivation: daily breadth + advance/decline.

Derives raw daily *market-state* series from the adjusted bhavcopy panel — breadth %
and A/D ratio, for both the all-EQ universe and the v2 liquid subset — plus an optional
India VIX merge. These are the regime-score *inputs* for the v4 swing strategy
(``specs/v4/01_REGIME_DATA_LAYER.md``). This is a **data-layer derivation only**: no
regime score, no entry/exit logic, no return number lives here (the score is defined in
``00_SWING_PREREG.md``).

Point-in-time discipline (01 §3 — every item a check, not a nicety):
  * Direction uses the split/bonus-**adjusted** close (``close``), never ``close_raw`` —
    a corporate action must not manufacture a phantom decliner (the exact class of
    data-layer bug that sank v1).
  * A name is counted on day ``D`` only if it has an adjusted close on **both** ``D`` and
    the immediately-preceding trading day (the market calendar derived from the panel
    itself). A new listing / late-entering ISIN is excluded from its first day —
    survivorship-free, no phantom advancer/decliner from a missing prior.
  * The liquid subset gates on ``adv_20`` as of ``D`` (decision-date, no lookahead),
    matching the v2 ₹5cr floor (``signals_v3.py``: ``liquidity_floor_cr * 1e7``).
  * India VIX is left-joined onto the trading calendar; missing days are surfaced as NaN
    (logged), **never** forward-filled.
"""

import logging

import numpy as np
import pandas as pd

from app.data.bhavcopy import store as store_mod

logger = logging.getLogger(__name__)

# ₹5cr liquidity floor in rupees — matches signals_v3.py (``liquidity_floor_cr * 1e7``).
LIQUID_FLOOR_RUPEES: float = 5.0 * 1e7

# Canonical output column order (== MARKET_INTERNALS_SCHEMA in store.py).
MARKET_INTERNALS_COLUMNS: list[str] = [
    "date",
    "advancers",
    "decliners",
    "unchanged",
    "total",
    "breadth_pct",
    "ad_ratio",
    "liq_advancers",
    "liq_decliners",
    "liq_unchanged",
    "liq_total",
    "liq_breadth_pct",
    "liq_ad_ratio",
    "india_vix",
]


def _ad_ratio(adv: pd.Series, dec: pd.Series) -> pd.Series:
    """Advancers ÷ decliners, with ``decliners == 0 → adv / 1`` (avoids +inf).

    Monotonic and meaningful at the zero-decliner edge (effectively "every directional
    name advanced"); a broad market never hits this except on warmup-thin early days.
    """
    return adv / dec.where(dec > 0, 1)


def _breadth_pct(adv: pd.Series, dec: pd.Series) -> pd.Series:
    """100 · advancers / (advancers + decliners); NaN when no directional names."""
    direction = adv + dec
    return 100.0 * adv / direction.where(direction > 0, np.nan)


def compute_market_internals(
    prices_df: pd.DataFrame,
    vix_series: "pd.Series | pd.DataFrame | None" = None,
    *,
    liquid_floor_rupees: float = LIQUID_FLOOR_RUPEES,
) -> pd.DataFrame:
    """Derive daily breadth + A/D (all-EQ and liquid-subset) from the adjusted panel.

    Parameters
    ----------
    prices_df:
        ``PRICES_ADJUSTED_SCHEMA`` frame; needs ``isin``, ``date``, ``close``, ``adv_20``.
    vix_series:
        Optional India VIX daily series — a Series indexed by date, or a frame with
        ``date`` + ``india_vix``. Left-joined onto the trading calendar; missing days are
        NaN (logged, not filled). ``None`` ⇒ ``india_vix`` all-NaN — the 3-factor regime
        tier still works without it (01 §0; Part B lands VIX separately).
    liquid_floor_rupees:
        adv_20 threshold for the liquid subset (default ₹5cr = ``5e7``).

    Returns
    -------
    One row per trading day, columns == ``MARKET_INTERNALS_COLUMNS``, sorted by date.
    The first calendar day in the panel has ``total == 0`` (no prior day to diff against)
    and NaN breadth — an explicit warmup edge, not an error.
    """
    if prices_df.empty:
        return pd.DataFrame(columns=MARKET_INTERNALS_COLUMNS)

    df = prices_df.loc[:, ["isin", "date", "close", "adv_20"]].copy()
    df["date"] = pd.to_datetime(df["date"])

    # (date × isin) close panel; the row index IS the market trading calendar derived
    # from the data. pivot_table (not pivot) tolerates any accidental dup (date, isin).
    close = df.pivot_table(index="date", columns="isin", values="close").sort_index()
    adv20 = df.pivot_table(index="date", columns="isin", values="adv_20").reindex(
        index=close.index, columns=close.columns
    )

    # Day-over-day adjusted-close change vs the immediately-preceding trading day.
    # NaN on either side (name absent on D or D-1) ⇒ NOT counted (survivorship-free).
    delta = close - close.shift(1)
    counted = delta.notna()
    up = delta > 0
    down = delta < 0
    flat = counted & (delta == 0)

    # Liquid subset: counted AND adv_20[D] >= floor (decision-date liquidity).
    liq = counted & (adv20 >= liquid_floor_rupees)

    out = pd.DataFrame({"date": close.index})
    out["advancers"] = up.sum(axis=1).values
    out["decliners"] = down.sum(axis=1).values
    out["unchanged"] = flat.sum(axis=1).values
    out["total"] = counted.sum(axis=1).values
    out["breadth_pct"] = _breadth_pct(out["advancers"], out["decliners"])
    out["ad_ratio"] = _ad_ratio(out["advancers"], out["decliners"])
    out["liq_advancers"] = (up & liq).sum(axis=1).values
    out["liq_decliners"] = (down & liq).sum(axis=1).values
    out["liq_unchanged"] = (flat & liq).sum(axis=1).values
    out["liq_total"] = liq.sum(axis=1).values
    out["liq_breadth_pct"] = _breadth_pct(out["liq_advancers"], out["liq_decliners"])
    out["liq_ad_ratio"] = _ad_ratio(out["liq_advancers"], out["liq_decliners"])

    out["india_vix"] = _vix_column(out["date"], vix_series)

    return out.loc[:, MARKET_INTERNALS_COLUMNS].reset_index(drop=True)


def _vix_column(
    dates: pd.Series, vix_series: "pd.Series | pd.DataFrame | None"
) -> pd.Series:
    """Align an India VIX series onto ``dates`` (left join); NaN where absent (logged)."""
    if vix_series is None:
        return pd.Series(np.nan, index=dates.index, dtype="float64")

    if isinstance(vix_series, pd.Series):
        vix = vix_series.rename("india_vix").reset_index()
        vix.columns = ["date", "india_vix"]
    else:
        vix = vix_series.loc[:, ["date", "india_vix"]].copy()
    vix["date"] = pd.to_datetime(vix["date"])

    merged = pd.DataFrame({"date": pd.to_datetime(dates.values)}).merge(
        vix, on="date", how="left"
    )
    missing = int(merged["india_vix"].isna().sum())
    if missing:
        logger.warning(
            "market_internals: %d trading day(s) missing India VIX "
            "(stored as NaN, not forward-filled — 01 §3)",
            missing,
        )
    return pd.Series(merged["india_vix"].values, index=dates.index, dtype="float64")


def backfill_from_store(root: "str | None" = None) -> pd.DataFrame:
    """Seed ``market_internals`` from the EXISTING adjusted store — non-destructive.

    Reads ``prices_adjusted`` in full, derives the series, and writes the artifact
    **without** a full rebuild: no download, no live CA fetch, no overwrite of
    ``prices_adjusted`` / membership / any backtest input. A normal ``run_build``
    regenerates the same artifact in Stage 7b; this just seeds it now (01 §2A). India
    VIX stays NaN until Part B lands (the 3-factor regime tier works without it).
    """
    prices = store_mod.read_prices_adjusted(root=root)
    internals = compute_market_internals(prices)
    store_mod.write_market_internals(internals, root=root)
    logger.info(
        "market_internals: backfilled %d trading days (%s → %s)",
        len(internals),
        internals["date"].min().date() if not internals.empty else "—",
        internals["date"].max().date() if not internals.empty else "—",
    )
    return internals


if __name__ == "__main__":  # pragma: no cover — one-off backfill entry point
    logging.basicConfig(level=logging.INFO)
    out = backfill_from_store()
    print(
        f"market_internals: {len(out)} trading days, "
        f"{out['date'].min().date()} → {out['date'].max().date()}"
    )
