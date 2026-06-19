"""
TB7 — data acceptance gate invariant tests (Rule 9: encode WHY each matters).

The gate runs five §6 checks against the assembled fundamentals panel before
``03_TRACK_B_PREREG.md`` may be written.  Each test below proves that one check
correctly distinguishes PASS from FAIL for a synthetic dataset.

No network, no live NSE — in-memory SQLite + fixture seams only (CLAUDE.md §5).

Test matrix
-----------
1. Coverage dual gate: weight-only pass ≠ dual pass — name floor is enforced
2. PIT integrity: stored row with available_date ≤ period_end is caught (zero tolerance)
3. Survivorship: absent delisted ISIN is flagged, not silently dropped
4. Look-ahead replay: correct version served at D_pre (v1) and D_post (v2) — TB4+TB5 e2e
5. Reconciliation: stored value outside ±2% tolerance is flagged
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.fundamentals.gate import (
    check_coverage,
    check_lookahead_replay,
    check_pit_integrity,
    check_reconciliation,
    check_survivorship,
    run_acceptance_gate,
)
from app.fundamentals.models import (
    FundamentalsFilingIndex,
    FundamentalsLineItemVersion,
    FundamentalsUniverse,
)
from app.fundamentals.reader import read_fundamentals_asof

# ── Fixture ISINs (all registered in the universe fixture) ────────────────────
ISIN_A = "INE002A01018"  # RELIANCE placeholder
ISIN_B = "INE009A01021"  # INFY placeholder
ISIN_C = "INE040A01034"  # HDFC placeholder
ISIN_D = "INE001A01036"  # TCS placeholder

PERIOD = datetime.date(2022, 3, 31)
V1_AVAIL = datetime.date(2022, 5, 10)  # original filing available date
V2_AVAIL = datetime.date(2022, 8, 1)  # restatement available date


@pytest.fixture
def session():
    """Isolated in-memory SQLite with the full fundamentals schema."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        for isin in (ISIN_A, ISIN_B, ISIN_C, ISIN_D):
            s.add(FundamentalsUniverse(isin=isin, exchange="NSE"))
        s.commit()
        yield s


def _row(
    isin: str,
    period_end: datetime.date,
    available_date: datetime.date,
    net_income: float = 100.0,
    total_equity: float = 500.0,
    revenue: float = 1000.0,
    total_assets: float = 800.0,
) -> FundamentalsLineItemVersion:
    return FundamentalsLineItemVersion(
        isin=isin,
        period_end=period_end,
        available_date=available_date,
        net_income=net_income,
        total_equity=total_equity,
        revenue=revenue,
        total_assets=total_assets,
    )


def _filing(
    isin: str,
    available_date: datetime.date,
    period_end: datetime.date = PERIOD,
) -> FundamentalsFilingIndex:
    """A filing-index row — evidence the name was an established filer as-of D.

    §6.1's filers-only denominator (Option 2) keeps a name only if it had filed
    something by D; a covered name and a genuine-gap name both need this row.
    """
    return FundamentalsFilingIndex(
        isin=isin,
        period_end=period_end,
        available_date=available_date,
        statement_type="Annual",
        source_exchange="NSE",
        document_url=None,
    )


# ── Test 1 — Coverage dual gate ───────────────────────────────────────────────


