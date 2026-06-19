"""
fundamentals.xbrl_parser — TB4: Ind-AS XBRL → standardized line items (§3.3 + §3.4
write-side).

For each ``FundamentalsFilingIndex`` row with a ``document_url``, downloads the
XBRL document, maps standard ``in-bse-fin`` namespace tags to the 8 target line
items, and writes a ``FundamentalsLineItemVersion`` row.

Restatement write-side (§3.4)
------------------------------
A re-filed period writes a **new** row keyed by its ``available_date`` — the
version key from the TB1 schema.  The original row is never overwritten.  TB5
reads back "as known on D" via the as-of reader.

Unmapped items
--------------
If a line item cannot be resolved from any standard-namespace tag, it is stored
as NULL and a single ``PipelineError`` is logged for the filing listing all
unmapped fields.  **Items are never zero-filled** (Rule 12).

EBIT derivation
---------------
Ind-AS XBRL has no standalone EBIT element.  We derive:
    EBIT = ProfitBeforeExceptionalItemsAndTax + FinanceCosts
Both components must be present; if either is absent, ebit = NULL.

Total equity derivation
-----------------------
Direct ``Equity`` element preferred; falls back to the standard component sum
``PaidUpValueOfEquityShareCapital + ReserveExcludingRevaluationReserves``.

Total debt derivation
---------------------
Direct ``Borrowings`` element preferred (used by NBFC/Banking filings); falls
back to ``BorrowingsNoncurrent + BorrowingsCurrent`` (the real balance-sheet tag
names — the legacy ``LongTermBorrowings``/``ShortTermBorrowings`` /
``NonCurrentBorrowings``/``CurrentBorrowings`` names are kept as further fallbacks
but do not appear in real Ind-AS filings).  Zero-filled per component if only one
is present.  **Results-only filings (the bulk of 2020–2023) carry no balance
sheet — total_debt is correctly NULL there, never zero-filled (Rule 12).**

Shares-outstanding derivation
-----------------------------
Ind-AS filings carry **no** ``NumberOf*SharesOutstanding`` element.  Share count
is derived from ``PaidUpValueOfEquityShareCapital / FaceValueOfEquityShareCapital``
(both near-universal, including results-only filings).  The first **positive**
paid-up value is used: a listed company cannot have ₹0 paid-up capital, so a 0 in
a duplicate context is a data artifact and is skipped (§4.3 degenerate handling).

Source seam
-----------
``XBRLFetcher = Callable[[str], str]``  — url → raw XBRL text.
Tests inject a fixture callable (CLAUDE.md §5 — no network in tests).
``fetch_xbrl_document`` is the concrete production fetcher.
"""

from __future__ import annotations

import datetime
import json
import re
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import PipelineCheckpoint, PipelineError
from app.fundamentals.models import FundamentalsFilingIndex, FundamentalsLineItemVersion
from app.pipeline.errors import classify_error

PHASE = "tb4_xbrl_parse"
# Re-parse pass (TBE2b): re-fetch + re-parse in-window filings with the corrected
# tag mappings, updating existing rows in place.  Separate checkpoint phase so it
# never collides with the original populate checkpoint.
PHASE_REPARSE = "tbe2b_reparse"

# Standard Ind-AS taxonomy namespace (mandated for NSE/BSE filings).
_STD_NS_PREFIX = "in-bse-fin"
_STD_NS_MARKER = "in-bse-fin"

_HTTP_TIMEOUT_S = 15
_REQUEST_SLEEP_S = 0.5  # base inter-request sleep (slightly conservative vs 0.3)
_MAX_RETRIES = 3  # total attempts per URL (1 initial + 2 retries)
_RETRY_BACKOFF_S = (3.0, 8.0)  # sleep before retry 2, retry 3
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
}

# ---------------------------------------------------------------------------
# Tag mappings — standard `in-bse-fin` namespace only.
# All tuples are (primary, *fallbacks); first match wins.
# ---------------------------------------------------------------------------

_REVENUE_TAGS = (
    "Revenue",
    "RevenueFromOperations",
    "RevenueFromContractsWithCustomers",
    "IncomeFromOperations",
    "GrossRevenue",
)

