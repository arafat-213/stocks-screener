"""TB2 — survivorship-free universe master: populate + cross-check invariants.

These tests encode WHY the populate behaves as it does (Rule 9), not merely that
it runs:

  - **Survivorship-free**: a delisted name (DHFL) is *retained* with its real
    trading window — the whole point of the master (§3.1 / problem §1.2).
  - **Idempotent** (CLAUDE.md §1): re-running never duplicates an ISIN and
    refreshes in place, so a re-run can't corrupt the spine.
  - **Completeness surfaced** (Rule 12): a price-layer ISIN absent from the
    master is flagged, never silently dropped — else that name loses fundamentals.
  - **Fail loud, not fatal** (CLAUDE.md §1): one bad ISIN is logged to
    `PipelineError` and the run continues; the good rows still land.
  - **Resumable** (CLAUDE.md §1): a checkpointed ISIN is skipped on resume.

Mocks every fetch (no network, no Parquet/disk); isolated in-memory SQLite,
matching the project's test-DB choice and the TB1 fundamentals tests.
"""

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, PipelineCheckpoint, PipelineError, PipelineRun
from app.fundamentals.models import FundamentalsUniverse
from app.fundamentals.universe import (
    PHASE,
    ListingRecord,
    cross_check_against_price_universe,
    populate_universe,
)

RUN_ID = "tb2-test-run"

# A known in-window delisting: Dewan Housing Finance (DHFL), ISIN INE202B01012,
# resolved through NCLT (Piramal) in 2021. Exact dates are illustrative fixture
# values — the invariant under test is that the delisted name is *retained* with
# a closed trading window, not the precise calendar.
DHFL = ListingRecord(
    isin="INE202B01012",
    name="DHFL",
    exchange="NSE",
    list_date=datetime.date(2017, 1, 2),
    delist_date=datetime.date(2021, 9, 30),
)
# A still-listed name: delist_date is None (the survivorship-free "open window").
RELIANCE = ListingRecord(
    isin="INE002A01018",
    name="Reliance",
    exchange="NSE",
    list_date=datetime.date(2017, 1, 2),
    delist_date=None,
)


@pytest.fixture
def session():
    """Isolated in-memory DB with the full schema + a parent PipelineRun row
    (so the checkpoint/error FKs to `pipeline_runs` are realistic)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    sess.add(PipelineRun(run_id=RUN_ID, status="running"))
    sess.commit()
    yield sess
    sess.close()
    Base.metadata.drop_all(bind=engine)


def _source(*records):
    """Build a ListingSource (zero-arg callable) from explicit records."""
    return lambda: list(records)


def test_known_delisting_retained_with_window(session):
    """A delisted name must persist with its real trading window — the master is
    survivorship-free (§3.1)."""
    stats = populate_universe(session, _source(DHFL, RELIANCE), RUN_ID)
    assert (stats.inserted, stats.failed) == (2, 0)

    dhfl = session.get(FundamentalsUniverse, DHFL.isin)
    assert dhfl is not None
    assert dhfl.delist_date == datetime.date(2021, 9, 30)  # retained, not dropped
    assert dhfl.list_date == datetime.date(2017, 1, 2)
    # A still-listed name keeps an open window (NULL delist_date).
    assert session.get(FundamentalsUniverse, RELIANCE.isin).delist_date is None


def test_populate_idempotent_no_duplicate_isins(session):
    """Re-running populate must not duplicate an ISIN and must refresh in place
    (ISIN is the PK; CLAUDE.md §1 idempotency)."""
    populate_universe(session, _source(DHFL, RELIANCE), RUN_ID)
    # Re-process the same ISINs with one field changed. `resume=False` forces a
    # full re-run (a same-run_id resume would correctly *skip* checkpointed ISINs
    # — a different guarantee); write-idempotency is PK-guaranteed regardless.
    renamed = ListingRecord(
        isin=DHFL.isin,
        name="DHFL (renamed)",
        exchange="NSE",
        list_date=DHFL.list_date,
        delist_date=DHFL.delist_date,
    )
    stats2 = populate_universe(
        session, _source(renamed, RELIANCE), RUN_ID, resume=False
    )

    assert session.query(FundamentalsUniverse).count() == 2  # no duplicates
    assert stats2.inserted == 0 and stats2.updated == 2  # both refreshed in place
    assert session.get(FundamentalsUniverse, DHFL.isin).name == "DHFL (renamed)"


def test_price_isin_absent_from_master_is_flagged(session):
    """A price-layer ISIN missing from the master is surfaced, not swallowed
    (Rule 12) — otherwise that name would silently lose fundamentals."""
    populate_universe(session, _source(DHFL, RELIANCE), RUN_ID)
    # Price layer carries a third ISIN the master never saw.
    price_isins = {DHFL.isin, RELIANCE.isin, "INE999X01099"}

    report = cross_check_against_price_universe(session, price_isins)
    assert not report.ok
    assert report.missing_from_master == ["INE999X01099"]

    # The clean case: master covers the whole price universe.
    clean = cross_check_against_price_universe(session, {DHFL.isin, RELIANCE.isin})
    assert clean.ok and clean.missing_from_master == []


def test_per_isin_failure_logged_not_crashed(session):
    """One bad ISIN must log to PipelineError and let the run continue; the good
    rows still land (CLAUDE.md §1 / Rule 12)."""
    bad = ListingRecord(isin=None)  # no ISIN -> can't key the master -> rejected
    stats = populate_universe(session, _source(DHFL, bad, RELIANCE), RUN_ID)

    assert stats.failed == 1
    assert stats.inserted == 2  # the two good names persisted around the failure
    errors = session.query(PipelineError).filter_by(run_id=RUN_ID, phase=PHASE).all()
    assert len(errors) == 1
    assert errors[0].error_type == "unknown"  # ValueError -> classify_error "unknown"


def test_resume_skips_checkpointed_isins(session):
    """An ISIN already checkpointed for the run is skipped on resume — the
    crash-recovery contract (CLAUDE.md §1)."""
    # Pretend a prior crashed run already completed DHFL.
    session.add(
        PipelineCheckpoint(
            run_id=RUN_ID,
            phase=PHASE,
            completed_symbols='["INE202B01012"]',
            started_at=datetime.datetime.now(datetime.timezone.utc),
        )
    )
    session.commit()

    stats = populate_universe(session, _source(DHFL, RELIANCE), RUN_ID)
    assert stats.skipped_checkpoint == 1  # DHFL skipped, not re-touched
    assert stats.inserted == 1  # only RELIANCE inserted
    # DHFL was skipped, so it never got a master row in this resumed run.
    assert session.get(FundamentalsUniverse, DHFL.isin) is None
    assert session.get(FundamentalsUniverse, RELIANCE.isin) is not None