def test_coverage_dual_gate_name_floor_enforced(session):
    """
    WHY: the weight-only floor (90%) guards large-cap coverage but could pass for a
    cap-heavy/name-thin panel — the exact "large-cap monopoly" failure the 75%
    by-name floor prevents.  If only the top ISIN (carrying 95% of weight) has
    fundamentals, weight_pct=95% (PASS) but name_pct=25% (FAIL).  The dual gate
    must reject this — a panel this thin would silently exclude three out of four
    names from every Track-B factor.
    """
    # Only ISIN_A has fundamentals.
    CHECK_DATE = datetime.date(2022, 7, 1)
    # cutoff(2022-07-01) = 2022-06-29 ≥ V1_AVAIL → v1 qualifies for ISIN_A.
    session.add(_row(ISIN_A, PERIOD, V1_AVAIL))
    # All four are established filers as-of D (filing-index entry ≤ cutoff) so
    # B/C/D stay in the denominator as genuine gaps — the case this test guards.
    for isin in (ISIN_A, ISIN_B, ISIN_C, ISIN_D):
        session.add(_filing(isin, V1_AVAIL))
    session.commit()

    def eligible_on_date(D: datetime.date) -> list[tuple[str, float]]:
        # ISIN_A carries 95% of total weight; the other three share 5%.
        return [
            (ISIN_A, 9500.0),
            (ISIN_B, 100.0),
            (ISIN_C, 200.0),
            (ISIN_D, 200.0),
        ]

    result = check_coverage(session, eligible_on_date, [CHECK_DATE])

    assert not result.passed, (
        "should FAIL: name_pct=1/4=25% < 75% threshold even though weight_pct=95% ≥ 90%"
    )
    assert "25%" in result.detail or "floor" in result.detail or "name" in result.detail


def test_coverage_excludes_nonfilers_from_denominator(session):
    """
    WHY: §6.1's filers-only denominator (Option 2, pre-registered 2026-06-19). A
    name that listed days before D has no fundamentals on file *by construction* —
    counting it against fundamentals coverage measures IPO timing, not data
    quality (the 2021-07 Zomato / 2021-11 Paytm-wave artifact). Such a name (no
    filing-index entry ≤ cutoff) must be DROPPED from the denominator entirely;
    only zero-filing-history names are dropped — genuine gaps (a long-listed name
    whose filing we failed to ingest) still count, so this is not a free pass.

    Panel: ISIN_A (covered, est. filer) + ISIN_B (huge weight, NON-filer / fresh
    IPO). Counted, ISIN_B's weight would sink the 90% floor → FAIL. Excluded as a
    non-filer, the date PASSES on the established-filer ISIN_A alone. The §8.2
    floors are untouched — only the denominator narrows.
    """
    CHECK_DATE = datetime.date(2022, 7, 1)
    cutoff_ok = V1_AVAIL  # 2022-05-10 ≤ cutoff(2022-07-01)=2022-06-29
    # ISIN_A: established filer WITH fundamentals (covered).
    session.add(_row(ISIN_A, PERIOD, cutoff_ok))
    session.add(_filing(ISIN_A, cutoff_ok))
    # ISIN_B: fresh IPO — its only filing is AFTER D (no entry ≤ cutoff).
    session.add(_filing(ISIN_B, datetime.date(2022, 8, 15)))
    session.commit()

    def eligible_on_date(D: datetime.date) -> list[tuple[str, float]]:
        # ISIN_B carries 80% of weight; if counted, weight_pct=20% << 90% → FAIL.
        return [(ISIN_A, 200.0), (ISIN_B, 800.0)]

    result = check_coverage(session, eligible_on_date, [CHECK_DATE])

    assert result.passed, (
        "should PASS: ISIN_B is a non-filer as-of D (fresh IPO) and is excluded "
        "from the denominator; coverage is then 100% on the established filer ISIN_A"
    )


# ── Test 2 — PIT integrity ────────────────────────────────────────────────────


def test_pit_integrity_catches_stored_violation(session):
    """
    WHY: a stored row with available_date ≤ period_end means a filing was (impossibly)
    publicly available on or before the period it reports — a hard PIT violation.
    TB3 rejects such rows at ingest time via PITViolationError, but the gate provides
    a safety net by scanning the DB directly.  Even one such row invalidates the
    look-ahead contract that is the entire reason this layer exists (§1.1).

    Inject the row bypassing ingest (direct ORM insert) to simulate a case where
    the ingest validator was circumvented or data was loaded from an external source.
    """
    period_end = datetime.date(2022, 3, 31)
    bad_avail = period_end  # available_date == period_end — physically impossible

    # Insert directly into the DB (bypassing filing_index ingest validation).
    session.add(
        FundamentalsLineItemVersion(
            isin=ISIN_A,
            period_end=period_end,
            available_date=bad_avail,
            net_income=100.0,
        )
    )
    session.commit()

    result = check_pit_integrity(
        session,
        sample_isins=[ISIN_A],
        sample_dates=[datetime.date(2022, 7, 1)],
    )

    assert not result.passed, (
        "should FAIL: available_date == period_end violates the PIT invariant"
    )
    assert "not > period_end" in result.detail or "available_date" in result.detail