_NET_INCOME_TAGS = (
    "ProfitLossForPeriod",
    "ProfitLossForPeriodFromContinuingOperations",
    "ProfitLossForThePeriod",
    "ProfitLossFromOrdinaryActivitiesAfterTax",
)

# EBIT = PBT + FinanceCosts (both must be present; derived, never a direct element).
_PBT_TAGS = (
    "ProfitBeforeExceptionalItemsAndTax",
    "ProfitLossBeforeExtraordinaryItemsAndTax",
    "ProfitLossBeforeTax",
)
_FINANCE_COSTS_TAGS = (
    "FinanceCosts",
    "FinanceCharges",
    "FinancialCosts",
    "InterestAndFinanceCharges",
)

# Total equity: direct first, component sum fallback.
_TOTAL_EQUITY_DIRECT_TAGS = (
    "Equity",
    "EquityAttributableToOwnersOfParent",
)
_EQUITY_SHARE_CAPITAL_TAG = ("PaidUpValueOfEquityShareCapital",)
_EQUITY_RESERVES_TAG = ("ReserveExcludingRevaluationReserves",)

_TOTAL_ASSETS_TAGS = (
    "Assets",
    "TotalAssets",
)

# Total debt: direct first, LT+ST sum fallback.
_TOTAL_DEBT_DIRECT_TAGS = (
    "Borrowings",
    "TotalBorrowings",
)
# Real Ind-AS tag names are BorrowingsNoncurrent / BorrowingsCurrent (the
# legacy Long/Short/NonCurrent/Current names below never appear in filings but
# are retained as harmless further fallbacks).
_LT_BORROWINGS_TAGS = (
    "BorrowingsNoncurrent",
    "LongTermBorrowings",
    "NonCurrentBorrowings",
)
_ST_BORROWINGS_TAGS = (
    "BorrowingsCurrent",
    "ShortTermBorrowings",
    "CurrentBorrowings",
)

# Direct share-count tags do not exist in Ind-AS filings (kept as defensive
# primary); share count is derived from paid-up capital / face value below.
_SHARES_OUTSTANDING_TAGS = (
    "NumberOfSharesOutstanding",
    "NumberOfEquitySharesOutstanding",
    "NumberOfEquitySharesOutstandingAtEndOfReportingPeriod",
)
_PAIDUP_CAPITAL_TAGS = ("PaidUpValueOfEquityShareCapital",)
_FACE_VALUE_TAGS = ("FaceValueOfEquityShareCapital",)

_CFO_TAGS = (
    "NetCashFlowsFromUsedInOperatingActivities",
    "CashFlowsFromUsedInOperatingActivities",
    "NetCashFromOperatingActivities",
    "CashGeneratedFromOperations",
)

# All 8 items as (field_name, resolver) — used by parse_xbrl to build the result
# and populate unmapped_items. Resolvers are set after the helper functions below.
_ITEM_NAMES = (
    "revenue",
    "net_income",
    "ebit",
    "total_equity",
    "total_assets",
    "total_debt",
    "shares_outstanding",
    "cfo",
)


# ---------------------------------------------------------------------------
# XBRL parsing — pure functions, no I/O
# ---------------------------------------------------------------------------


def _std_namespace_ok(xbrl_text: str) -> bool:
    """True iff the in-bse-fin prefix maps to a URI containing the standard marker."""
    m = re.search(rf'xmlns:{_STD_NS_PREFIX}="([^"]+)"', xbrl_text[:8000])
    return bool(m and _STD_NS_MARKER in m.group(1))


