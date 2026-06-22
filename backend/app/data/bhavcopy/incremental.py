"""Daily incremental append for the v3/11 paper probation (§5a, §5b, §5d).

Why this is not ``run_build(today, today)``
-------------------------------------------
specs/v3/11 §5a sketches the daily append as ``build(start=today, end=today)``.
Taken literally that is **wrong** against the real pipeline: ``build.run_build``
documents (build.py §"Chunked / incremental invocation caveat") that calling it
on a sub-range **silently clobbers** prior data — Stage 6 ``delete_matching`` is
per-ISIN (not per-date) and the 20-day ``adv_20`` rolling window would be
recomputed without the earlier history. Corporate-action back-adjustment is also
*retroactive*: a split on day D rewrites the **entire prior history** of that
ISIN's adjusted series (adjust.py convention: latest date → 1.0, earlier < 1.0).

The faithful append therefore re-runs ``run_build(inception, today)`` every day.
The build's per-day checkpoint makes every prior day **free** (loaded from the
on-disk per-day parquet, zero network — proven by
``test_identical_output_with_or_without_resume``), only the new day is fetched,
and Stages 4–8 re-derive CA + adjust + ``adv_20`` over the **full** history. By
construction the incremental append is then **byte-identical to a full rebuild**
— exactly what §5b requires — and a retroactive CA is handled correctly.

§5d consistency guard
---------------------
After the append, ``reconcile_appended_series`` asserts the pre-existing history's
adjusted closes/factors are unchanged versus the prior stored snapshot — *except*
for ISINs that had a corporate action inside the appended window (whose entire
series is legitimately rescaled by the moving anchor). Any unexplained retroactive
drift raises ``IncrementalReconciliationError`` so the run halts (11 §8).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.data.bhavcopy import build as build_mod
from app.data.bhavcopy import download as dl_mod
from app.data.bhavcopy import store as store_mod

logger = logging.getLogger(__name__)


class IncrementalReconciliationError(RuntimeError):
    """Raised when appended history drifts on an ISIN with no logged CA (§5d)."""


@dataclass
class ReconciliationReport:
    """Outcome of the §5d post-append consistency guard."""

    overlapping_isins: int
    drifted_isins: list[str]  # ISINs whose history changed
    ca_explained_isins: list[str]  # of those, the ones with a CA in the window
    unexplained_isins: list[str]  # drift with NO CA → a halt condition

    @property
    def ok(self) -> bool:
        return not self.unexplained_isins


def _inception_date(root) -> date | None:
    """Earliest processed (ok/missing) trading date from the build checkpoint."""
    cp = build_mod._load_checkpoint(store_mod._root(root))
    days = [
        d for d, status in cp.get("days", {}).items() if status in ("ok", "missing")
    ]
    if not days:
        return None
    return min(date.fromisoformat(d) for d in days)


def _ca_isins_in_window(root, start_d: date, end_d: date) -> set[str]:
    """ISINs whose stored CA ex_date falls within [start_d, end_d] (inclusive)."""
    try:
        ca = store_mod.read_corporate_actions(root=root)
    except FileNotFoundError:
        return set()
    if ca.empty or "ex_date" not in ca.columns:
        return set()
    ex = pd.to_datetime(ca["ex_date"])
    mask = (ex >= pd.Timestamp(start_d)) & (ex <= pd.Timestamp(end_d))
    return set(ca.loc[mask, "isin"].astype(str))


def reconcile_appended_series(
    prior_prices: pd.DataFrame,
    new_prices: pd.DataFrame,
    ca_isins_in_window: set[str],
    *,
    tol: float = 1e-9,
) -> ReconciliationReport:
    """§5d guard — compare the overlapping (isin, date) history before/after append.

    ``prior_prices`` is the stored ``prices_adjusted`` snapshot taken *before* the
    append; ``new_prices`` is the snapshot *after*. Only rows present in BOTH (the
    pre-existing history) are compared, on ``close`` and ``adj_factor``. Drift is
    permitted only for ISINs in ``ca_isins_in_window`` (their series is rightly
    rescaled by the moving back-adjustment anchor). Any other drift is unexplained.
    """
    keys = ["isin", "date"]
    cols = keys + ["adj_factor", "close"]
    if prior_prices.empty:
        return ReconciliationReport(0, [], [], [])

    prior = prior_prices[cols].copy()
    new = new_prices[cols].copy()
    merged = prior.merge(new, on=keys, how="inner", suffixes=("_old", "_new"))

    drift_mask = ((merged["adj_factor_old"] - merged["adj_factor_new"]).abs() > tol) | (
        (merged["close_old"] - merged["close_new"]).abs() > tol
    )
    drifted = set(merged.loc[drift_mask, "isin"].astype(str))

    explained = sorted(drifted & ca_isins_in_window)
    unexplained = sorted(drifted - ca_isins_in_window)

    return ReconciliationReport(
        overlapping_isins=merged["isin"].nunique(),
        drifted_isins=sorted(drifted),
        ca_explained_isins=explained,
        unexplained_isins=unexplained,
    )


def incremental_append(
    through,
    *,
    root=None,
    raw_root=None,
    inception=None,
    reconcile: bool = True,
    **build_kwargs,
):
    """Append trading days up to ``through`` by re-running the full-history build.

    Returns a ``(BuildReport, ReconciliationReport | None)`` tuple. The second
    element is ``None`` on the very first append (no prior history to reconcile)
    or when ``reconcile=False``.

    Raises ``IncrementalReconciliationError`` if the §5d guard finds unexplained
    retroactive drift in the pre-existing history.

    ``**build_kwargs`` are forwarded to ``run_build`` (e.g. ``_session``,
    ``_ca_records``, ``sleep``, ``skip_validation``) — the test seams stay intact.
    """
    through_d = dl_mod._to_date(through)
    start_d = (
        dl_mod._to_date(inception) if inception is not None else _inception_date(root)
    )

    first_append = start_d is None
    if first_append:
        start_d = through_d

    # Snapshot the pre-existing adjusted history BEFORE the append (for §5d).
    prior_prices = pd.DataFrame()
    if reconcile and not first_append:
        try:
            prior_prices = store_mod.read_prices_adjusted(root=root)
        except FileNotFoundError:
            prior_prices = pd.DataFrame()

    logger.info(
        "incremental_append: re-running full-history build %s → %s (inception anchored)",
        start_d,
        through_d,
    )
    report = build_mod.run_build(
        start_d, through_d, root=root, raw_root=raw_root, **build_kwargs
    )

    if not reconcile or prior_prices.empty:
        return report, None

    new_prices = store_mod.read_prices_adjusted(root=root)
    # Drift is only legitimate on ISINs with a CA in the newly-appended window.
    window_start = _next_after(prior_prices)
    ca_isins = _ca_isins_in_window(root, window_start, through_d)
    rec = reconcile_appended_series(prior_prices, new_prices, ca_isins)

    if not rec.ok:
        raise IncrementalReconciliationError(
            "§5d: unexplained retroactive drift (no logged CA) on "
            f"{rec.unexplained_isins} — halting (11 §8)"
        )
    if rec.ca_explained_isins:
        logger.info(
            "incremental_append: %d ISIN(s) rescaled by an in-window CA (expected): %s",
            len(rec.ca_explained_isins),
            rec.ca_explained_isins,
        )
    return report, rec


def _next_after(prior_prices: pd.DataFrame) -> date:
    """Day after the latest date already stored — start of the appended window."""
    last = pd.to_datetime(prior_prices["date"]).max().date()
    return last + pd.Timedelta(days=1).to_pytimedelta()