# ── Test 3 — Survivorship presence ───────────────────────────────────────────


def test_survivorship_flags_absent_delisting(session):
    """
    WHY: a delisted name absent from fundamentals_universe is excluded from Track-B
    factors for all the dates it traded.  This is pure survivorship bias — exactly
    problem §1.2.  The gate must flag any known in-window delisting that is missing
    from the master, rather than silently producing a survivor-only panel.

    The universe fixture registered ISIN_A through ISIN_D.  A fifth ISIN
    (representing a known in-window delisting like DHFL) was never inserted;
    the gate must surface it.
    """
    ISIN_DELISTED = (
        "INE202B01012"  # synthetic delisted ISIN; not in the universe fixture
    )

    result = check_survivorship(
        session,
        known_delistings=[
            ISIN_A,
            ISIN_DELISTED,
        ],  # ISIN_A present; ISIN_DELISTED absent
    )

    assert not result.passed, (
        "should FAIL: ISIN_DELISTED is not in fundamentals_universe"
    )
    assert ISIN_DELISTED in result.detail


# ── Test 4 — Look-ahead replay ────────────────────────────────────────────────


def test_lookahead_replay_correct_version_at_each_date(session):
    """
    WHY: §6.4 is the TB4+TB5 end-to-end integration check.  For a period with a
    restatement (v1 original, v2 updated), the pipeline must serve v1 before the
    restatement was publicly disseminated and v2 once it was.  Any look-ahead would
    mean a decision on D used information that wasn't available until after D — the
    core correctness property the lag+available_date mechanism exists to enforce.

    The check verifies PASS: both versions correctly stored; gate confirms v1 is the
    only qualifying version at D_pre (before v2's cutoff) and v2 wins at D_post.
    """
    # v1: original annual results filed 2022-05-10.
    # v2: restatement filed 2022-08-01 (upward revision to net_income).
    session.add(_row(ISIN_A, PERIOD, V1_AVAIL, net_income=100.0))
    session.add(_row(ISIN_A, PERIOD, V2_AVAIL, net_income=115.0))
    session.commit()

    # D_pre = 2022-07-15 (Friday):
    #   cutoff = busday_offset(2022-07-15, -2) = 2022-07-13
    #   V1_AVAIL=2022-05-10 ≤ 2022-07-13 → v1 qualifies
    #   V2_AVAIL=2022-08-01 > 2022-07-13  → v2 does NOT qualify
    D_pre = datetime.date(2022, 7, 15)

    # D_post = 2022-10-03 (Monday; 2022-10-01 is Saturday — busday_offset rejects it):
    #   cutoff = busday_offset(2022-10-03, -2) = 2022-09-29
    #   V2_AVAIL=2022-08-01 ≤ 2022-09-29 → v2 qualifies; reader picks latest = v2
    D_post = datetime.date(2022, 10, 3)

    test_cases = [(ISIN_A, PERIOD, D_pre, D_post)]
    result = check_lookahead_replay(session, test_cases)

    assert result.passed, (
        f"should PASS for correctly-stored restatement (no look-ahead): {result.detail}"
    )

    # Belt-and-suspenders: confirm the reader itself returns the right version at each date.
    pre_snaps = read_fundamentals_asof(session, ISIN_A, D_pre)
    post_snaps = read_fundamentals_asof(session, ISIN_A, D_post)

    assert len(pre_snaps) == 1
    assert pre_snaps[0].available_date == V1_AVAIL, (
        "at D_pre only v1 (original) should be visible"
    )
    assert pre_snaps[0].net_income == 100.0

    assert len(post_snaps) == 1
    assert post_snaps[0].available_date == V2_AVAIL, (
        "at D_post v2 (restatement) should win over v1"
    )
    assert post_snaps[0].net_income == 115.0


# ── Test 5 — Reconciliation ───────────────────────────────────────────────────


