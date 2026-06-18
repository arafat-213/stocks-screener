"""
tb8_ingest — TB8: production ingest + §6 gate RUN (the actual PASS/FAIL verdict).

This is the **only** Track-B data task that touches LIVE NSE data.  Every prior
TBx mocked exchange fetches (CLAUDE.md §5); this module is the operational run
that populates the real PIT panel and then executes the TB7 acceptance gate over
it to produce the first actual §6 verdict.

What it wires (the only NEW code — everything else is reused, Rule 3)
--------------------------------------------------------------------
1. ``membership_derived_listings`` — the ``fetch_exchange_listings`` source.
   Derives the survivorship-free universe from the v2 ``universe_membership``
   parquet (first-seen → list_date, last-seen → delist_date, NULL if seen
   through the panel end).  Fully OFFLINE + reproducible; makes the TB2
   cross-check pass by construction (same ISIN spine as the price layer).
2. ``make_eligible_on_date`` — the gate's ``EligibleOnDate`` adapter.  Per
   rebalance date: liquidity-eligible ISINs (adv_20 ≥ floor), each weighted by
   ``adv_20``.  **Weight basis decision (surfaced, Rule 7/12):** the §6.1
   "by market-cap weight" floor is weighted by ``adv_20``, NOT by
   ``market_cap_raw``.  market_cap needs shares_outstanding *from* the
   fundamentals layer, so an uncovered name would contribute 0 to both the
   numerator and denominator and MASK a large-cap coverage gap (weight-coverage
   would read ~100% even with a mega-cap missing).  adv_20 is available for every
   eligible name (complete, non-circular denominator) and a missing large name
   correctly drags weight-coverage down — the §6.1 intent.  ``market_cap_raw``
   stays the convention for ``03`` factor math, not for gate weighting.
3. ``make_recon_reader`` — the §6.5 ``ReconReader``.  Re-fetches + re-parses the
   stored XBRL document per sampled ISIN-quarter.  This is a transport / parser-
   stability / store-integrity audit (it catches a corrupted or stale stored row,
   or a parser drift since ingest); a fully independent semantic reference (the
   filing PDF / portal) is a future hardening, surfaced in the session log.

Orchestration (one ``PipelineRun``, idempotent + checkpointed)
--------------------------------------------------------------
    0. cleanup_zombie_runs + concurrency guard; resume from last checkpoint
    1. populate_universe(source = membership-derived listings)       [OFFLINE]
    2. cross_check_against_price_universe(...)  → surfaced (Rule 12)  [OFFLINE]
    3. symbol_map from the v2 price layer                            [OFFLINE]
    4. populate_filing_index(fetch_nse_filing_index, symbol_map)     [LIVE NSE]
    5. populate_line_items(fetch_xbrl_document)                      [LIVE NSE]
    6. run_acceptance_gate(...) over monthly rebalances 2020 → DISCOVERY_END
    7. emit per-check PASS/FAIL table + verdict; pin DISCOVERY_START month

Discipline (non-negotiable)
---------------------------
NO threshold is introduced here — the gate reads ``data_config.py`` (TB0-locked).
If coverage FAILS at some 2020 rebalances, the ONLY sanctioned response is the
already-pre-registered ``DISCOVERY_START`` ≈2020 rescope (a §10 decision), never a
floor nudge.  ``FINAL_OOS`` (2023-07-01 → 2026-06-12) stays pristine — the gate
runs on the DISCOVERY panel only.

Run (smoke — ~20 ISINs end-to-end, bounded live surface):
    backend/venv/bin/python -m app.fundamentals.tb8_ingest --smoke --limit 20

Run (full panel — multi-hour, resumable):
    backend/venv/bin/python -m app.fundamentals.tb8_ingest
    backend/venv/bin/python -m app.fundamentals.tb8_ingest --resume <run_id>
"""

from __future__ import annotations

