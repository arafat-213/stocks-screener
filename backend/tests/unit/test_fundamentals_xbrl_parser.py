"""TB4 — XBRL parser + line-item write-side invariants.

Tests encode WHY each behavior matters (Rule 9):

  - **All 8 items parse from standard tags**
    (test_all_line_items_parse_from_standard_tags):
    The tag mapping must cover every target field from a representative Ind-AS
    XBRL document.  If any item silently drops to None here, downstream factors
    built on it will silently have no signal.

  - **Unmapped item → NULL not zero + PipelineError**
    (test_unmapped_items_are_null_not_zero_and_logged):
    A missing line item is NULL (Rule 12).  Zero-filling would inject a false
    signal into every factor that divides by it (e.g. EV/EBIT → ∞ from 0).
    The PipelineError surfaces the gap so it's visible in the run audit.

  - **Restatement writes a new row, original preserved**
    (test_restatement_writes_new_row_original_preserved):
    Two filings for the same period_end but different available_dates must
    BOTH persist (§3.4 write-side) — the as-of reader (TB5) relies on finding
    the vintage as known on each historical date, not just the latest figure.

  - **Populate is idempotent**
    (test_populate_is_idempotent):
    Running the parser twice against the same filing must produce one row, not
    two.  A crash + retry must not double-count a period (CLAUDE.md §1).

  - **Per-filing fetcher failure → logged + run continues**
    (test_per_filing_failure_logged_and_run_continues):
    One ISIN whose fetch fails must log to PipelineError and let the run
    continue; the other ISIN's row still lands (CLAUDE.md §1 / Rule 12).

Fixture XBRL only — no network (CLAUDE.md §5).  Isolated in-memory SQLite.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, PipelineError, PipelineRun
from app.fundamentals.models import (
    FundamentalsFilingIndex,
    FundamentalsLineItemVersion,
    FundamentalsUniverse,
)
from app.fundamentals.xbrl_parser import (
    PHASE,
    parse_xbrl,
    populate_line_items,
)

RUN_ID = "tb4-test-run"
ISIN_A = "INE002A01018"  # Reliance (primary)
ISIN_B = "INE090A01021"  # ICICI Bank (secondary)

_PERIOD_END_A = datetime.date(2023, 3, 31)
_AVAIL_DATE_A1 = datetime.date(2023, 5, 2)  # first filing
_AVAIL_DATE_A2 = datetime.date(2023, 8, 10)  # restatement (later vintage)
_AVAIL_DATE_B = datetime.date(2022, 5, 20)
_PERIOD_END_B = datetime.date(2022, 3, 31)

DOC_URL_A1 = "https://example.com/rel_fy23_v1.xml"
DOC_URL_A2 = "https://example.com/rel_fy23_v2.xml"
DOC_URL_B = "https://example.com/icici_fy22.xml"

# ---------------------------------------------------------------------------
# Fixture XBRL helpers
# ---------------------------------------------------------------------------

_STD_NS = 'xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2014-03-31/in-bse-fin"'


def _xbrl(
    revenue: float | None = None,
    net_income: float | None = None,
    pbt: float | None = None,
    finance_costs: float | None = None,
    equity: float | None = None,
    total_assets: float | None = None,
    lt_borrowings: float | None = None,
    st_borrowings: float | None = None,
    shares: float | None = None,
    cfo: float | None = None,
) -> str:
    """Build a minimal Ind-AS XBRL document with the requested line items.

    EBIT is derived in the parser as PBT + FinanceCosts — so we expose those
    components here rather than a direct EBIT tag (which doesn't exist in Ind-AS).
    """
    ctx = 'contextRef="duration_2022-04-01_2023-03-31"'
    ins = 'unitRef="INR" decimals="-5"'
    shr = 'unitRef="shares" decimals="0"'

    def el(tag: str, value: float, unit: str = ins) -> str:
        return f"  <in-bse-fin:{tag} {ctx} {unit}>{value}</in-bse-fin:{tag}>"

    elements: list[str] = []
    if revenue is not None:
        elements.append(el("Revenue", revenue))
    if net_income is not None:
        elements.append(el("ProfitLossForPeriod", net_income))
    if pbt is not None:
        elements.append(el("ProfitBeforeExceptionalItemsAndTax", pbt))
    if finance_costs is not None:
        elements.append(el("FinanceCosts", finance_costs))
    if equity is not None:
        elements.append(el("Equity", equity))
    if total_assets is not None:
        elements.append(el("Assets", total_assets))
    if lt_borrowings is not None:
        elements.append(el("LongTermBorrowings", lt_borrowings))
    if st_borrowings is not None:
        elements.append(el("ShortTermBorrowings", st_borrowings))
    if shares is not None:
        elements.append(el("NumberOfSharesOutstanding", shares, unit=shr))
    if cfo is not None:
        elements.append(el("NetCashFlowsFromUsedInOperatingActivities", cfo))

    body = "\n".join(elements)
    return f'<?xml version="1.0"?>\n<xbrl {_STD_NS}>\n{body}\n</xbrl>'


# Full XBRL with all 8 items derivable.
_FULL_XBRL = _xbrl(
    revenue=800_000.0,
    net_income=100_000.0,
    pbt=130_000.0,
    finance_costs=20_000.0,  # → ebit = 150_000
    equity=600_000.0,
    total_assets=1_200_000.0,
    lt_borrowings=200_000.0,
    st_borrowings=50_000.0,  # → total_debt = 250_000
    shares=1_392_015_712.0,
    cfo=155_000.0,
)

# Partial XBRL — revenue and CFO missing (unmapped).
_PARTIAL_XBRL = _xbrl(
    net_income=80_000.0,
    pbt=100_000.0,
    finance_costs=15_000.0,
    equity=500_000.0,
    total_assets=900_000.0,
    lt_borrowings=150_000.0,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    sess.add(FundamentalsUniverse(isin=ISIN_A, name="Reliance", exchange="NSE"))
    sess.add(FundamentalsUniverse(isin=ISIN_B, name="ICICI Bank", exchange="NSE"))
    sess.commit()
    yield sess
    sess.close()
    Base.metadata.drop_all(bind=engine)


def _add_filing(
    sess, isin: str, period_end: datetime.date, avail_date: datetime.date, url: str
):
    sess.add(
        FundamentalsFilingIndex(
            isin=isin,
            period_end=period_end,
            available_date=avail_date,
            statement_type="Annual",
            source_exchange="NSE",
            document_url=url,
        )
    )
    sess.commit()


def _static_fetcher(url_to_text: dict[str, str]):
    """Build an XBRLFetcher that returns pre-canned XBRL text per URL."""

    def _fetch(url: str) -> str:
        if url not in url_to_text:
            raise ValueError(f"Unexpected URL in test: {url!r}")
        return url_to_text[url]

    return _fetch


def _error_fetcher(failing_url: str, fallback: dict[str, str]):
    """Fetcher that raises for one URL and delegates the rest to fallback."""

    def _fetch(url: str) -> str:
        if url == failing_url:
            raise ConnectionError(f"Timeout fetching {url}")
        return fallback[url]

    return _fetch


# ---------------------------------------------------------------------------
# Test 1 — all 8 target items parse from standard Ind-AS tags
# ---------------------------------------------------------------------------


def test_all_line_items_parse_from_standard_tags():
    """The tag mapping must resolve all 8 items from a representative Ind-AS filing.

    A None here means a Track-B factor for that item has no signal — silently
    missing data is worse than a loud failure because it goes undetected until
    the backtest phase (Rule 12 / §3.3).
    """
    result = parse_xbrl(_FULL_XBRL)

    assert result.unmapped_items == [], (
        f"Expected all items mapped; unmapped: {result.unmapped_items}"
    )
    assert result.revenue == 800_000.0
    assert result.net_income == 100_000.0
    # EBIT = PBT (130k) + FinanceCosts (20k) — derived, no direct element
    assert result.ebit == pytest.approx(150_000.0)
    assert result.total_equity == 600_000.0
    assert result.total_assets == 1_200_000.0
    # total_debt = LT (200k) + ST (50k) — component sum fallback
    assert result.total_debt == pytest.approx(250_000.0)
    assert result.shares_outstanding == 1_392_015_712.0
    assert result.cfo == 155_000.0


# ---------------------------------------------------------------------------
# Test 2 — unmapped item → NULL not zero + PipelineError logged
# ---------------------------------------------------------------------------


def test_unmapped_items_are_null_not_zero_and_logged(session):
    """Items absent from the XBRL must be NULL, never 0, and surfaced via PipelineError.

    Zero-filling silently injects a false signal: EV/EBIT → ∞ when ebit=0,
    B/P → ∞ when equity=0.  The gap must be visible in the run audit (Rule 12).
    """
    _add_filing(session, ISIN_A, _PERIOD_END_A, _AVAIL_DATE_A1, DOC_URL_A1)
    fetcher = _static_fetcher({DOC_URL_A1: _PARTIAL_XBRL})

    stats = populate_line_items(session, fetcher, RUN_ID)
    assert stats.rows_inserted == 1
    assert stats.filings_with_unmapped > 0

    row = session.query(FundamentalsLineItemVersion).filter_by(isin=ISIN_A).one()

    # Unmapped items must be NULL, never 0.
    assert row.revenue is None  # missing from _PARTIAL_XBRL
    assert row.shares_outstanding is None
    assert row.cfo is None

    # Items that were present must be populated.
    assert row.net_income == pytest.approx(80_000.0)
    assert row.total_equity == pytest.approx(500_000.0)

    # PipelineError must be logged listing the unmapped fields.
    errors = session.query(PipelineError).filter_by(run_id=RUN_ID, phase=PHASE).all()
    assert len(errors) >= 1
    combined_messages = " ".join(e.message for e in errors)
    assert "unmapped" in combined_messages


# ---------------------------------------------------------------------------
# Test 3 — restatement writes new row, original preserved
# ---------------------------------------------------------------------------


def test_restatement_writes_new_row_original_preserved(session):
    """Two filings for the same period_end differing only by available_date must
    both persist (§3.4 write-side).

    The as-of reader (TB5) must be able to return 'the figure as known on D'
    for any historical D — which requires both vintages to be stored.  An
    overwrite would silently corrupt all historical reconstructions before the
    restatement date.
    """
    _add_filing(session, ISIN_A, _PERIOD_END_A, _AVAIL_DATE_A1, DOC_URL_A1)
    _add_filing(session, ISIN_A, _PERIOD_END_A, _AVAIL_DATE_A2, DOC_URL_A2)

    xbrl_v1 = _xbrl(net_income=100_000.0, equity=600_000.0)
    xbrl_v2 = _xbrl(
        net_income=115_000.0, equity=600_000.0
    )  # net_income restated upward

    fetcher = _static_fetcher({DOC_URL_A1: xbrl_v1, DOC_URL_A2: xbrl_v2})
    stats = populate_line_items(session, fetcher, RUN_ID)

    assert stats.rows_inserted == 2

    rows = (
        session.query(FundamentalsLineItemVersion)
        .filter_by(isin=ISIN_A, period_end=_PERIOD_END_A)
        .order_by(FundamentalsLineItemVersion.available_date)
        .all()
    )
    assert len(rows) == 2
    assert [r.available_date for r in rows] == [_AVAIL_DATE_A1, _AVAIL_DATE_A2]
    # Original vintage is preserved untouched alongside the restatement.
    assert rows[0].net_income == pytest.approx(100_000.0)
    assert rows[1].net_income == pytest.approx(115_000.0)


# ---------------------------------------------------------------------------
# Test 4 — populate is idempotent
# ---------------------------------------------------------------------------


def test_populate_is_idempotent(session):
    """Running populate twice with the same filing must produce one row, not two.

    A crash + retry must never double-count a period (CLAUDE.md §1).  The
    unique key (isin, period_end, available_date) is the idempotency guard.
    """
    _add_filing(session, ISIN_A, _PERIOD_END_A, _AVAIL_DATE_A1, DOC_URL_A1)
    fetcher = _static_fetcher({DOC_URL_A1: _FULL_XBRL})

    populate_line_items(session, fetcher, RUN_ID)
    # Second run with resume=False bypasses the checkpoint — exercises DB-level dedup.
    stats2 = populate_line_items(session, fetcher, RUN_ID, resume=False)

    count = session.query(FundamentalsLineItemVersion).filter_by(isin=ISIN_A).count()
    assert count == 1
    assert stats2.rows_inserted == 0  # second run skipped the existing row
    assert stats2.rows_skipped_existing == 1


# ---------------------------------------------------------------------------
# Test 5 — per-filing fetcher failure → logged + run continues
# ---------------------------------------------------------------------------


def test_per_filing_failure_logged_and_run_continues(session):
    """A fetcher failure for one ISIN's document must log to PipelineError and
    let the run continue; the other ISIN's row still lands (Rule 12 / CLAUDE.md §1).

    Crashing the entire pipeline on one bad URL would make the ingest brittle —
    a single deleted or corrupted XBRL file would wipe the whole run.
    """
    _add_filing(session, ISIN_A, _PERIOD_END_A, _AVAIL_DATE_A1, DOC_URL_A1)
    _add_filing(session, ISIN_B, _PERIOD_END_B, _AVAIL_DATE_B, DOC_URL_B)

    fetcher = _error_fetcher(
        failing_url=DOC_URL_A1,
        fallback={DOC_URL_B: _FULL_XBRL},
    )
    stats = populate_line_items(session, fetcher, RUN_ID)

    assert stats.filings_failed >= 1
    assert stats.rows_inserted == 1  # ISIN_B still landed

    assert (
        session.query(FundamentalsLineItemVersion).filter_by(isin=ISIN_A).count() == 0
    )
    assert (
        session.query(FundamentalsLineItemVersion).filter_by(isin=ISIN_B).count() == 1
    )

    errors = session.query(PipelineError).filter_by(run_id=RUN_ID, phase=PHASE).all()
    assert len(errors) >= 1
    assert any("Timeout" in e.message or "timeout" in e.message.lower() for e in errors)


# ---------------------------------------------------------------------------
# Test 6 — ISIN with fetch failure is NOT checkpointed → retried on resume
# ---------------------------------------------------------------------------


def test_failed_isin_not_checkpointed_and_retried_on_resume(session):
    """An ISIN whose fetch fails must NOT be checkpointed so --resume retries it.

    This is the core invariant that prevents throttled NSE responses from being
    silently swallowed and permanently skipped.  If an ISIN were checkpointed
    despite fetch failures, a --resume would skip it forever — the §6.1 weight
    floor failure would be permanent even when the data exists on NSE.
    The fix: only checkpoint an ISIN when isin_fetch_failures == 0.
    """
    _add_filing(session, ISIN_A, _PERIOD_END_A, _AVAIL_DATE_A1, DOC_URL_A1)
    _add_filing(session, ISIN_B, _PERIOD_END_B, _AVAIL_DATE_B, DOC_URL_B)

    # First pass: ISIN_A fetch fails; ISIN_B succeeds.
    fetcher_pass1 = _error_fetcher(
        failing_url=DOC_URL_A1,
        fallback={DOC_URL_B: _FULL_XBRL},
    )
    populate_line_items(session, fetcher_pass1, RUN_ID)

    # After first pass: ISIN_B is checkpointed; ISIN_A is NOT (fetch failed).
    import json

    from app.db.models import PipelineCheckpoint

    ckpt = (
        session.query(PipelineCheckpoint).filter_by(run_id=RUN_ID, phase=PHASE).first()
    )
    assert ckpt is not None
    checkpointed = set(json.loads(ckpt.completed_symbols))
    assert ISIN_B in checkpointed, "ISIN_B (success) must be checkpointed"
    assert ISIN_A not in checkpointed, "ISIN_A (fetch failed) must NOT be checkpointed"

    # Second pass (resume=True): ISIN_A fetch now succeeds → its row lands.
    fetcher_pass2 = _static_fetcher({DOC_URL_A1: _FULL_XBRL, DOC_URL_B: _FULL_XBRL})
    stats2 = populate_line_items(session, fetcher_pass2, RUN_ID, resume=True)

    assert stats2.isins_skipped_checkpoint == 1  # ISIN_B skipped (already done)
    assert stats2.rows_inserted == 1  # ISIN_A row now lands
    assert (
        session.query(FundamentalsLineItemVersion).filter_by(isin=ISIN_A).count() == 1
    )


# ---------------------------------------------------------------------------
# Test 7 — placeholder ".../xbrl/-" URL (no XBRL doc) is skipped, never fetched
# ---------------------------------------------------------------------------


def test_placeholder_url_is_skipped_not_fetched(session):
    """A filing whose document_url is NSE's no-document placeholder ('.../xbrl/-')
    must be skipped WITHOUT a fetch attempt.

    NSE returns this placeholder when no XBRL exists for a filing (the xbrl='-' /
    format='Old' case — TB0.5). These are not transient throttles: re-fetching
    them 404s forever. If they entered the fetch loop, every --resume would burn
    the rate-limit budget re-404ing tens of thousands of dead URLs (~11s each
    with retries) and never make progress — the exact bug this guards against.
    The placeholder ISIN must not even count as work, and a fetch must never fire
    for it (asserted by an exploding fetcher).
    """
    placeholder = "https://nsearchives.nseindia.com/corporate/xbrl/-"
    _add_filing(session, ISIN_A, _PERIOD_END_A, _AVAIL_DATE_A1, placeholder)
    _add_filing(session, ISIN_B, _PERIOD_END_B, _AVAIL_DATE_B, DOC_URL_B)

    fetched_urls: list[str] = []

    def _tracking_fetcher(url: str) -> str:
        fetched_urls.append(url)
        if url == placeholder:
            raise AssertionError(f"placeholder URL must never be fetched: {url!r}")
        return _FULL_XBRL

    stats = populate_line_items(session, _tracking_fetcher, RUN_ID)

    # Placeholder filing produced no row and no fetch; only the real ISIN landed.
    assert placeholder not in fetched_urls
    assert fetched_urls == [DOC_URL_B]
    assert stats.rows_inserted == 1
    assert (
        session.query(FundamentalsLineItemVersion).filter_by(isin=ISIN_A).count() == 0
    )
    assert (
        session.query(FundamentalsLineItemVersion).filter_by(isin=ISIN_B).count() == 1
    )