def _extract_numeric(xbrl_text: str, local_names: tuple[str, ...]) -> float | None:
    """Extract the first matching numeric value from the standard namespace.

    Only matches elements under the ``in-bse-fin`` prefix.  Custom-namespace or
    absent elements return None — never a false positive (Rule 12 conservative bound).
    """
    for ln in local_names:
        pat = (
            rf"<{_STD_NS_PREFIX}:{ln}\b[^>]*>"
            rf"\s*(-?\d[\d,]*\.?\d*(?:[eE][+-]?\d+)?)\s*"
            rf"</{_STD_NS_PREFIX}:{ln}>"
        )
        m = re.search(pat, xbrl_text)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def _extract_first_positive(
    xbrl_text: str, local_names: tuple[str, ...]
) -> float | None:
    """First strictly-positive match from the standard namespace, else None.

    Used for share capital: the same fact can appear in duplicate contexts where
    one carries a 0 artifact (e.g. a standalone/consolidated split or a filing
    error).  A listed company cannot have ₹0 paid-up capital, so a 0 is skipped
    in favour of the real positive value (§4.3 degenerate handling).
    """
    for ln in local_names:
        for m in re.finditer(
            rf"<{_STD_NS_PREFIX}:{ln}\b[^>]*>"
            rf"\s*(-?\d[\d,]*\.?\d*(?:[eE][+-]?\d+)?)\s*"
            rf"</{_STD_NS_PREFIX}:{ln}>",
            xbrl_text,
        ):
            v = float(m.group(1).replace(",", ""))
            if v > 0:
                return v
    return None


def _derive_shares_outstanding(xbrl_text: str) -> float | None:
    """Direct share-count element if present; else paid-up capital / face value.

    No Ind-AS filing carries a ``NumberOf*SharesOutstanding`` element, so in
    practice the count is ``PaidUpValueOfEquityShareCapital /
    FaceValueOfEquityShareCapital`` (both near-universal, including results-only
    filings).  Either component absent or non-positive → None (never zero-filled).
    """
    direct = _extract_numeric(xbrl_text, _SHARES_OUTSTANDING_TAGS)
    if direct is not None:
        return direct
    paid_up = _extract_first_positive(xbrl_text, _PAIDUP_CAPITAL_TAGS)
    face_value = _extract_first_positive(xbrl_text, _FACE_VALUE_TAGS)
    if paid_up is not None and face_value is not None and face_value > 0:
        return paid_up / face_value
    return None


def _derive_ebit(xbrl_text: str) -> float | None:
    """EBIT = PBT + FinanceCosts.  None if either component is absent."""
    pbt = _extract_numeric(xbrl_text, _PBT_TAGS)
    fc = _extract_numeric(xbrl_text, _FINANCE_COSTS_TAGS)
    if pbt is not None and fc is not None:
        return pbt + fc
    return None


def _derive_total_equity(xbrl_text: str) -> float | None:
    """Direct Equity element; falls back to share-capital + reserves component sum."""
    eq = _extract_numeric(xbrl_text, _TOTAL_EQUITY_DIRECT_TAGS)
    if eq is not None:
        return eq
    capital = _extract_numeric(xbrl_text, _EQUITY_SHARE_CAPITAL_TAG)
    reserves = _extract_numeric(xbrl_text, _EQUITY_RESERVES_TAG)
    if capital is not None and reserves is not None:
        return capital + reserves
    return None


def _derive_total_debt(xbrl_text: str) -> float | None:
    """Direct Borrowings element; falls back to LT + ST borrowings sum.

    If only one component is present the other is treated as zero (a company with
    no short-term debt still reports a valid total_debt from LT alone).
    """
    debt = _extract_numeric(xbrl_text, _TOTAL_DEBT_DIRECT_TAGS)
    if debt is not None:
        return debt
    lt = _extract_numeric(xbrl_text, _LT_BORROWINGS_TAGS)
    st = _extract_numeric(xbrl_text, _ST_BORROWINGS_TAGS)
    if lt is not None or st is not None:
        return (lt or 0.0) + (st or 0.0)
    return None


@dataclass
class XBRLParseResult:
    """Parsed line items from one XBRL document.

    ``None`` means the item could not be resolved from any standard-namespace tag
    — NEVER zero-filled (TB4 / Rule 12).  ``unmapped_items`` lists which fields
    were not found, for surfacing in the PipelineError message.
    """

    revenue: float | None = None
    net_income: float | None = None
    ebit: float | None = None
    total_equity: float | None = None
    total_assets: float | None = None
    total_debt: float | None = None
    shares_outstanding: float | None = None
    cfo: float | None = None
    unmapped_items: list[str] = field(default_factory=list)


