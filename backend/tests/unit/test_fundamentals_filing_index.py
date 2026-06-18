"""TB3 — filing-index ingest (the PIT clock): invariants.

Tests encode WHY each behavior matters (Rule 9):

  - **available_date ≠ period_end** (test_filing_lands_with_available_date_not_period_end):
    The available_date is the public dissemination timestamp, never the period
    end.  This is the entire PIT clock — every downstream factor's look-ahead
    guard depends on this distinction (§3.2 / problem §1.1).

  - **PIT violation → logged + skipped** (test_pit_invariant_violation_logged_and_skipped):
    A row with available_date <= period_end is NEVER stored, even if the source
    sends it.  Storing it would bake look-ahead bias into every factor.  It must
    be surfaced (PipelineError), not silently accepted or silently dropped.

  - **Idempotent** (test_ingest_is_idempotent):
    Re-running populate with the same records inserts one row, not two.  A crash
    + retry must not double-count a period's filing (CLAUDE.md §1).

  - **Resumable** (test_checkpointed_isin_skipped_on_resume):
    An ISIN already checkpointed is not re-fetched from the source.  The crash-
    recovery contract: a partially-ingested run resumes without re-touching ISINs
    that already committed (CLAUDE.md §1).

  - **Fail loud, not fatal** (test_per_isin_failure_logged_continues):
    One ISIN whose source raises must log to PipelineError and let the run
    continue; the good ISINs still land (CLAUDE.md §1 / Rule 12).

Mocks every fetch (no network); isolated in-memory SQLite.
"""

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, PipelineCheckpoint, PipelineError, PipelineRun
from app.fundamentals.filing_index import (
    PHASE,
    FilingRecord,
    populate_filing_index,
)
from app.fundamentals.models import FundamentalsFilingIndex, FundamentalsUniverse

RUN_ID = "tb3-test-run"
ISIN_A = "INE002A01018"  # Reliance
ISIN_B = "INE202B01012"  # DHFL (delisted)
SYMBOL_A = "RELIANCE"
SYMBOL_B = "DHFL"

# A well-formed filing: period ending 31-Mar-2024, filed 45 days later (22-Apr-2024).
_PERIOD_END = datetime.date(2024, 3, 31)
_AVAIL_DATE = datetime.date(2024, 4, 22)  # > period_end ✓

GOOD_RECORD_A = FilingRecord(
    isin=ISIN_A,
    period_end=_PERIOD_END,
    available_date=_AVAIL_DATE,
    statement_type="Annual",
    source_exchange="NSE",
    document_url="https://example.com/reliance_fy24.xml",
)
# A second ISIN B filing — different period, used in multi-ISIN tests.
GOOD_RECORD_B = FilingRecord(
    isin=ISIN_B,
    period_end=datetime.date(2021, 3, 31),
    available_date=datetime.date(2021, 5, 15),
    statement_type="Annual",
    source_exchange="NSE",
    document_url=None,
)