def test_reconciliation_flags_value_above_tolerance(session):
    """
    WHY: §6.5 catches systematic parse errors or XBRL tag-mapping bugs that produce
    WRONG values (not just missing ones).  A revenue figure stored at 1100 when the
    actual filed value is 1000 is a 10% error — well above the ±2% RECON_TOLERANCE
    locked in TB0 §8.3.  The gate must surface this mismatch so it can be traced
    back to a parser bug and corrected; silently accepting wrong values would corrupt
    every P/E and revenue-growth computation downstream.
    """
    session.add(
        FundamentalsLineItemVersion(
            isin=ISIN_A,
            period_end=PERIOD,
            available_date=V1_AVAIL,
            revenue=1100.0,  # stored: 1100 — WRONG (parser bug inflated by 10%)
            net_income=100.0,  # stored: matches reference (within tolerance)
            total_equity=500.0,
            total_assets=800.0,
        )
    )
    session.commit()

    def reference_reader(
        pairs: list[tuple[str, datetime.date]],
    ) -> dict[tuple[str, datetime.date], dict[str, float | None]]:
        # Reference: actual filed revenue = 1000 (±2% floor = 980–1020); stored=1100 is outside.
        return {
            (ISIN_A, PERIOD): {
                "revenue": 1000.0,
                "net_income": 100.0,  # matches stored exactly → no mismatch
                "total_equity": 500.0,
                "total_assets": 800.0,
            }
        }

    result = check_reconciliation(
        session,
        sample_isin_periods=[(ISIN_A, PERIOD)],
        reference_reader=reference_reader,
    )

    assert not result.passed, (
        "should FAIL: revenue stored=1100 vs ref=1000 is 10% > RECON_TOLERANCE=2%"
    )
    assert "revenue" in result.detail
    assert "10%" in result.detail or "err=" in result.detail


# ── Integration smoke-test — run_acceptance_gate aggregates correctly ─────────


def test_run_acceptance_gate_fail_aggregation(session):
    """
    WHY: ``run_acceptance_gate`` must return a GateResult whose ``.verdict`` is "FAIL"
    if ANY of the five checks fails.  This test ensures the aggregation logic doesn't
    accidentally AND the pass-booleans in a way that lets one FAIL be masked by
    four PASSes.  The spec §7 is clear: any FAIL stops Track B.
    """
    # Build a panel that passes §6.2 / §6.3 / §6.4 / §6.5 but FAILS §6.1 (coverage):
    # ISIN_A has fundamentals; the other three do not.
    session.add(_row(ISIN_A, PERIOD, V1_AVAIL))
    for isin in (ISIN_A, ISIN_B, ISIN_C, ISIN_D):
        session.add(_filing(isin, V1_AVAIL))
    session.commit()

    CHECK_DATE = datetime.date(2022, 7, 1)

    def eligible_on_date(D: datetime.date) -> list[tuple[str, float]]:
        # ISIN_A = 95% weight, three others = 5% — coverage will be 25% by name (FAIL).
        return [(ISIN_A, 950.0), (ISIN_B, 10.0), (ISIN_C, 20.0), (ISIN_D, 20.0)]

    def reference_reader(pairs):
        return {(ISIN_A, PERIOD): {"revenue": 1000.0, "net_income": 100.0}}

    result = run_acceptance_gate(
        session,
        eligible_on_date=eligible_on_date,
        rebalance_dates=[CHECK_DATE],
        sample_isins=[ISIN_A],
        sample_dates=[CHECK_DATE],
        known_delistings=[ISIN_A],  # all present → §6.3 passes
        lookahead_test_cases=[(ISIN_A, PERIOD, CHECK_DATE, CHECK_DATE)],
        recon_sample=[(ISIN_A, PERIOD)],
        reference_reader=reference_reader,
    )

    assert not result.passed, "GateResult.passed must be False when any check fails"
    assert result.verdict == "FAIL"
    coverage_check = next(c for c in result.checks if "coverage" in c.name)
    assert not coverage_check.passed
    assert len(result.checks) == 5, "gate must run exactly 5 checks"
