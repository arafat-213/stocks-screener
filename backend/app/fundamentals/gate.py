"""
fundamentals.gate — TB7: data acceptance gate (§6 five checks → PASS / FAIL).

This module runs the five §6 checks against the assembled fundamentals panel.
Every threshold used here comes from ``data_config.py`` (TB0-locked §8 constants).
NO threshold may be introduced or loosened here in response to the result
(Rule 12 — moving the stick is the v1 data sin applied to data).

Overall contract
----------------
``run_acceptance_gate(...)`` returns a ``GateResult``.  A ``verdict`` of "PASS"
means ``03_TRACK_B_PREREG.md`` may be written.  Any "FAIL" means Track B closes
as a research note and ``FINAL_OOS`` remains pristine (spec §7).

The five checks
---------------
§6.1  Coverage (dual)       — ≥90% by weight AND ≥75% by name
§6.2  PIT integrity         — zero available_date ≤ period_end violations
§6.3  Survivorship presence — known in-window delistings in the master
§6.4  Look-ahead replay     — no future-filed/restated figure leaks in (TB4+TB5 e2e)
§6.5  Reconciliation        — RECON_SAMPLE_N ISIN-quarters within RECON_TOLERANCE

Seam conventions (CLAUDE.md §5 — never hit live exchange in tests)
-------------------------------------------------------------------
``EligibleOnDate`` and ``ReconReader`` are Callable seams; tests inject fixtures,
production passes the real price-layer reader and an NSE XBRL re-parser.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from app.fundamentals.data_config import (
    COVERAGE_THRESHOLD_NAME,
    COVERAGE_THRESHOLD_WEIGHT,
    RECON_TOLERANCE,
)
from app.fundamentals.models import (
    FundamentalsFilingIndex,
    FundamentalsLineItemVersion,
    FundamentalsUniverse,
)
from app.fundamentals.reader import _cutoff, read_fundamentals_asof

# ---------------------------------------------------------------------------
# Seam types
# ---------------------------------------------------------------------------

# Returns [(isin, weight)] for all liquidity-eligible ISINs on a given date.
# Weight is any positive float (e.g. adv_20 as a market-cap proxy).
# Tests inject a fixture; production passes a function over the price Parquet.
EligibleOnDate = Callable[[datetime.date], list[tuple[str, float]]]

# Given [(isin, period_end)], returns reference values per (isin, period_end).
# Used for the §6.5 reconciliation spot-audit.
# Tests inject synthetic "expected" values; production re-parses the XBRL filing.
ReconReader = Callable[
    [list[tuple[str, datetime.date]]],
    dict[tuple[str, datetime.date], dict[str, float | None]],
]

# ---------------------------------------------------------------------------
# Per-check result
# ---------------------------------------------------------------------------

_LINE_ITEMS_CHECKED = ("revenue", "net_income", "total_equity", "total_assets")


@dataclass(frozen=True)
class GateCheck:
    """Result of one §6 acceptance check."""

    name: str
    passed: bool
    detail: str


# ---------------------------------------------------------------------------
# Aggregated gate result
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    checks: list[GateCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def verdict(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def summary(self) -> str:
        lines: list[str] = []
        for c in self.checks:
            tag = "PASS" if c.passed else "FAIL"
            lines.append(f"  [{tag}] {c.name}: {c.detail}")
        lines.append(f"\nOverall TB7 verdict: {self.verdict}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# §6.1  Coverage (dual gate)
# ---------------------------------------------------------------------------


def _filers_asof(session: Session, isins: list[str], cutoff: datetime.date) -> set[str]:
    """ISINs in ``isins`` that had made ≥1 filing of any kind by ``cutoff``.

    Reads the filing index (which carries ALL filings, including no-XBRL
    placeholder ones), so a name that filed results but had no XBRL document
    still counts as a *filer* — it stays in the §6.1 denominator and, if its
    line items were never ingested, is correctly counted as an uncovered gap.
    Only names that had filed *nothing at all* as-of ``cutoff`` are absent here.
    """
    if not isins:
        return set()
    rows = (
        session.query(FundamentalsFilingIndex.isin)
        .filter(
            FundamentalsFilingIndex.isin.in_(isins),
            FundamentalsFilingIndex.available_date <= cutoff,
        )
        .distinct()
        .all()
    )
    return {r.isin for r in rows}


def check_coverage(
    session: Session,
    eligible_on_date: EligibleOnDate,
    rebalance_dates: list[datetime.date],
) -> GateCheck:
    """§6.1 — dual coverage: ≥90% weight AND ≥75% name on each rebalance date.

    Denominator = liquidity-eligible DISCOVERY universe from ``eligible_on_date``
    (NOT raw universe_membership — §6.1 denominator pin), further restricted to
    names that had filed something as-of D (the §10 "filers-only" refinement,
    pre-registered 2026-06-19): a name that listed days before the rebalance has
    no fundamentals on file *by construction* — it cannot have a TTM set yet, so
    counting it against fundamentals coverage measures IPO timing, not data
    quality. Excluding only zero-filing-history names keeps every genuine gap
    (a long-listed name whose filing we failed to ingest) in the denominator.
    The §8.2 floors (90/75) are UNCHANGED — only the denominator is refined.
    Both TB0-locked floors must hold on EVERY checked date; one below = FAIL.
    """
    failing: list[str] = []
    date_count = 0

    for D in rebalance_dates:
        eligible = eligible_on_date(D)
        if not eligible:
            continue

        # §10 filers-only denominator: drop names with zero filings as-of D.
        filers = _filers_asof(session, [i for i, _ in eligible], _cutoff(D))
        eligible = [(i, w) for i, w in eligible if i in filers]
        if not eligible:
            continue
        date_count += 1

        total_count = len(eligible)
        total_weight = sum(w for _, w in eligible)
        covered_count = 0
        covered_weight = 0.0

        for isin, weight in eligible:
            if read_fundamentals_asof(session, isin, D):
                covered_count += 1
                covered_weight += weight

        name_pct = covered_count / total_count if total_count else 0.0
        weight_pct = covered_weight / total_weight if total_weight else 0.0

        if name_pct < COVERAGE_THRESHOLD_NAME or weight_pct < COVERAGE_THRESHOLD_WEIGHT:
            failing.append(
                f"{D.isoformat()}: name={name_pct:.0%} "
                f"(floor={COVERAGE_THRESHOLD_NAME:.0%}), "
                f"weight={weight_pct:.0%} "
                f"(floor={COVERAGE_THRESHOLD_WEIGHT:.0%})"
            )

    if failing:
        return GateCheck(
            name="§6.1_coverage_dual",
            passed=False,
            detail=f"{len(failing)}/{date_count} dates below floor: {'; '.join(failing[:3])}",
        )
    return GateCheck(
        name="§6.1_coverage_dual",
        passed=True,
        detail=(
            f"all {date_count} dates cleared "
            f"name≥{COVERAGE_THRESHOLD_NAME:.0%} and weight≥{COVERAGE_THRESHOLD_WEIGHT:.0%}"
        ),
    )


# ---------------------------------------------------------------------------
# §6.2  PIT integrity
# ---------------------------------------------------------------------------


def check_pit_integrity(
    session: Session,
    sample_isins: list[str],
    sample_dates: list[datetime.date],
) -> GateCheck:
    """§6.2 — PIT integrity: zero available_date ≤ period_end violations.

    Two passes:
    1. Direct DB scan: every stored row for ``sample_isins`` must have
       ``available_date > period_end``.  TB3 rejects bad rows at ingest time;
       this is a safety net for any that slipped through.
    2. Reader replay: for each (isin, D) pair, every snapshot returned by
       ``read_fundamentals_asof`` must satisfy ``available_date ≤ _cutoff(D)``.

    Zero violations required — the PIT contract is the raison d'être of this layer.
    """
    violations: list[str] = []

    # Pass 1 — DB scan.
    rows = (
        session.query(FundamentalsLineItemVersion)
        .filter(FundamentalsLineItemVersion.isin.in_(sample_isins))
        .all()
    )
    for row in rows:
        if row.available_date <= row.period_end:
            violations.append(
                f"{row.isin}/{row.period_end}: "
                f"available_date={row.available_date} not > period_end"
            )

    # Pass 2 — reader replay.
    for isin in sample_isins:
        for D in sample_dates:
            cutoff = _cutoff(D)
            for snap in read_fundamentals_asof(session, isin, D):
                if snap.available_date > cutoff:
                    violations.append(
                        f"reader({isin}@{D}): "
                        f"returned available_date={snap.available_date} > cutoff={cutoff}"
                    )

    if violations:
        return GateCheck(
            name="§6.2_pit_integrity",
            passed=False,
            detail=f"{len(violations)} violation(s): {violations[0]}",
        )
    return GateCheck(
        name="§6.2_pit_integrity",
        passed=True,
        detail=(
            f"0 violations; {len(rows)} rows scanned, "
            f"{len(sample_isins)}×{len(sample_dates)} reader replays"
        ),
    )


# ---------------------------------------------------------------------------
# §6.3  Survivorship presence
# ---------------------------------------------------------------------------


def check_survivorship(
    session: Session,
    known_delistings: list[str],
) -> GateCheck:
    """§6.3 — survivorship presence: every known in-window delisting in the master.

    A silently-absent delisted name is excluded from all Track-B factors for the
    dates it traded — the survivorship bias §1.2 exists to prevent.  Hard fail on
    any missing ISIN.
    """
    master = {row[0] for row in session.query(FundamentalsUniverse.isin).all()}
    missing = [isin for isin in known_delistings if isin not in master]

    if missing:
        return GateCheck(
            name="§6.3_survivorship_presence",
            passed=False,
            detail=(
                f"{len(missing)}/{len(known_delistings)} known delistings "
                f"absent from master: {missing[:5]}"
            ),
        )
    return GateCheck(
        name="§6.3_survivorship_presence",
        passed=True,
        detail=f"all {len(known_delistings)} known delistings present in fundamentals_universe",
    )


# ---------------------------------------------------------------------------
# §6.4  Look-ahead replay
# ---------------------------------------------------------------------------


def check_lookahead_replay(
    session: Session,
    test_cases: list[tuple[str, datetime.date, datetime.date, datetime.date]],
) -> GateCheck:
    """§6.4 — look-ahead replay: no future-filed or restated figure leaks in (TB4+TB5 e2e).

    For each ``(isin, period_end, D_pre, D_post)`` test case:

    * At ``D_pre``: every snapshot the reader returns for that period must have
      ``available_date ≤ _cutoff(D_pre)``.  If a restatement filed AFTER D_pre
      appeared here, information that wasn't public yet leaked backward in time.
    * At ``D_post``: same ``available_date ≤ _cutoff(D_post)`` invariant; for
      periods with a restatement, the reader must return the latest qualifying
      version (verifying the TB5 restatement read-side over the real stored data).

    Any violation is a hard fail — zero tolerance.
    """
    violations: list[str] = []
    cases_checked = 0

    for isin, period_end, D_pre, D_post in test_cases:
        cutoff_pre = _cutoff(D_pre)
        cutoff_post = _cutoff(D_post)

        for D, cutoff in ((D_pre, cutoff_pre), (D_post, cutoff_post)):
            for snap in read_fundamentals_asof(session, isin, D):
                if snap.period_end == period_end and snap.available_date > cutoff:
                    violations.append(
                        f"{isin}/{period_end} at D={D}: "
                        f"available_date={snap.available_date} > cutoff={cutoff}"
                    )

        cases_checked += 1

    if violations:
        return GateCheck(
            name="§6.4_lookahead_replay",
            passed=False,
            detail=f"{len(violations)} violation(s): {violations[0]}",
        )
    return GateCheck(
        name="§6.4_lookahead_replay",
        passed=True,
        detail=f"{cases_checked} (isin, period_end) test cases replayed; no look-ahead detected",
    )


# ---------------------------------------------------------------------------
# §6.5  Reconciliation spot-audit
# ---------------------------------------------------------------------------


def check_reconciliation(
    session: Session,
    sample_isin_periods: list[tuple[str, datetime.date]],
    reference_reader: ReconReader,
) -> GateCheck:
    """§6.5 — reconciliation: RECON_SAMPLE_N ISIN-quarters within RECON_TOLERANCE.

    Compares the latest stored version of each sampled (isin, period_end) against
    the ``reference_reader``'s expected values (which re-parses or cross-checks the
    actual filed statement in production).  Items NULL in either stored or reference
    are skipped — unavailability is not a mismatch.  Any relative deviation above
    RECON_TOLERANCE (±2%) is flagged (Rule 12 — surface, never swallow).
    """
    ref_values = reference_reader(sample_isin_periods)
    mismatches: list[str] = []
    checked = 0

    for isin, period_end in sample_isin_periods:
        ref = ref_values.get((isin, period_end))
        if ref is None:
            continue

        rows = (
            session.query(FundamentalsLineItemVersion)
            .filter_by(isin=isin, period_end=period_end)
            .order_by(FundamentalsLineItemVersion.available_date.desc())
            .all()
        )
        if not rows:
            continue

        row = rows[0]  # latest version
        checked += 1

        for item in _LINE_ITEMS_CHECKED:
            stored = getattr(row, item, None)
            expected = ref.get(item)
            if stored is None or expected is None or expected == 0.0:
                continue
            rel_err = abs(stored - expected) / abs(expected)
            if rel_err > RECON_TOLERANCE:
                mismatches.append(
                    f"{isin}/{period_end.isoformat()}/{item}: "
                    f"stored={stored:.0f} vs ref={expected:.0f} (err={rel_err:.1%})"
                )

    if mismatches:
        return GateCheck(
            name="§6.5_reconciliation",
            passed=False,
            detail=(
                f"{len(mismatches)} mismatch(es) in {checked} ISIN-periods "
                f"(tol=±{RECON_TOLERANCE:.0%}): {mismatches[0]}"
            ),
        )
    return GateCheck(
        name="§6.5_reconciliation",
        passed=True,
        detail=(
            f"{checked}/{len(sample_isin_periods)} ISIN-periods "
            f"reconciled within ±{RECON_TOLERANCE:.0%}"
        ),
    )


# ---------------------------------------------------------------------------
# Top-level gate
# ---------------------------------------------------------------------------


def run_acceptance_gate(
    session: Session,
    *,
    eligible_on_date: EligibleOnDate,
    rebalance_dates: list[datetime.date],
    sample_isins: list[str],
    sample_dates: list[datetime.date],
    known_delistings: list[str],
    lookahead_test_cases: list[tuple[str, datetime.date, datetime.date, datetime.date]],
    recon_sample: list[tuple[str, datetime.date]],
    reference_reader: ReconReader,
) -> GateResult:
    """Run all five §6 acceptance checks against the assembled panel.

    Returns a ``GateResult`` whose ``.verdict`` is "PASS" only when every check
    passes.  A "FAIL" on any single check means ``03_TRACK_B_PREREG.md`` must NOT
    be written and ``FINAL_OOS`` stays pristine (spec §7).

    No threshold may be adjusted here in response to the result (Rule 12).
    All thresholds are read from ``data_config.py`` (TB0-locked §8 constants).
    """
    return GateResult(
        checks=[
            check_coverage(session, eligible_on_date, rebalance_dates),
            check_pit_integrity(session, sample_isins, sample_dates),
            check_survivorship(session, known_delistings),
            check_lookahead_replay(session, lookahead_test_cases),
            check_reconciliation(session, recon_sample, reference_reader),
        ]
    )