def parse_xbrl(xbrl_text: str) -> XBRLParseResult:
    """Parse an Ind-AS XBRL document into the 8 standardized line items.

    Returns an ``XBRLParseResult`` where any item that cannot be resolved from
    a standard ``in-bse-fin`` tag is ``None`` and listed in ``unmapped_items``.
    If the document's standard namespace is absent, all items are None (the
    document is unparseable by this mapper — treat as a full miss).
    """
    result = XBRLParseResult()

    if not _std_namespace_ok(xbrl_text):
        result.unmapped_items = list(_ITEM_NAMES)
        return result

    candidates: list[tuple[str, float | None]] = [
        ("revenue", _extract_numeric(xbrl_text, _REVENUE_TAGS)),
        ("net_income", _extract_numeric(xbrl_text, _NET_INCOME_TAGS)),
        ("ebit", _derive_ebit(xbrl_text)),
        ("total_equity", _derive_total_equity(xbrl_text)),
        ("total_assets", _extract_numeric(xbrl_text, _TOTAL_ASSETS_TAGS)),
        ("total_debt", _derive_total_debt(xbrl_text)),
        ("shares_outstanding", _derive_shares_outstanding(xbrl_text)),
        ("cfo", _extract_numeric(xbrl_text, _CFO_TAGS)),
    ]

    for name, value in candidates:
        setattr(result, name, value)
        if value is None:
            result.unmapped_items.append(name)

    return result


# ---------------------------------------------------------------------------
# Source seam
# ---------------------------------------------------------------------------

# Injectable fetcher: tests pass a fixture; production passes fetch_xbrl_document.
XBRLFetcher = Callable[[str], str]  # url → raw XBRL text


def fetch_xbrl_document(url: str) -> str:
    """Fetch an XBRL document from a URL with retry + exponential backoff.

    Retries up to ``_MAX_RETRIES`` times on any exception (connection error,
    HTTP 429/5xx throttle, timeout).  Sleep between retries grows exponentially
    per ``_RETRY_BACKOFF_S``.  Base inter-request sleep of ``_REQUEST_SLEEP_S``
    is applied after every successful fetch to stay under NSE's rate limit.
    Production only — tests inject a fixture fetcher (CLAUDE.md §5).
    """
    import requests  # local import: live-only dependency

    sess = requests.Session()
    sess.headers.update(_NSE_HEADERS)
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = sess.get(url, timeout=_HTTP_TIMEOUT_S)
            resp.raise_for_status()
            time.sleep(_REQUEST_SLEEP_S)
            return resp.text
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF_S[attempt])
    raise last_exc  # type: ignore[misc]


def make_caching_fetcher(
    cache_dir: str, inner: XBRLFetcher = fetch_xbrl_document
) -> XBRLFetcher:
    """Wrap a fetcher so each raw XBRL doc is read from / written to ``cache_dir``.

    Raw XBRL is otherwise discarded after parsing, so a tag-mapping re-ingest
    would re-fetch the whole panel from live NSE every time.  Caching keyed by
    the URL's filename (filings have globally-unique names) pays the network
    cost **once**: a cache hit short-circuits the live fetch entirely, so a
    re-parse after the first pass needs no network at all.  Cache misses delegate
    to ``inner`` (the live fetcher) and persist the result.
    """
    import os

    os.makedirs(cache_dir, exist_ok=True)

    def _fetch(url: str) -> str:
        path = os.path.join(cache_dir, url.rsplit("/", 1)[-1])
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        text = inner(url)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return text

    return _fetch


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class XBRLPopulateStats:
    """Outcome of a populate_line_items run — surfaced, not logged-and-forgotten."""

    total_filings: int = 0
    rows_inserted: int = 0
    rows_skipped_existing: int = 0
    filings_failed: int = 0
    isins_skipped_checkpoint: int = 0
    filings_with_unmapped: int = 0


