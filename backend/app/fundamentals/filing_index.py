"""
fundamentals.filing_index — TB3: populate the FundamentalsFilingIndex (PIT clock).

For each ISIN in the universe master, fetches the NSE financial-results filing list
and stores one row per (isin, period_end, available_date, statement_type) in
``FundamentalsFilingIndex`` — the look-ahead guard the rest of the layer hangs on
(§3.2, problem §1.1).

The critical design invariant
------------------------------
``available_date`` is the **public dissemination timestamp** (``broadCastDate`` from
the NSE API), never the period_end.  A quarterly result for the period ending 31-Mar
is typically filed 4–8 weeks later; using the period_end as the availability date
would bake look-ahead bias into every downstream factor (§1.1).  The hard check here
is: ``available_date > period_end`` for every stored row — any violation is logged
to ``PipelineError`` and **never** stored, even if the API returns bad data.

NSE API notes (from the TB0.5 diagnostic, 2026-06-17)
------------------------------------------------------
Endpoint: ``/api/corporates-financial-results?index=equities&symbol=<S>&period=<P>``
Key response fields per row:
  - ``toDate``       — period end ("31-Mar-2024")
  - ``broadCastDate``— public dissemination ts ("22-Apr-2024 19:47:12") → available_date
  - ``filingDate``   — minutes-precision fallback ("22-Apr-2024 19:47")
  - ``xbrl``         — XBRL document URL or "-" (no document)
  - ``period``       — "Annual" / "Half-Yearly" / "Quarterly"
  - ``consolidated`` — "Consolidated" / "Non-Consolidated"
  - ``isin``         — the company ISIN (present in every row)

Deduplication: both Consolidated and Non-Consolidated filings share the same calendar
available_date, making the unique key ``(isin, period_end, available_date,
statement_type)`` reject the second.  Within each (period_end, statement_type) group,
Consolidated is preferred; Non-Consolidated is kept only when no Consolidated exists.

Source seam
-----------
``FilingSource = Callable[[str, str], Iterable[FilingRecord]]`` (isin, symbol).
Tests inject a fixture source (CLAUDE.md §5 — never hit live NSE in tests).
``fetch_nse_filing_index`` is the concrete production implementation.
"""

from __future__ import annotations

import datetime
import json
import time
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import PipelineCheckpoint, PipelineError
from app.fundamentals.models import FundamentalsFilingIndex
from app.pipeline.errors import classify_error

PHASE = "tb3_filing_index"

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
_FIN_RESULTS_URL = (
    "https://www.nseindia.com/api/corporates-financial-results"
    "?index=equities&symbol={symbol}&period={period}"
)
_PERIODS = ("Annual", "Half-Yearly", "Quarterly")
_HTTP_TIMEOUT_S = 15
_REQUEST_SLEEP_S = 0.5
_SOURCE_EXCHANGE = "NSE"


class PITViolationError(ValueError):
    """Raised when available_date <= period_end — the PIT contract violation (§3.2).

    A filing cannot pre-date the period it reports; storing such a row would
    introduce look-ahead bias.  Violations are logged to PipelineError and the
    row is skipped — never stored, never silent.
    """


@dataclass(frozen=True)
class FilingRecord:
    """One filing-index record — the populate input unit.

    ``available_date`` must be strictly after ``period_end``; the populate
    function enforces this invariant before any insert.
    """

    isin: str
    period_end: datetime.date
    available_date: datetime.date
    statement_type: str | None = None  # "Annual" / "Half-Yearly" / "Quarterly"
    source_exchange: str | None = None  # §8.1 EXCHANGE_PRIORITY — "NSE" / "BSE"
    document_url: str | None = None  # XBRL URL; None if not available


# An injectable source of filing records.  Tests pass a fixture; production passes
# ``fetch_nse_filing_index`` (or a BSE equivalent if built later).
FilingSource = Callable[[str, str], Iterable[FilingRecord]]  # (isin, symbol) -> records


@dataclass
class FilingPopulateStats:
    """Outcome of a populate run — surfaced, not logged-and-forgotten."""

    total_isins: int = 0
    rows_inserted: int = 0
    rows_failed: int = 0
    isins_failed: int = 0
    isins_skipped_checkpoint: int = 0
    pit_violations: int = 0


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def _parse_broadcast_date(s: str | None) -> datetime.date | None:
    """Parse NSE broadCastDate / filingDate to a Python date; None on failure."""
    if not s:
        return None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_period_end(s: str | None) -> datetime.date | None:
    """Parse NSE toDate string ("31-Mar-2024") to a Python date; None on failure."""
    if not s:
        return None
    try:
        return datetime.datetime.strptime(s.strip(), "%d-%b-%Y").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Concrete NSE fetcher
# ---------------------------------------------------------------------------