import argparse
import datetime
import random
import uuid
from collections.abc import Callable

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.engine import _rebalance_dates
from app.backtest_v2.validation import DISCOVERY
from app.data.bhavcopy import store
from app.db.models import PipelineRun
from app.db.session import SessionLocal
from app.fundamentals.data_config import RECON_SAMPLE_N
from app.fundamentals.filing_index import fetch_nse_filing_index, populate_filing_index
from app.fundamentals.gate import (
    EligibleOnDate,
    GateResult,
    ReconReader,
    run_acceptance_gate,
)
from app.fundamentals.models import (
    FundamentalsFilingIndex,
    FundamentalsLineItemVersion,
    FundamentalsUniverse,
)
from app.fundamentals.reader import read_fundamentals_asof
from app.fundamentals.tb0_5_probe import liquidity_eligible_isins
from app.fundamentals.universe import (
    ListingRecord,
    cross_check_against_price_universe,
    populate_universe,
    read_price_universe_isins,
)
from app.fundamentals.xbrl_parser import (
    fetch_xbrl_document,
    parse_xbrl,
    populate_line_items,
)
from app.pipeline.orchestrator import cleanup_zombie_runs

# Pre-registered DISCOVERY_START ≈2020 (00_PREREGISTRATION.md / TB0.5 STEP-1).
# The gate's coverage check across monthly rebalances is what pins the exact
# durable-≥75% month — a genuine TB8 output, not a guess.  DISCOVERY_END caps the
# panel so FINAL_OOS (2023-07-01 →) is never touched.
DEFAULT_START = datetime.date(2020, 1, 1)
PANEL_END = DISCOVERY[1]  # 2023-06-30 — DISCOVERY end; FINAL_OOS stays pristine.

_RANDOM_SEED = 20260618  # reproducible recon / smoke sampling


def _to_business_day(d: datetime.date) -> datetime.date:
    """Roll ``d`` forward to the next Mon–Fri business day (idempotent if already one).

    The gate's ``_cutoff`` (TB5) calls ``np.busday_offset(..., roll='raise')`` which
    rejects a weekend ``as_of`` date.  Rebalance dates are real trading days (always
    Mon–Fri), but synthetic look-ahead probe dates derived by calendar arithmetic can
    land on a weekend — snap them so the gate contract (business-day inputs) holds.
    """
    return np.busday_offset(d, 0, roll="forward").astype("O")


# ---------------------------------------------------------------------------
# Seam 1 — fetch_exchange_listings: membership-derived (OFFLINE, reproducible)
# ---------------------------------------------------------------------------


def membership_derived_listings(root: str | None = None) -> list[ListingRecord]:
    """Derive the survivorship-free universe from the v2 ``universe_membership``.

    One ``ListingRecord`` per ISIN ever present in-window:
      * ``list_date``   = first date the ISIN appears in membership (left-censored
        at the panel start — "first seen", not necessarily the true IPO date).
      * ``delist_date`` = last date it appears, OR ``None`` if it is still present
        on the panel's final membership date (the survivorship-free open window).

    Offline + deterministic: the master's ISIN spine equals the price layer's, so
    ``cross_check_against_price_universe`` passes by construction.  ``name`` carries
    the latest known NSE symbol (no company-name source in the v2 layer).
    """
    membership = store.read_universe_membership(root=root)
    if membership.empty:
        return []

    grp = membership.groupby("isin")["date"].agg(["min", "max"])
    panel_last = membership["date"].max()

    symmap_df = store.read_isin_symbol_map(root=root)
    # Latest symbol per ISIN (one ISIN can have multiple symbols over time).
    symmap_df = symmap_df.sort_values("last_date")
    sym_by_isin = dict(zip(symmap_df["isin"], symmap_df["symbol"]))

    records: list[ListingRecord] = []
    for isin, row in grp.iterrows():
        if not isin:
            continue
        first_seen = row["min"]
        last_seen = row["max"]
        # Still listed if present on the panel's final membership date.
        delist = None if last_seen >= panel_last else last_seen.date()
        records.append(
            ListingRecord(
                isin=isin,
                name=sym_by_isin.get(isin),
                exchange="NSE",
                list_date=first_seen.date(),
                delist_date=delist,
            )
        )
    return records