@dataclass
class XBRLReparseStats:
    """Outcome of a reparse_line_items run — surfaced, not logged-and-forgotten."""

    total_filings: int = 0
    rows_updated: int = 0  # existing row re-parsed + a field changed
    rows_unchanged: int = 0  # existing row re-parsed, identical (idempotent)
    rows_inserted: int = 0  # filing had no row yet (gap fill)
    filings_failed: int = 0
    isins_skipped_checkpoint: int = 0
    filings_with_unmapped: int = 0
    shares_filled: int = 0  # rows where shares_outstanding went NULL → value
    debt_filled: int = 0  # rows where total_debt went NULL → value


# ---------------------------------------------------------------------------
# Checkpoint / error helpers (same pattern as TB2/TB3 — Rule 3)
# ---------------------------------------------------------------------------


def _get_completed_isins(session: Session, run_id: str, phase: str = PHASE) -> set[str]:
    checkpoint = (
        session.query(PipelineCheckpoint).filter_by(run_id=run_id, phase=phase).first()
    )
    if checkpoint and checkpoint.completed_symbols:
        try:
            return set(json.loads(checkpoint.completed_symbols))
        except Exception:
            return set()
    return set()


def _save_checkpoint(
    session: Session, run_id: str, completed: set[str], phase: str = PHASE
) -> None:
    checkpoint = (
        session.query(PipelineCheckpoint).filter_by(run_id=run_id, phase=phase).first()
    )
    if not checkpoint:
        checkpoint = PipelineCheckpoint(
            run_id=run_id,
            phase=phase,
            started_at=datetime.datetime.now(datetime.timezone.utc),
        )
        session.add(checkpoint)
    checkpoint.completed_symbols = json.dumps(sorted(completed))
    checkpoint.completed_at = datetime.datetime.now(datetime.timezone.utc)
    session.commit()


def _log_pipeline_error(
    session: Session, run_id: str, isin: str, exc: Exception
) -> None:
    err = PipelineError(
        run_id=run_id,
        symbol=isin,
        phase=PHASE,
        error_type=classify_error(exc),
        message=str(exc),
        traceback=traceback.format_exc(),
    )
    session.add(err)
    session.commit()


# ---------------------------------------------------------------------------
# Populate
# ---------------------------------------------------------------------------


