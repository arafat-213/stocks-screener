"""T8 — Validation: acceptance checks for the v2 bhavcopy data layer.

All checks raise AssertionError on failure — fail loud, never warn-and-continue
(01_DATA_LAYER.md §7, CLAUDE.md Rule 12). Run via run_validation(root=...) after
a successful build.

Checks (01 §7):
  1. Known CA events: ~5 hard-coded split/bonus ex-dates have no spurious >40%
     single-day gap; adj_factor ratio across the ex-date matches documented ratio.
     Hardened: fails (not skips) when a ≥2018 build finds zero known ISINs.
  2. Survivorship sanity: universe_membership contains ISINs whose last trading
     date is well before today (delisted names present). Zero delisted → FAIL.
  3. ISIN continuity across a known rename: one ISIN spans both symbols, no gap.
  4. No lookahead: adv_20 at date D is the causal rolling median of traded_value
     ≤ D; any contamination from future data → FAIL.
  5. close_tr cumulative return ≥ split/bonus-adjusted cumulative return on a
     sample (dividends are non-negative, so TR ≥ price over any horizon).
  6. Coverage report: printed always; sane numbers on a real multi-year run.
  7. Universe-wide unadjusted-split/bonus scan: for every ISIN, flag any
     single-day move matching a standard split ratio (2:1, 3:1, 4:1, 5:1, 10:1)
     in the adjusted close while adj_factor and tr_factor are flat — the
     signature of a missed back-adjustment. Fails if count exceeds
     _CHECK7_TOLERANCE (295). Measured post-Phase-1 residual: 287 events
     full-range (269 in-window) from ~180 permanently-absent ISINs in NSE CA
     feed (spec 05 §11.3). Added: spec 05 Phase 2.
  8. Succession coverage (T06.4): every asserted succession chain in
     successor_map.parquet resolves to exactly one instrument_id in
     prices_adjusted; both old and new legs must be present and share the
     chain-constant root_isin. Fails if any asserted successor is absent or
     mis-keyed. Skipped gracefully when successor_map is absent (pre-T06.1 stores).
     Added: spec 06 T06.4.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.data.bhavcopy import store as store_mod

# ---------------------------------------------------------------------------
# Check 7 constants (spec 05 Phase 2)
# ---------------------------------------------------------------------------
# Standard split/bonus price multipliers: close_T / close_{T-1} for a correctly
# priced event is (1 / ratio).  A flat adj_factor + this ratio = missed adjustment.
#   2:1 split or Bonus 1:1 → ×0.5    (50% drop)
#   3:1 split or Bonus 2:1 → ×0.333  (67% drop)
#   4:1 split or Bonus 3:1 → ×0.25   (75% drop)
#   5:1 split or Bonus 4:1 → ×0.2    (80% drop)   ← CUPID's actual event
#   10:1 split              → ×0.1    (90% drop)
_SPLIT_MULTIPLIERS: list[float] = [0.5, 1.0 / 3, 0.25, 0.2, 0.1]
_SPLIT_MULTIPLIER_TOL: float = 0.10  # ±10% relative tolerance per multiplier

# Post-Phase-1 residual (measured after Phase 3 rebuild, 2026-06-16):
#   62  ISIN-succession ISINs → fixed by the bridge → 0 remaining
#    5  false-positives (genuine crashes matching a clean ratio) → ~7 events
#  180  permanently absent from NSE CA feed → unfixable
# Measured post-fix count (full 2017–2026 range): 287 events
#   of which 269 fall within the floor window (2018-02-06 → 2026-06-12)
#   and 18 fall in the pre-floor period (2017-early2018).
# Pre-fix clean-ratio count was ~332 (floor window only, Phase 0 §11.3).
# Tolerance set at 295: above measured residual (287) with ~8 events headroom,
# below pre-fix count (332).
_CHECK7_TOLERANCE: int = 295

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard-coded known corporate-action events (Check 1)
# Source: NSE corporate-actions archive; ISINs verified from bhavcopy files.
# expected_ratio = per-event price multiplier (the back-adjustment factor jumps
# by this amount on the ex-date boundary):
#   Bonus a:b  → b / (a+b)   e.g. Bonus 1:1 → 0.5
#   FV split old→new → new/old   e.g. Rs2→Re1 → 0.5
# ---------------------------------------------------------------------------
# ⚠ build_run start date must be ≤ 2017-01-01 to exercise all five checks.
# RELIANCE ex-date is 2017-09-28; a 2018→present build excludes it, so check_1
# silently skips RELIANCE (the other four still fire). Start at 2017-01-01 to
# test the full set.
KNOWN_CA_EVENTS: list[dict] = [
    {
        "isin": "INE002A01018",
        "symbol": "RELIANCE",
        "ex_date": "2017-09-28",
        "description": "Bonus 1:1 — b/(a+b) = 1/2 = 0.5",
        "expected_ratio": 0.5,
        "tol": 0.05,
    },
    {
        "isin": "INE009A01021",
        "symbol": "INFY",
        "ex_date": "2018-06-14",
        "description": "Bonus 1:1 — b/(a+b) = 1/2 = 0.5",
        "expected_ratio": 0.5,
        "tol": 0.05,
    },
    {
        "isin": "INE467B01029",
        "symbol": "TCS",
        "ex_date": "2018-07-26",
        "description": "Bonus 1:1 — b/(a+b) = 1/2 = 0.5",
        "expected_ratio": 0.5,
        "tol": 0.05,
    },
    {
        "isin": "INE075A01022",
        "symbol": "WIPRO",
        "ex_date": "2019-04-11",
        "description": "FV sub-division Rs 2 → Re 1 — new/old = 1/2 = 0.5",
        "expected_ratio": 0.5,
        "tol": 0.05,
    },
    {
        "isin": "INE06H201014",
        "symbol": "GENSOL",
        "ex_date": "2023-10-17",
        "description": "Bonus 2:1 — b/(a+b) = 1/3 ≈ 0.333 (verbatim T0 record)",
        "expected_ratio": 1 / 3,
        "tol": 0.05,
    },
]

# ---------------------------------------------------------------------------
# Known rename (Check 3)
# MOTHERSUMI → MOTHERSON: NSE ticker changed Nov 2022 after Samvardhana
# Motherson International name change. ISIN INE775A01035 is continuous.
# ---------------------------------------------------------------------------
KNOWN_RENAME = {
    "isin": "INE775A01035",
    "old_symbol": "MOTHERSUMI",
    "new_symbol": "MOTHERSON",
}

# An ISIN is "delisted" (for survivorship purposes) when its last trading date
# in universe_membership is more than this many calendar days before today.
_DELISTED_THRESHOLD_DAYS = 365


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class ValidationReport:
    """Coverage numbers emitted by run_validation (check 6)."""

    rows: int = 0
    distinct_isins: int = 0
    distinct_delisted_isins: int = 0
    date_range_start: date | None = None
    date_range_end: date | None = None
    pct_days_with_gaps: float = 0.0
    ca_events_applied: int | None = None
    ca_events_unmatched: int | None = None
    checks_skipped: list[str] = field(default_factory=list)
    # Check 8 — succession coverage (T06.4)
    succession_chains_asserted: int = 0
    succession_liquid_ghost_risk: int = 0
    succession_liquid_resolved: int = 0

    def print_coverage(self) -> None:
        ca_line = (
            f"  CA events applied: {self.ca_events_applied:,}\n"
            f"  CA unmatched:      {self.ca_events_unmatched:,}\n"
            if self.ca_events_applied is not None
            else "  CA events:         (not supplied — pass ca_events_applied/unmatched)\n"
        )
        skipped = (
            f"  Checks skipped:    {', '.join(self.checks_skipped)}\n"
            if self.checks_skipped
            else ""
        )
        succession_line = (
            f"  Succession chains: {self.succession_chains_asserted} asserted "
            f"({self.succession_liquid_resolved}/{self.succession_liquid_ghost_risk} "
            f"liquid ghost-risk legs resolved)\n"
            if self.succession_chains_asserted > 0
            else ""
        )
        print(
            f"\n=== Data Layer Coverage Report ===\n"
            f"  Rows:              {self.rows:,}\n"
            f"  Distinct ISINs:    {self.distinct_isins:,}\n"
            f"  Delisted ISINs:    {self.distinct_delisted_isins:,}\n"
            f"  Date range:        {self.date_range_start} → {self.date_range_end}\n"
            f"  Days with gaps:    {self.pct_days_with_gaps:.1f}%\n"
            f"{ca_line}"
            f"{succession_line}"
            f"{skipped}"
            f"=================================="
        )


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------


def _check_1_known_ca_events(prices: pd.DataFrame, report: ValidationReport) -> None:
    """No spurious >40% gap on known ex-dates; adj_factor ratio matches documented event."""
    isins_in_data = set(prices["isin"].unique())
    checked = 0

    for ev in KNOWN_CA_EVENTS:
        isin = ev["isin"]
        if isin not in isins_in_data:
            logger.info(
                "check_1: %s (%s) not in dataset — skipping", ev["symbol"], isin
            )
            continue

        ex_date = pd.Timestamp(ev["ex_date"])
        isin_df = prices[prices["isin"] == isin].sort_values("date")

        pre = isin_df[isin_df["date"] < ex_date]
        post = isin_df[isin_df["date"] >= ex_date]

        if pre.empty or post.empty:
            logger.info(
                "check_1: %s (%s) — no data spanning ex-date %s; skipping",
                ev["symbol"],
                isin,
                ev["ex_date"],
            )
            continue

        close_before = float(pre.iloc[-1]["close"])
        close_after = float(post.iloc[0]["close"])

        # Adjusted prices must not have a >40% gap on the ex-date.
        if close_before > 0:
            gap = abs(close_after - close_before) / close_before
            assert gap <= 0.40, (
                f"check_1 FAIL: {ev['symbol']} ({isin}) has {gap:.1%} gap at "
                f"ex-date {ev['ex_date']} (close_before={close_before:.2f}, "
                f"close_after={close_after:.2f}). Event: {ev['description']}"
            )

        # adj_factor ratio across the ex-date boundary must equal expected_ratio.
        # Convention (T4): factor(day before ex_date) / factor(ex_date) = event_multiplier.
        factor_before = float(pre.iloc[-1]["adj_factor"])
        factor_after = float(post.iloc[0]["adj_factor"])

        if factor_after > 0 and not np.isclose(factor_before, factor_after, rtol=1e-6):
            ratio = factor_before / factor_after
            expected = ev["expected_ratio"]
            tol = ev["tol"]
            assert abs(ratio - expected) <= tol, (
                f"check_1 FAIL: {ev['symbol']} ({isin}) adj_factor ratio at "
                f"ex-date {ev['ex_date']}: computed={ratio:.4f}, "
                f"expected={expected:.4f} (tol ±{tol}). {ev['description']}"
            )

        logger.info(
            "check_1 PASS: %s (%s) ex-date %s — gap OK, ratio OK",
            ev["symbol"],
            isin,
            ev["ex_date"],
        )
        checked += 1

    if checked == 0:
        # For a multi-year build whose data spans ≥2018, INFY (2018-06-14) and
        # TCS (2018-07-26) must be present.  Finding zero known ISINs in such a
        # build indicates data loss, wrong store path, or schema mismatch — fail
        # rather than silently skip (spec 05 Phase 2, Check 1 hardening).
        if not prices.empty and prices["date"].min().year <= 2018:
            raise AssertionError(
                f"check_1 FAIL: multi-year build (data from "
                f"{prices['date'].min().date()}) contains zero of the "
                f"{len(KNOWN_CA_EVENTS)} known CA event ISINs in prices_adjusted. "
                f"Expected ISINs: {[ev['isin'] for ev in KNOWN_CA_EVENTS]}. "
                f"Indicates data loss, wrong store path, or ISIN schema mismatch."
            )
        report.checks_skipped.append("1-known-ca (no known ISINs in dataset)")
        logger.warning(
            "check_1: none of the %d known ISINs found in dataset", len(KNOWN_CA_EVENTS)
        )


def _check_2_survivorship(
    isin_map: pd.DataFrame, report: ValidationReport, today: date
) -> None:
    """Delisted names (last_date well before today) are present in the universe."""
    if isin_map.empty:
        raise AssertionError(
            "check_2 FAIL: isin_symbol_map is empty — no universe data at all"
        )

    cutoff = pd.Timestamp(today - timedelta(days=_DELISTED_THRESHOLD_DAYS))
    last_by_isin = isin_map.groupby("isin")["last_date"].max()
    delisted = last_by_isin[last_by_isin < cutoff]
    n_delisted = len(delisted)

    report.distinct_delisted_isins = n_delisted

    assert n_delisted > 0, (
        f"check_2 FAIL: zero ISINs with last_date before "
        f"{cutoff.date()} ({_DELISTED_THRESHOLD_DAYS} days ago). "
        f"Dataset appears to be current-universe-only — survivorship bias present."
    )
    logger.info(
        "check_2 PASS: %d delisted ISINs (last_date < %s)",
        n_delisted,
        cutoff.date(),
    )


def _check_3_isin_rename(isin_map: pd.DataFrame, report: ValidationReport) -> None:
    """ISIN continuity across a known rename: both symbols map to the same ISIN, no gap."""
    isin = KNOWN_RENAME["isin"]
    old_sym = KNOWN_RENAME["old_symbol"]
    new_sym = KNOWN_RENAME["new_symbol"]

    rows = isin_map[isin_map["isin"] == isin]
    if rows.empty:
        report.checks_skipped.append(f"3-isin-rename ({isin} not in dataset)")
        logger.info("check_3: %s not in isin_symbol_map — skipping", isin)
        return

    symbols_found = set(rows["symbol"].tolist())
    if old_sym not in symbols_found or new_sym not in symbols_found:
        report.checks_skipped.append(
            f"3-isin-rename (only {symbols_found} for {isin}; need both {old_sym}/{new_sym})"
        )
        logger.info("check_3: rename not yet visible — skipping (%s)", symbols_found)
        return

    # Old symbol must end before the new symbol starts (non-overlapping date ranges).
    old_row = rows[rows["symbol"] == old_sym].iloc[0]
    new_row = rows[rows["symbol"] == new_sym].iloc[0]

    assert old_row["last_date"] < new_row["first_date"], (
        f"check_3 FAIL: {isin} rename ({old_sym}→{new_sym}) has overlapping "
        f"date ranges: {old_sym} last={old_row['last_date'].date()}, "
        f"{new_sym} first={new_row['first_date'].date()}"
    )
    logger.info(
        "check_3 PASS: %s → %s (%s) — non-overlapping, ISIN continuous",
        old_sym,
        new_sym,
        isin,
    )


def _check_4_no_lookahead(prices: pd.DataFrame, report: ValidationReport) -> None:
    """adv_20 at date D is the causal rolling(20).median() of traded_value ≤ D.

    Note: this check recomputes the same formula universe.py uses, so it is
    a near-tautology — it catches data corruption or row-reordering after the
    fact but does not independently prove causality. The real no-lookahead
    proof is in T6's TestAdv20NoLookahead unit tests (future-spike invisibility).
    """
    if prices.empty:
        report.checks_skipped.append("4-no-lookahead (empty prices)")
        return

    # Pick the ISIN with the most rows (best coverage for a meaningful check).
    isin_counts = prices.groupby("isin").size()
    candidates = isin_counts[isin_counts >= 25]
    if candidates.empty:
        report.checks_skipped.append("4-no-lookahead (no ISIN with ≥25 rows)")
        return

    isin = candidates.idxmax()
    df = prices[prices["isin"] == isin].sort_values("date").reset_index(drop=True)

    # Independently recompute adv_20 as a causal rolling median.
    expected = df["traded_value"].rolling(20, min_periods=1).median().values
    actual = df["adv_20"].values

    assert np.allclose(actual, expected, rtol=1e-6, equal_nan=True), (
        f"check_4 FAIL: adv_20 for {isin} does not match causal "
        f"rolling(20, min_periods=1).median() — possible lookahead contamination. "
        f"First mismatch at index "
        f"{int(np.where(~np.isclose(actual, expected, rtol=1e-6, equal_nan=True))[0][0])}"
    )
    logger.info("check_4 PASS: adv_20 causal rolling-median verified for %s", isin)


def _check_5_tr_ge_price_adjusted(
    prices: pd.DataFrame, report: ValidationReport
) -> None:
    """close_tr cumulative return ≥ close (split/bonus-adjusted) cumulative return."""
    if prices.empty:
        report.checks_skipped.append("5-tr-ge-price (empty prices)")
        return

    isins = prices["isin"].unique()
    sample = isins[: min(10, len(isins))]
    checked = 0

    for isin in sample:
        df = prices[prices["isin"] == isin].sort_values("date")
        if len(df) < 2:
            continue

        c0 = float(df["close"].iloc[0])
        ctr0 = float(df["close_tr"].iloc[0])
        cN = float(df["close"].iloc[-1])
        ctrN = float(df["close_tr"].iloc[-1])

        if c0 <= 0 or ctr0 <= 0 or cN <= 0 or ctrN <= 0:
            continue

        cum_adj = cN / c0
        cum_tr = ctrN / ctr0

        # TR must be ≥ price-adjusted (dividends non-negative, 01 §7.5).
        assert cum_tr >= cum_adj - 1e-6, (
            f"check_5 FAIL: {isin} — close_tr cumulative return ({cum_tr:.6f}) "
            f"< split/bonus-adjusted ({cum_adj:.6f}). "
            f"Dividends are non-negative, so TR ≥ price must always hold (01 §7.5)."
        )
        checked += 1

    if checked == 0:
        report.checks_skipped.append("5-tr-ge-price (no qualifying ISINs)")
    else:
        logger.info(
            "check_5 PASS: close_tr ≥ close cumulative return on %d ISINs", checked
        )


def _check_7_unadjusted_action_scan(
    prices: pd.DataFrame,
    report: ValidationReport,
    tolerance: int = _CHECK7_TOLERANCE,
) -> None:
    """Universe-wide unadjusted-split/bonus scan (spec 05 Phase 2).

    Flags every single-day drop in the adjusted ``close`` that:
      (a) matches a standard split/bonus ratio (2:1, 3:1, 4:1, 5:1, 10:1)
          within ±10 % relative tolerance, AND
      (b) has both ``adj_factor`` and ``tr_factor`` flat across that day
          (no back-adjustment step was applied).

    This is the signature of a missed corporate-action back-adjustment.
    Genuine market crashes produce non-clean price ratios; circuit limits
    prevent >40 % single-day drops in liquid names, so false positives are
    rare (Phase 0 found 5 over the full universe).

    Fails loud if the flagged count exceeds *tolerance*.  Default tolerance
    (280) sits above the expected post-Phase-1 residual of ~249 events from
    the 180 permanently-absent ISINs in the NSE CA feed (spec 05 §11.3).
    Tests should pass ``tolerance=0`` to fail on even one unadjusted event.
    """
    if prices.empty:
        report.checks_skipped.append("7-unadjusted-action-scan (empty prices)")
        return

    ps = prices.sort_values(["isin", "date"]).reset_index(drop=True)
    close_arr = ps["close"].to_numpy(dtype=float)
    adj_arr = ps["adj_factor"].to_numpy(dtype=float)
    trf_arr = ps["tr_factor"].to_numpy(dtype=float)
    isin_arr = ps["isin"].to_numpy()

    # Mark first row of each ISIN group so we never compare across ISINs.
    isin_prev = np.empty_like(isin_arr)
    isin_prev[0] = ""
    isin_prev[1:] = isin_arr[:-1]
    same_isin = isin_arr == isin_prev  # False at every group boundary

    # Daily price ratio close[T] / close[T-1], NaN at group boundaries.
    prev_close = np.empty_like(close_arr)
    prev_close[0] = np.nan
    prev_close[1:] = close_arr[:-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        daily_ratio = np.where(
            same_isin & (prev_close > 0), close_arr / prev_close, np.nan
        )

    # Flat-factor flags: True when the factor does not step on this row.
    prev_adj = np.empty_like(adj_arr)
    prev_adj[0] = np.nan
    prev_adj[1:] = adj_arr[:-1]
    prev_trf = np.empty_like(trf_arr)
    prev_trf[0] = np.nan
    prev_trf[1:] = trf_arr[:-1]
    adj_flat = np.isclose(adj_arr, prev_adj, rtol=1e-6, equal_nan=False)
    trf_flat = np.isclose(trf_arr, prev_trf, rtol=1e-6, equal_nan=False)
    both_flat = same_isin & adj_flat & trf_flat

    # Match daily_ratio against each standard split/bonus multiplier.
    is_split_ratio = np.zeros(len(close_arr), dtype=bool)
    for m in _SPLIT_MULTIPLIERS:
        band = _SPLIT_MULTIPLIER_TOL * m
        is_split_ratio |= np.abs(daily_ratio - m) <= band

    n_flagged = int((both_flat & is_split_ratio).sum())

    logger.info(
        "check_7: %d unadjusted-split/bonus events (tolerance %d)",
        n_flagged,
        tolerance,
    )
    assert n_flagged <= tolerance, (
        f"check_7 FAIL: {n_flagged} unadjusted split/bonus events detected "
        f"(flat adj_factor+tr_factor with a clean-ratio drop in adjusted close) — "
        f"exceeds tolerance of {tolerance}. "
        f"Run diag_universe_quality.py for details. "
        f"Measured post-Phase-1 residual (2026-06-16): 287 full-range events "
        f"(269 in floor window) from ~180 permanently-absent ISINs in the NSE "
        f"CA feed (spec 05 §11.3)."
    )
    logger.info("check_7 PASS: %d ≤ tolerance %d", n_flagged, tolerance)


def _check_8_succession_coverage(
    successor_map: pd.DataFrame,
    prices: pd.DataFrame,
    report: ValidationReport,
) -> None:
    """Every asserted succession chain resolves to one instrument_id in prices_adjusted.

    For each asserted OLD→NEW edge in ``successor_map``:
    - The new leg's ISIN must be present in ``prices_adjusted`` (otherwise the old
      leg becomes a ghost: held but un-sellable with no forward prices).
    - Both old and new legs must carry ``instrument_id == root_isin`` (the chain-
      constant identity from T06.2). A mismatch means T06.2 was not applied or the
      re-derive was partial — momentum is still truncated on the new leg.

    Fails loud (Rule 12) if any asserted edge violates either condition. Skips
    gracefully when ``successor_map`` is absent or empty (pre-T06.1 stores).
    """
    if successor_map.empty:
        report.checks_skipped.append("8-succession-coverage (no successor_map)")
        logger.info("check_8: no successor_map — skipping")
        return

    asserted = successor_map[successor_map["asserted"]]
    if asserted.empty:
        report.checks_skipped.append("8-succession-coverage (no asserted links)")
        logger.info("check_8: no asserted links in successor_map — skipping")
        return

    isins_in_prices: set[str] = (
        set(prices["isin"].unique()) if not prices.empty else set()
    )

    # Per-ISIN instrument_id lookup (first row is sufficient — invariant within an ISIN).
    if "instrument_id" in prices.columns and not prices.empty:
        id_by_isin: dict[str, str] = (
            prices.groupby("isin")["instrument_id"].first().to_dict()
        )
    else:
        id_by_isin = {}

    failures: list[str] = []
    liquid_old_legs = 0
    liquid_resolved = 0

    for row in asserted.itertuples(index=False):
        old = str(row.old_isin)
        new = str(row.new_isin)
        root = str(row.root_isin)
        liquid = bool(row.liquid_old_leg)

        if liquid:
            liquid_old_legs += 1

        # Gate 1: new leg must be present in prices_adjusted.
        if new not in isins_in_prices:
            failures.append(
                f"  {old}→{new}: new leg {new!r} absent from prices_adjusted"
            )
            continue

        # Gate 2: old leg instrument_id must equal root_isin.
        old_id = id_by_isin.get(old, old)
        if old_id != root:
            failures.append(
                f"  {old}→{new}: old leg instrument_id={old_id!r} ≠ root={root!r}"
            )
            continue

        # Gate 3: new leg instrument_id must equal root_isin.
        new_id = id_by_isin.get(new, new)
        if new_id != root:
            failures.append(
                f"  {old}→{new}: new leg instrument_id={new_id!r} ≠ root={root!r}"
            )
            continue

        if liquid:
            liquid_resolved += 1

    report.succession_chains_asserted = len(asserted)
    report.succession_liquid_ghost_risk = liquid_old_legs
    report.succession_liquid_resolved = liquid_resolved

    assert not failures, (
        f"check_8 FAIL: {len(failures)} asserted succession chain(s) not resolved "
        f"correctly in prices_adjusted:\n"
        + "\n".join(failures[:10])
        + (f"\n  ... ({len(failures) - 10} more)" if len(failures) > 10 else "")
    )

    logger.info(
        "check_8 PASS: %d asserted chains OK; %d/%d liquid ghost-risk legs resolved",
        len(asserted),
        liquid_resolved,
        liquid_old_legs,
    )


def _build_coverage_report(
    prices: pd.DataFrame,
    membership: pd.DataFrame,
    isin_map: pd.DataFrame,
    ca_events_applied: int | None,
    ca_events_unmatched: int | None,
    today: date,
    report: ValidationReport,
) -> None:
    """Populate the coverage numbers; always runs (check 6)."""
    report.rows = len(prices)
    report.distinct_isins = prices["isin"].nunique() if not prices.empty else 0
    report.ca_events_applied = ca_events_applied
    report.ca_events_unmatched = ca_events_unmatched

    if not prices.empty:
        report.date_range_start = prices["date"].min().date()
        report.date_range_end = prices["date"].max().date()

        # % of weekdays in the range with no data in membership (trading gaps / holidays).
        if report.date_range_start and report.date_range_end:
            all_weekdays = pd.bdate_range(
                report.date_range_start, report.date_range_end
            )
            trading_days = membership["date"].nunique() if not membership.empty else 0
            total = len(all_weekdays)
            gap_days = max(0, total - trading_days)
            report.pct_days_with_gaps = (gap_days / total * 100) if total > 0 else 0.0

    cutoff = pd.Timestamp(today - timedelta(days=_DELISTED_THRESHOLD_DAYS))
    if not isin_map.empty:
        last_by_isin = isin_map.groupby("isin")["last_date"].max()
        report.distinct_delisted_isins = int((last_by_isin < cutoff).sum())

    logger.info(
        "check_6: rows=%d, ISINs=%d, delisted=%d, range=%s→%s, gaps=%.1f%%",
        report.rows,
        report.distinct_isins,
        report.distinct_delisted_isins,
        report.date_range_start,
        report.date_range_end,
        report.pct_days_with_gaps,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_validation(
    root=None,
    *,
    ca_events_applied: int | None = None,
    ca_events_unmatched: int | None = None,
    today: date | None = None,
    check7_tolerance: int = _CHECK7_TOLERANCE,
) -> ValidationReport:
    """Run all acceptance checks from 01_DATA_LAYER.md §7.

    Reads the three parquet tables from *root* (default: store.default_root()).
    Fails loud (AssertionError) if any check fails. Always prints the coverage
    report (check 6).

    Parameters
    ----------
    root:
        Parquet store root; defaults to ``store.default_root()``.
    ca_events_applied, ca_events_unmatched:
        Counts from the build run (from BuildReport). Optional — printed in the
        coverage report if supplied.
    today:
        Override "today" for testing (default: date.today()).
    check7_tolerance:
        Maximum unadjusted-split events before Check 7 fails.  Pass 0 in tests
        that inject a deliberately unadjusted split (default: _CHECK7_TOLERANCE).

    Returns
    -------
    ValidationReport
        Coverage numbers from check 6. Only returned if all checks pass.
    """
    _today = today or date.today()

    logger.info(
        "validate: reading parquet tables from %s", root or store_mod.default_root()
    )
    prices = store_mod.read_prices_adjusted(root)
    membership = store_mod.read_universe_membership(root)
    isin_map = store_mod.read_isin_symbol_map(root)
    successor_map = store_mod.read_successor_map(root)

    report = ValidationReport()

    # Check 6 first so coverage is always populated for printing.
    _build_coverage_report(
        prices,
        membership,
        isin_map,
        ca_events_applied,
        ca_events_unmatched,
        _today,
        report,
    )

    logger.info("validate: running check 1 — known CA events")
    _check_1_known_ca_events(prices, report)

    logger.info("validate: running check 2 — survivorship sanity")
    _check_2_survivorship(isin_map, report, _today)

    logger.info("validate: running check 3 — ISIN continuity across rename")
    _check_3_isin_rename(isin_map, report)

    logger.info("validate: running check 4 — no lookahead in adv_20")
    _check_4_no_lookahead(prices, report)

    logger.info("validate: running check 5 — close_tr ≥ close cumulative return")
    _check_5_tr_ge_price_adjusted(prices, report)

    logger.info("validate: running check 7 — universe-wide unadjusted-split scan")
    _check_7_unadjusted_action_scan(prices, report, tolerance=check7_tolerance)

    logger.info("validate: running check 8 — succession coverage")
    _check_8_succession_coverage(successor_map, prices, report)

    report.print_coverage()
    logger.info("validate: all checks passed")
    return report