# ---------------------------------------------------------------------------
# Seam 2 — EligibleOnDate adapter (liquidity-eligible denominator, adv_20 weight)
# ---------------------------------------------------------------------------


def make_eligible_on_date(
    prices: pd.DataFrame,
    liq_floor_rupees: float,
    restrict_isins: set[str] | None = None,
) -> EligibleOnDate:
    """Build the gate's ``EligibleOnDate`` seam over the v2 price panel.

    Per rebalance date ``D``: the liquidity-eligible ISINs (adv_20 ≥ floor —
    the §6.1 pinned denominator, NOT raw membership), each weighted by ``adv_20``
    (see the weight-basis decision in the module docstring).  ``restrict_isins``
    (smoke mode) narrows the denominator to the ingested subset so the smoke's
    coverage % is meaningful over what was actually ingested; ``None`` (full run)
    uses the entire eligible universe.
    """
    by_date = {pd.Timestamp(d): g for d, g in prices.groupby("date")}

    def eligible_on_date(D: datetime.date) -> list[tuple[str, float]]:
        on_day = by_date.get(pd.Timestamp(D))
        if on_day is None or on_day.empty:
            return []
        elig = liquidity_eligible_isins(on_day, liq_floor_rupees)
        adv = dict(zip(on_day["isin"], on_day["adv_20"]))
        out: list[tuple[str, float]] = []
        for isin in elig:
            if restrict_isins is not None and isin not in restrict_isins:
                continue
            w = adv.get(isin)
            if w is None or w <= 0:
                continue
            out.append((isin, float(w)))
        return out

    return eligible_on_date


# ---------------------------------------------------------------------------
# Seam 3 — ReconReader for §6.5 (re-fetch + re-parse the stored XBRL doc)
# ---------------------------------------------------------------------------


def make_recon_reader(
    session: Session,
    fetcher: Callable[[str], str] = fetch_xbrl_document,
) -> ReconReader:
    """Build the §6.5 ``ReconReader``: re-parse the stored XBRL per ISIN-quarter.

    For each sampled ``(isin, period_end)`` finds the latest stored filing that
    has a ``document_url``, re-fetches + re-parses it, and returns the 4 reconciled
    core items as the reference the gate diffs against ``RECON_TOLERANCE`` (±2%).
    A missing document or a fetch/parse failure yields ``None`` (the gate skips it
    — unavailability is not a mismatch).
    """

    def recon_reader(
        isin_periods: list[tuple[str, datetime.date]],
    ) -> dict[tuple[str, datetime.date], dict[str, float | None]]:
        out: dict[tuple[str, datetime.date], dict[str, float | None]] = {}
        for isin, period_end in isin_periods:
            filing = (
                session.query(FundamentalsFilingIndex)
                .filter_by(isin=isin, period_end=period_end)
                .filter(FundamentalsFilingIndex.document_url.isnot(None))
                .order_by(FundamentalsFilingIndex.available_date.desc())
                .first()
            )
            if filing is None:
                out[(isin, period_end)] = None
                continue
            try:
                parsed = parse_xbrl(fetcher(filing.document_url))
            except Exception:
                out[(isin, period_end)] = None
                continue
            out[(isin, period_end)] = {
                "revenue": parsed.revenue,
                "net_income": parsed.net_income,
                "total_equity": parsed.total_equity,
                "total_assets": parsed.total_assets,
            }
        return out

    return recon_reader


# ---------------------------------------------------------------------------
# Rebalance calendar + smoke ISIN selection
# ---------------------------------------------------------------------------