def populate_line_items(
    session: Session,
    fetcher: XBRLFetcher,
    run_id: str,
    *,
    resume: bool = True,
) -> XBRLPopulateStats:
    """Idempotently parse XBRL documents and write FundamentalsLineItemVersion rows.

    Reads ``FundamentalsFilingIndex`` rows with a non-NULL ``document_url``,
    groups by ISIN (checkpoint granularity = one ISIN = all its filings committed),
    and writes one ``FundamentalsLineItemVersion`` row per filing.

    Restatement write-side (§3.4): two filings for the same period_end with
    different ``available_date``s each write their own row — never an overwrite.
    The TB1 unique key ``(isin, period_end, available_date)`` rejects exact
    duplicates (idempotency).

    Per-filing fetcher or parse failures log to ``PipelineError`` via
    ``classify_error`` and the run continues (CLAUDE.md §1 / Rule 12).
    Unmapped items are NULL + one ``PipelineError`` per filing listing them.
    """
    completed = _get_completed_isins(session, run_id) if resume else set()
    stats = XBRLPopulateStats()

    # Collect all ISINs with at least one filing that has a REAL document_url.
    # NSE returns a placeholder URL ending in ``/-`` when no XBRL document exists
    # for a filing (the ``xbrl="-"`` / format="Old" case — TB0.5). Those are not
    # fetchable; excluding them here keeps resume from burning the rate-limit
    # budget re-404ing tens of thousands of dead URLs (~11s each with retries).
    real_url = FundamentalsFilingIndex.document_url.isnot(None) & ~(
        FundamentalsFilingIndex.document_url.like("%/-")
    )
    isins_with_filings: list[str] = [
        row.isin
        for row in (
            session.query(FundamentalsFilingIndex.isin)
            .filter(real_url)
            .distinct()
            .order_by(FundamentalsFilingIndex.isin)
            .all()
        )
    ]

    for isin in isins_with_filings:
        if isin in completed:
            stats.isins_skipped_checkpoint += 1
            continue

        filings = (
            session.query(FundamentalsFilingIndex)
            .filter(
                FundamentalsFilingIndex.isin == isin,
                real_url,
            )
            .order_by(FundamentalsFilingIndex.available_date)
            .all()
        )

        # Track fetch failures separately from parse/write failures.
        # Only fetch failures are retryable — parse/unmapped are deterministic.
        # An ISIN is checkpointed only when fetch_failures == 0 so that
        # throttled ISINs are automatically retried on --resume (Rule 12).
        isin_fetch_failures = 0

        for filing in filings:
            stats.total_filings += 1
            doc_url = filing.document_url  # guaranteed non-None by the query filter

            # --- Idempotency: skip BEFORE fetching ---
            # On --resume an ISIN may be reprocessed because a sibling filing was
            # throttled; the filings already stored must be skipped WITHOUT a
            # network round-trip, or every resume re-fetches the whole panel and
            # re-throttles the genuine gaps (the "no progress" failure mode).
            existing = (
                session.query(FundamentalsLineItemVersion)
                .filter_by(
                    isin=isin,
                    period_end=filing.period_end,
                    available_date=filing.available_date,
                )
                .first()
            )
            if existing is not None:
                stats.rows_skipped_existing += 1
                continue

            # --- Fetch (with retry/backoff inside fetch_xbrl_document) ---
            try:
                xbrl_text = fetcher(doc_url)
            except Exception as exc:
                stats.filings_failed += 1
                isin_fetch_failures += 1
                _log_pipeline_error(session, run_id, isin, exc)
                continue

            # --- Parse ---
            try:
                parsed = parse_xbrl(xbrl_text)
            except Exception as exc:
                stats.filings_failed += 1
                _log_pipeline_error(session, run_id, isin, exc)
                continue

            # Unmapped items → NULL (already None in parsed) + log.
            if parsed.unmapped_items:
                stats.filings_with_unmapped += 1
                unmapped_exc = ValueError(
                    f"{isin} period_end={filing.period_end} avail={filing.available_date}: "
                    f"unmapped line items (stored as NULL): {', '.join(parsed.unmapped_items)}"
                )
                _log_pipeline_error(session, run_id, isin, unmapped_exc)

            # --- Write (restatement write-side: new row per available_date) ---
            # Existence already checked above (pre-fetch). The TB1 unique key
            # still guards against a concurrent duplicate; an IntegrityError here
            # rolls back and is logged, never crashing the run.
            try:
                session.add(
                    FundamentalsLineItemVersion(
                        isin=isin,
                        period_end=filing.period_end,
                        available_date=filing.available_date,
                        statement_type=filing.statement_type,
                        source_exchange=filing.source_exchange,
                        revenue=parsed.revenue,
                        net_income=parsed.net_income,
                        ebit=parsed.ebit,
                        total_equity=parsed.total_equity,
                        total_assets=parsed.total_assets,
                        total_debt=parsed.total_debt,
                        shares_outstanding=parsed.shares_outstanding,
                        cfo=parsed.cfo,
                    )
                )
                session.commit()
                stats.rows_inserted += 1

            except Exception as exc:
                session.rollback()
                stats.filings_failed += 1
                _log_pipeline_error(session, run_id, isin, exc)

        # Only checkpoint if every fetch for this ISIN succeeded.  An ISIN
        # with any throttled/failed fetch stays uncheckpointed so --resume
        # retries it automatically.  Parse failures and unmapped items are
        # deterministic (re-fetching won't change them) and do NOT block
        # checkpointing — they are already in the DB as NULL or logged.
        if isin_fetch_failures == 0:
            completed.add(isin)
            _save_checkpoint(session, run_id, completed)

    return stats


_REPARSE_FIELDS = (
    "revenue",
    "net_income",
    "ebit",
    "total_equity",
    "total_assets",
    "total_debt",
    "shares_outstanding",
    "cfo",
)