def fetch_nse_filing_index(isin: str, symbol: str) -> list[FilingRecord]:
    """Fetch the filing index for one ISIN from NSE's financial-results API.

    Pools Annual, Half-Yearly, and Quarterly feeds.  Within each
    (period_end, statement_type) group, Consolidated is preferred over
    Non-Consolidated — one ``FilingRecord`` per unique (period_end, statement_type).

    ``available_date`` = ``broadCastDate`` (the public dissemination timestamp,
    never period_end).  Rows with an unparseable or absent broadcast date are
    silently dropped (can't key the PIT clock without a reliable date).
    """
    import requests  # local import: live-only dependency

    sess = requests.Session()
    sess.headers.update(_NSE_HEADERS)
    try:
        # NSE requires a home-page hit to set session cookies before API calls.
        sess.get("https://www.nseindia.com", timeout=_HTTP_TIMEOUT_S)
    except requests.RequestException:
        pass
    time.sleep(_REQUEST_SLEEP_S)

    raw: list[dict] = []
    for period in _PERIODS:
        try:
            url = _FIN_RESULTS_URL.format(symbol=symbol, period=period)
            resp = sess.get(url, timeout=_HTTP_TIMEOUT_S)
            data = resp.json()
            if isinstance(data, list):
                raw.extend(data)
        except (requests.RequestException, ValueError):
            pass
        time.sleep(_REQUEST_SLEEP_S)

    # Deduplicate: group by (period_end, statement_type); keep Consolidated.
    # Key → {"period_end", "avail_date", "stmt_type", "document_url", "is_consolidated"}
    best: dict[tuple[datetime.date, str], dict] = {}
    for row in raw:
        period_end = _parse_period_end(row.get("toDate"))
        avail_date = _parse_broadcast_date(
            row.get("broadCastDate") or row.get("filingDate")
        )
        stmt_type = row.get("period")
        if not period_end or not avail_date or not stmt_type:
            continue
        xbrl = (row.get("xbrl") or "").strip()
        doc_url = xbrl if (xbrl and xbrl != "-") else None
        is_consolidated = row.get("consolidated", "").strip() == "Consolidated"
        key = (period_end, stmt_type)
        existing = best.get(key)
        if existing is None or (is_consolidated and not existing["is_consolidated"]):
            best[key] = {
                "period_end": period_end,
                "avail_date": avail_date,
                "stmt_type": stmt_type,
                "document_url": doc_url,
                "is_consolidated": is_consolidated,
            }

    return [
        FilingRecord(
            isin=isin,
            period_end=v["period_end"],
            available_date=v["avail_date"],
            statement_type=v["stmt_type"],
            source_exchange=_SOURCE_EXCHANGE,
            document_url=v["document_url"],
        )
        for v in best.values()
    ]


# ---------------------------------------------------------------------------
# Checkpoint / error helpers (same pattern as TB2 — Rule 3)
# ---------------------------------------------------------------------------


def _get_completed_isins(session: Session, run_id: str) -> set[str]:
    checkpoint = (
        session.query(PipelineCheckpoint).filter_by(run_id=run_id, phase=PHASE).first()
    )
    if checkpoint and checkpoint.completed_symbols:
        try:
            return set(json.loads(checkpoint.completed_symbols))
        except Exception:
            return set()
    return set()


def _save_checkpoint(session: Session, run_id: str, completed: set[str]) -> None:
    checkpoint = (
        session.query(PipelineCheckpoint).filter_by(run_id=run_id, phase=PHASE).first()
    )
    if not checkpoint:
        checkpoint = PipelineCheckpoint(
            run_id=run_id,
            phase=PHASE,
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


def populate_filing_index(
    session: Session,
    source: FilingSource,
    symbol_map: dict[str, str],
    run_id: str,
    *,
    resume: bool = True,
) -> FilingPopulateStats:
    """Idempotently populate ``FundamentalsFilingIndex`` from a filing source.

    Iterates over ``symbol_map`` (isin → symbol).  For each ISIN:

    - Calls ``source(isin, symbol)`` to get ``FilingRecord`` list.
    - Enforces ``available_date > period_end`` (PIT contract §3.2); violations
      log to ``PipelineError`` as ``PITViolationError`` and are never stored.
    - Upserts via the unique key ``(isin, period_end, available_date,
      statement_type)`` — re-running is idempotent (CLAUDE.md §1).
    - Checkpoints per-ISIN for crash recovery (CLAUDE.md §1).
    - Source-level failures log to ``PipelineError`` and the run continues;
      the ISIN is not checkpointed so it will be retried on resume.

    ``symbol_map`` is injected by the orchestrator, which resolves symbols from
    ``FundamentalsSymbolHistory`` or the v2 price layer's ISIN→symbol map.
    ``run_id`` must reference an existing ``PipelineRun``.
    """
    completed = _get_completed_isins(session, run_id) if resume else set()
    stats = FilingPopulateStats()

    for isin, symbol in sorted(symbol_map.items()):
        stats.total_isins += 1
        if isin in completed:
            stats.isins_skipped_checkpoint += 1
            continue

        try:
            records = list(source(isin, symbol))
        except Exception as exc:
            stats.isins_failed += 1
            _log_pipeline_error(session, run_id, isin, exc)
            continue

        for rec in records:
            # Hard PIT invariant: the filing date must post-date the period it
            # reports.  A violation means the source data is wrong; storing it
            # would silently propagate look-ahead bias into every factor (§3.2).
            if rec.available_date <= rec.period_end:
                pit_exc = PITViolationError(
                    f"{isin}: available_date={rec.available_date} is not after "
                    f"period_end={rec.period_end} — PIT contract violated (§3.2). "
                    f"Row skipped; never stored."
                )
                _log_pipeline_error(session, run_id, isin, pit_exc)
                stats.pit_violations += 1
                continue

            try:
                existing = (
                    session.query(FundamentalsFilingIndex)
                    .filter_by(
                        isin=isin,
                        period_end=rec.period_end,
                        available_date=rec.available_date,
                        statement_type=rec.statement_type,
                    )
                    .first()
                )
                if existing is None:
                    session.add(
                        FundamentalsFilingIndex(
                            isin=isin,
                            period_end=rec.period_end,
                            available_date=rec.available_date,
                            statement_type=rec.statement_type,
                            source_exchange=rec.source_exchange,
                            document_url=rec.document_url,
                        )
                    )
                    session.commit()
                    stats.rows_inserted += 1
            except Exception as exc:
                session.rollback()
                stats.rows_failed += 1
                _log_pipeline_error(session, run_id, isin, exc)

        completed.add(isin)
        _save_checkpoint(session, run_id, completed)

    return stats