def monthly_rebalance_dates(
    prices: pd.DataFrame, start: datetime.date, end: datetime.date
) -> list[datetime.date]:
    """Monthly rebalance dates (last trading day of each month) in [start, end].

    Reuses the v2 ``_rebalance_dates`` so the gate's rebalance grid is identical
    to the backtest's (Rule 3).
    """
    calendar = [pd.Timestamp(d) for d in sorted(prices["date"].unique())]
    rebal = _rebalance_dates(calendar, "monthly")
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    return sorted(d.date() for d in rebal if lo <= d <= hi)


def select_smoke_isins(
    prices: pd.DataFrame,
    ref_date: datetime.date,
    liq_floor_rupees: float,
    limit: int,
) -> dict[str, str]:
    """Pick the ``limit`` most-liquid eligible ISINs on ``ref_date`` for the smoke.

    Top-by-adv_20 large caps are the most likely to carry clean standard-tag XBRL,
    so the smoke exercises the happy path end-to-end.  Returns ``{isin: symbol}``
    using the as-of-date symbol from the price panel.
    """
    on_day = prices.loc[prices["date"] == pd.Timestamp(ref_date)]
    elig = on_day.loc[
        on_day["adv_20"].notna() & (on_day["adv_20"] >= liq_floor_rupees)
    ].sort_values("adv_20", ascending=False)
    elig = elig.head(limit)
    return dict(zip(elig["isin"], elig["symbol"]))


# ---------------------------------------------------------------------------
# Gate-input assembly (built from the freshly-ingested data)
# ---------------------------------------------------------------------------


def _assemble_gate_inputs(
    session: Session,
    isins: list[str],
    rebalance_dates: list[datetime.date],
) -> dict:
    """Assemble the §6.2/6.3/6.4/6.5 gate inputs from the ingested panel.

    §6.1 inputs (eligible_on_date, rebalance_dates) are passed separately by the
    caller.  The rest are derived here from what was actually stored:
      * §6.2 PIT — sample over ``isins`` × ``rebalance_dates``.
      * §6.3 survivorship — known in-window delistings present in the master
        (illustrative for the smoke; the FULL run supplies a curated external
        delisting list — surfaced in the session log).
      * §6.4 look-ahead — one case per ISIN-period: D_pre/D_post both post-period.
      * §6.5 reconciliation — up to RECON_SAMPLE_N random stored ISIN-quarters.
    """
    rng = random.Random(_RANDOM_SEED)

    # §6.3 — known delistings present in the master (have a delist_date set).
    delisted = [
        row[0]
        for row in (
            session.query(FundamentalsUniverse.isin)
            .filter(
                FundamentalsUniverse.isin.in_(isins),
                FundamentalsUniverse.delist_date.isnot(None),
            )
            .all()
        )
    ]

    # §6.4 + §6.5 — stored (isin, period_end) pairs.
    stored = (
        session.query(
            FundamentalsLineItemVersion.isin,
            FundamentalsLineItemVersion.period_end,
        )
        .filter(FundamentalsLineItemVersion.isin.in_(isins))
        .distinct()
        .all()
    )
    isin_periods = [(r[0], r[1]) for r in stored]

    lookahead_cases: list[tuple[str, datetime.date, datetime.date, datetime.date]] = []
    for isin, period_end in isin_periods[:5]:
        d_pre = _to_business_day(period_end + datetime.timedelta(days=120))
        d_post = _to_business_day(period_end + datetime.timedelta(days=300))
        lookahead_cases.append((isin, period_end, d_pre, d_post))

    recon_sample = rng.sample(isin_periods, min(RECON_SAMPLE_N, len(isin_periods)))

    return {
        "sample_isins": isins,
        "sample_dates": rebalance_dates,
        "known_delistings": delisted,
        "lookahead_test_cases": lookahead_cases,
        "recon_sample": recon_sample,
    }