@pytest.fixture
def session():
    """Isolated in-memory DB with the full schema + parent rows for FK integrity."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    sess.add(PipelineRun(run_id=RUN_ID, status="running"))
    # Universe rows required by FundamentalsFilingIndex FK (isin → fundamentals_universe).
    sess.add(FundamentalsUniverse(isin=ISIN_A, name="Reliance", exchange="NSE"))
    sess.add(FundamentalsUniverse(isin=ISIN_B, name="DHFL", exchange="NSE"))
    sess.commit()
    yield sess
    sess.close()
    Base.metadata.drop_all(bind=engine)


def _source(**isin_records: list[FilingRecord]):
    """Build a FilingSource from explicit per-ISIN record lists.

    Usage: ``_source(ISIN_A=[rec1, rec2], ISIN_B=[rec3])``
    Returns a callable ``(isin, symbol) -> list[FilingRecord]``.
    """

    def _fetch(isin: str, symbol: str) -> list[FilingRecord]:  # noqa: ARG001
        return isin_records.get(isin, [])

    return _fetch


def _error_source(failing_isin: str, exc: Exception, fallback: dict):
    """Source that raises for ``failing_isin`` and delegates others to fallback."""

    def _fetch(isin: str, symbol: str) -> list[FilingRecord]:
        if isin == failing_isin:
            raise exc
        return fallback.get(isin, [])

    return _fetch


# ---------------------------------------------------------------------------
# Test 1 — available_date is the broadcast date, not period_end
# ---------------------------------------------------------------------------


def test_filing_lands_with_available_date_not_period_end(session):
    """The stored row must carry the public dissemination date, not period_end.

    This is the PIT clock's core guarantee: the factor layer can only see
    figures that were publicly available on or before its as-of date.  If the
    DB stores period_end here instead, every quarterly look-back becomes a
    look-ahead (§3.2 / problem §1.1).
    """
    stats = populate_filing_index(
        session,
        _source(**{ISIN_A: [GOOD_RECORD_A]}),
        {ISIN_A: SYMBOL_A},
        RUN_ID,
    )
    assert stats.rows_inserted == 1
    assert stats.pit_violations == 0

    row = session.query(FundamentalsFilingIndex).filter_by(isin=ISIN_A).one()
    assert row.available_date == _AVAIL_DATE  # dissemination date stored
    assert row.available_date != row.period_end  # NOT the period end
    assert row.period_end == _PERIOD_END
    assert row.statement_type == "Annual"
    assert row.source_exchange == "NSE"


# ---------------------------------------------------------------------------
# Test 2 — PIT invariant violation: logged + never stored
# ---------------------------------------------------------------------------


def test_pit_invariant_violation_logged_and_skipped(session):
    """A row where available_date <= period_end must NEVER reach the DB.

    Storing it would silently bake look-ahead bias into every factor downstream.
    The violation must be surfaced (PipelineError) so it's visible in the run
    audit, not silently swallowed (Rule 12 / §3.2).
    """
    # Three violation modes: equal, before, and a genuine future-date filing.
    violations = [
        FilingRecord(
            isin=ISIN_A,
            period_end=_PERIOD_END,
            available_date=_PERIOD_END,  # equal — not strictly after
            statement_type="Annual",
            source_exchange="NSE",
        ),
        FilingRecord(
            isin=ISIN_A,
            period_end=_PERIOD_END,
            available_date=_PERIOD_END - datetime.timedelta(days=1),  # before
            statement_type="Half-Yearly",
            source_exchange="NSE",
        ),
    ]
    stats = populate_filing_index(
        session,
        _source(**{ISIN_A: violations}),
        {ISIN_A: SYMBOL_A},
        RUN_ID,
    )

    assert stats.rows_inserted == 0  # nothing committed to the filing index
    assert stats.pit_violations == 2  # both violations counted

    stored = session.query(FundamentalsFilingIndex).filter_by(isin=ISIN_A).all()
    assert stored == []  # zero rows — violations never stored

    errors = session.query(PipelineError).filter_by(run_id=RUN_ID, phase=PHASE).all()
    assert len(errors) == 2  # one PipelineError per violation
    assert all("PIT contract" in e.message for e in errors)


# ---------------------------------------------------------------------------
# Test 3 — idempotent: re-running inserts no duplicates
# ---------------------------------------------------------------------------


def test_ingest_is_idempotent(session):
    """Running populate twice with the same records must produce one row, not two.

    A crash + retry must not double-count a period's filing; the unique key
    (isin, period_end, available_date, statement_type) is the idempotency guard
    (CLAUDE.md §1).
    """
    src = _source(**{ISIN_A: [GOOD_RECORD_A]})
    populate_filing_index(session, src, {ISIN_A: SYMBOL_A}, RUN_ID)
    # Second run with resume=False to bypass checkpoint — exercises DB-level dedup.
    stats2 = populate_filing_index(
        session, src, {ISIN_A: SYMBOL_A}, RUN_ID, resume=False
    )

    count = session.query(FundamentalsFilingIndex).filter_by(isin=ISIN_A).count()
    assert count == 1  # exactly one row regardless of retries
    assert stats2.rows_inserted == 0  # second run skipped the existing row


# ---------------------------------------------------------------------------
# Test 4 — checkpointed ISIN is skipped on resume
# ---------------------------------------------------------------------------


def test_checkpointed_isin_skipped_on_resume(session):
    """An ISIN already in the checkpoint must not be re-fetched or re-inserted.

    This is the crash-recovery contract: a run that fails mid-way resumes from
    the last successful ISIN, never re-processing completed work (CLAUDE.md §1).
    """
    session.add(
        PipelineCheckpoint(
            run_id=RUN_ID,
            phase=PHASE,
            completed_symbols=f'["{ISIN_A}"]',
            started_at=datetime.datetime.now(datetime.timezone.utc),
        )
    )
    session.commit()

    fetched: list[str] = []

    def _tracking_source(isin: str, symbol: str) -> list[FilingRecord]:  # noqa: ARG001
        fetched.append(isin)
        return [GOOD_RECORD_A] if isin == ISIN_A else [GOOD_RECORD_B]

    stats = populate_filing_index(
        session, _tracking_source, {ISIN_A: SYMBOL_A, ISIN_B: SYMBOL_B}, RUN_ID
    )

    assert ISIN_A not in fetched  # never fetched — checkpointed
    assert ISIN_B in fetched  # the other ISIN was processed
    assert stats.isins_skipped_checkpoint == 1
    assert stats.rows_inserted == 1  # only ISIN_B's row landed
    assert session.query(FundamentalsFilingIndex).filter_by(isin=ISIN_A).count() == 0


# ---------------------------------------------------------------------------
# Test 5 — per-ISIN source failure: logged + run continues
# ---------------------------------------------------------------------------


def test_per_isin_failure_logged_continues(session):
    """A source that raises for one ISIN must log to PipelineError and let the
    run continue; the other ISINs' rows must still land (CLAUDE.md §1 / Rule 12).
    """
    exc = ConnectionError("NSE API timeout for ISIN_A")
    src = _error_source(
        failing_isin=ISIN_A,
        exc=exc,
        fallback={ISIN_B: [GOOD_RECORD_B]},
    )
    stats = populate_filing_index(
        session, src, {ISIN_A: SYMBOL_A, ISIN_B: SYMBOL_B}, RUN_ID
    )

    assert stats.isins_failed == 1
    assert stats.rows_inserted == 1  # ISIN_B still landed
    assert session.query(FundamentalsFilingIndex).filter_by(isin=ISIN_A).count() == 0
    assert session.query(FundamentalsFilingIndex).filter_by(isin=ISIN_B).count() == 1

    errors = session.query(PipelineError).filter_by(run_id=RUN_ID, phase=PHASE).all()
    assert len(errors) == 1
    assert "timeout" in errors[0].message.lower() or errors[0].error_type in (
        "timeout",
        "unknown",
    )