def reparse_line_items(
    session: Session,
    fetcher: XBRLFetcher,
    run_id: str,
    *,
    period_start: datetime.date,
    period_end: datetime.date,
    resume: bool = True,
) -> XBRLReparseStats:
    """Re-fetch + re-parse in-window filings with the corrected mappings, updating
    existing rows **in place** (TBE2b step 3).

    Distinct from ``populate_line_items``: that one *skips* filings whose row
    already exists, so it cannot apply a parser tag-fix to a panel already
    ingested.  This pass instead re-parses every in-window filing and overwrites
    the 8 line-item fields on the matching ``(isin, period_end, available_date)``
    row.  This is a **parse correction, not a restatement** — ``available_date``
    is unchanged and no new vintage row is created, so the §3.4 restatement
    invariant is untouched.  A filing with no row yet is inserted (gap fill).

    Update-in-place (never delete-then-repopulate) means an interruption never
    leaves the frozen panel with a missing row — only stale-or-fresh values, both
    valid.  Pair with ``make_caching_fetcher`` so the first pass pays the live-NSE
    cost once and any re-run is fully offline.  Checkpoints per ISIN under
    ``PHASE_REPARSE`` so ``resume`` continues after a throttle/crash.
    """
    completed = (
        _get_completed_isins(session, run_id, PHASE_REPARSE) if resume else set()
    )
    stats = XBRLReparseStats()

    real_url = FundamentalsFilingIndex.document_url.isnot(None) & ~(
        FundamentalsFilingIndex.document_url.like("%/-")
    )
    in_window = (
        real_url
        & (FundamentalsFilingIndex.period_end >= period_start)
        & (FundamentalsFilingIndex.period_end <= period_end)
    )

    isins: list[str] = [
        row.isin
        for row in (
            session.query(FundamentalsFilingIndex.isin)
            .filter(in_window)
            .distinct()
            .order_by(FundamentalsFilingIndex.isin)
            .all()
        )
    ]

    for isin in isins:
        if isin in completed:
            stats.isins_skipped_checkpoint += 1
            continue

        filings = (
            session.query(FundamentalsFilingIndex)
            .filter(FundamentalsFilingIndex.isin == isin, in_window)
            .order_by(FundamentalsFilingIndex.available_date)
            .all()
        )
        isin_fetch_failures = 0

        for filing in filings:
            stats.total_filings += 1
            try:
                xbrl_text = fetcher(filing.document_url)
            except Exception as exc:
                stats.filings_failed += 1
                isin_fetch_failures += 1
                _log_pipeline_error(session, run_id, isin, exc)
                continue

            try:
                parsed = parse_xbrl(xbrl_text)
            except Exception as exc:
                stats.filings_failed += 1
                _log_pipeline_error(session, run_id, isin, exc)
                continue

            if parsed.unmapped_items:
                stats.filings_with_unmapped += 1

            row = (
                session.query(FundamentalsLineItemVersion)
                .filter_by(
                    isin=isin,
                    period_end=filing.period_end,
                    available_date=filing.available_date,
                )
                .first()
            )
            try:
                if row is None:
                    session.add(
                        FundamentalsLineItemVersion(
                            isin=isin,
                            period_end=filing.period_end,
                            available_date=filing.available_date,
                            statement_type=filing.statement_type,
                            source_exchange=filing.source_exchange,
                            **{f: getattr(parsed, f) for f in _REPARSE_FIELDS},
                        )
                    )
                    session.commit()
                    stats.rows_inserted += 1
                    continue

                changed = False
                for f in _REPARSE_FIELDS:
                    new = getattr(parsed, f)
                    old = getattr(row, f)
                    if new != old:
                        if (
                            f == "shares_outstanding"
                            and old is None
                            and new is not None
                        ):
                            stats.shares_filled += 1
                        if f == "total_debt" and old is None and new is not None:
                            stats.debt_filled += 1
                        setattr(row, f, new)
                        changed = True
                if changed:
                    session.commit()
                    stats.rows_updated += 1
                else:
                    stats.rows_unchanged += 1
            except Exception as exc:
                session.rollback()
                stats.filings_failed += 1
                _log_pipeline_error(session, run_id, isin, exc)

        if isin_fetch_failures == 0:
            completed.add(isin)
            _save_checkpoint(session, run_id, completed, PHASE_REPARSE)

    return stats