def pin_discovery_start(
    eligible_on_date: EligibleOnDate,
    session: Session,
    rebalance_dates: list[datetime.date],
) -> datetime.date | None:
    """Earliest rebalance date from which by-name coverage holds ≥ floor durably.

    Walks the rebalance grid; returns the first date such that this date AND every
    later date clears the §6.1 by-name floor.  ``None`` if no such durable start
    exists (the honest "coverage never stabilizes" outcome).  This is a genuine
    TB8 output from the real panel, never a moved threshold.
    """
    from app.fundamentals.data_config import COVERAGE_THRESHOLD_NAME

    name_pct: dict[datetime.date, float] = {}
    for D in rebalance_dates:
        eligible = eligible_on_date(D)
        if not eligible:
            continue
        covered = sum(
            1 for isin, _ in eligible if read_fundamentals_asof(session, isin, D)
        )
        name_pct[D] = covered / len(eligible)

    dates = sorted(name_pct)
    for i, D in enumerate(dates):
        if all(name_pct[later] >= COVERAGE_THRESHOLD_NAME for later in dates[i:]):
            return D
    return None


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


def _acquire_run(session: Session, resume_run_id: str | None) -> str:
    """Acquire a PipelineRun id: resume an existing run, or start a guarded fresh one.

    Resume reactivates the named run and KEEPS its checkpoints (so a crashed
    multi-hour ingest continues from the last ISIN).  A fresh start runs
    ``cleanup_zombie_runs`` first (CLAUDE.md §1 startup hygiene / concurrency
    guard) — note this marks ANY 'running' PipelineRun as failed, so do not launch
    a fresh TB8 run alongside a live daily pipeline.
    """
    if resume_run_id:
        run = session.get(PipelineRun, resume_run_id)
        if run is None:
            raise ValueError(f"--resume run_id {resume_run_id!r} not found")
        run.status = "running"
        session.commit()
        return run.run_id

    cleanup_zombie_runs(session)
    run = PipelineRun(run_id=str(uuid.uuid4()), status="running")
    session.add(run)
    session.commit()
    return run.run_id


def run_ingest(
    session: Session,
    *,
    start_date: datetime.date = DEFAULT_START,
    panel_end: datetime.date = PANEL_END,
    limit: int | None = None,
    resume_run_id: str | None = None,
    do_live: bool = True,
) -> tuple[str, GateResult | None, datetime.date | None]:
    """Run the TB8 ingest + gate.  Returns (run_id, gate_result, pinned_start).

    ``limit`` caps the ISINs entering the LIVE stages (smoke).  ``do_live=False``
    runs only the offline stages (universe + cross-check) and skips the gate.
    """
    cfg = MomentumConfig()
    liq_floor_rupees = cfg.liquidity_floor_cr * 1e7

    run_id = _acquire_run(session, resume_run_id)
    print(f"\n=== TB8 ingest — run_id={run_id} (resume={bool(resume_run_id)}) ===")
    print(f"panel: {start_date} → {panel_end}  (FINAL_OOS stays pristine)")

    # --- Step 1: universe master (OFFLINE, membership-derived) ---
    print("\n[1/7] populate_universe (membership-derived, offline)…")
    stats_u = populate_universe(
        session, lambda: membership_derived_listings(), run_id, resume=True
    )
    print(
        f"      total={stats_u.total} inserted={stats_u.inserted} "
        f"updated={stats_u.updated} failed={stats_u.failed} "
        f"skipped_ckpt={stats_u.skipped_checkpoint}"
    )

    # --- Step 2: cross-check vs v2 price universe (surfaced, Rule 12) ---
    print("\n[2/7] cross_check_against_price_universe…")
    report = cross_check_against_price_universe(session, read_price_universe_isins())
    if report.ok:
        print(
            f"      CLEAN — price={report.price_universe_count} "
            f"master={report.master_count}, 0 missing"
        )
    else:
        print(
            f"      ⚠ {len(report.missing_from_master)} price ISIN(s) absent "
            f"from master (surfaced): {report.missing_from_master[:5]}…"
        )

    # --- Step 3: symbol map (OFFLINE) + smoke ISIN selection ---
    prices = store.read_prices_adjusted(start=start_date, end=panel_end)
    prices["date"] = pd.to_datetime(prices["date"])
    rebalance_dates = monthly_rebalance_dates(prices, start_date, panel_end)

    if limit is not None:
        # Smoke: pick top-N liquid names at a mid-panel reference date.
        ref = rebalance_dates[len(rebalance_dates) // 2]
        symbol_map = select_smoke_isins(prices, ref, liq_floor_rupees, limit)
        print(
            f"\n[3/7] SMOKE — {len(symbol_map)} ISINs selected at ref={ref} "
            f"(top adv_20)"
        )
    else:
        full = store.read_isin_symbol_map().sort_values("last_date")
        symbol_map = dict(zip(full["isin"], full["symbol"]))
        print(f"\n[3/7] symbol_map: {len(symbol_map)} ISINs (full panel)")

    if not do_live:
        print("\n(do_live=False — offline stages only; gate skipped.)")
        return run_id, None, None

    smoke_isins = set(symbol_map)

    # --- Step 4: filing index (LIVE NSE — bounded, checkpointed) ---
    print(f"\n[4/7] populate_filing_index — LIVE NSE × {len(symbol_map)} ISINs…")
    stats_f = populate_filing_index(
        session, fetch_nse_filing_index, symbol_map, run_id, resume=True
    )
    print(
        f"      isins={stats_f.total_isins} rows_inserted={stats_f.rows_inserted} "
        f"isins_failed={stats_f.isins_failed} pit_violations={stats_f.pit_violations} "
        f"skipped_ckpt={stats_f.isins_skipped_checkpoint}"
    )

    # --- Step 5: line items (LIVE NSE XBRL — long pole, checkpointed) ---
    print("\n[5/7] populate_line_items — LIVE NSE XBRL…")
    stats_l = populate_line_items(session, fetch_xbrl_document, run_id, resume=True)
    print(
        f"      filings={stats_l.total_filings} rows_inserted={stats_l.rows_inserted} "
        f"skipped_existing={stats_l.rows_skipped_existing} "
        f"failed={stats_l.filings_failed} with_unmapped={stats_l.filings_with_unmapped}"
    )

    # --- Step 6: acceptance gate over the ingested DISCOVERY panel ---
    print("\n[6/7] run_acceptance_gate…")
    restrict = smoke_isins if limit is not None else None
    eligible_on_date = make_eligible_on_date(prices, liq_floor_rupees, restrict)
    gate_inputs = _assemble_gate_inputs(session, sorted(smoke_isins), rebalance_dates)
    result = run_acceptance_gate(
        session,
        eligible_on_date=eligible_on_date,
        rebalance_dates=rebalance_dates,
        reference_reader=make_recon_reader(session),
        **gate_inputs,
    )

    # --- Step 7: verdict + DISCOVERY_START pin ---
    print("\n[7/7] verdict + DISCOVERY_START pin\n")
    print(result.summary())
    pinned = pin_discovery_start(eligible_on_date, session, rebalance_dates)
    print(
        f"\nDurable-≥75%-by-name DISCOVERY_START: "
        f"{pinned.isoformat() if pinned else 'NONE (coverage never stabilizes)'}"
    )

    run = session.get(PipelineRun, run_id)
    run.status = "completed"
    session.commit()

    return run_id, result, pinned


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="TB8 production ingest + §6 gate run")
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="end-to-end smoke on a bounded ISIN subset (use with --limit)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap ISINs entering the LIVE stages (smoke). Omit for the full panel.",
    )
    ap.add_argument(
        "--resume",
        default=None,
        help="resume an existing run_id from its last checkpoint",
    )
    ap.add_argument(
        "--offline-only",
        action="store_true",
        help="run only the offline stages (universe + cross-check); skip the gate",
    )
    args = ap.parse_args()

    limit = args.limit if (args.smoke or args.limit is not None) else None

    session = SessionLocal()
    try:
        run_ingest(
            session,
            limit=limit,
            resume_run_id=args.resume,
            do_live=not args.offline_only,
        )
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
