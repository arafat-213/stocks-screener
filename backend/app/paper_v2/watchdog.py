"""Worker-heartbeat watchdog for the S3 paper book (operational safety, NOT a control signal).

The forward probation (11 §7.2) deliberately tolerates missed days — an ordered EOD
replay is *fidelity-neutral*, so a gap that is backfilled before the next month-end costs
nothing. But that affordance only holds if someone NOTICES the worker/beat has stopped:
the book has already gone dark twice (worker + beat STOPPED — see the P11.2 session logs).
The FE ``StalenessBanner`` surfaces this passively (you have to be looking at the page);
nothing actively pages the operator.

This watchdog is the active half: a daily check that emails when the replay clock
(``PaperV2Portfolio.last_processed_date``) lags the latest expected trading day. It is a
*hint to go check the worker*, never a trading decision and never a knob move (11 §1). It
reads persisted state only — no live NSE/yfinance fetch (project law).

**Holiday-blindness (inherited, acknowledged).** The repo has no NSE holiday calendar (the
bhavcopy pipeline only skips weekends and tolerates holiday gaps), so "trading days" here
is a weekday (Mon–Fri) proxy — the exact choice the FE ``StalenessBanner`` already made
(holiday-blind, can over-count by an intervening holiday; acceptable for a "check the
worker" hint, not an exact figure). The threshold matches the viz: lag **> 2 trading days**.

**Why a wall-clock proxy and not the bhavcopy store edge?** The *same* daily task that
processes days also appends the store (``incremental_append``). If that task is dead the
store ALSO freezes, so a store-edge-vs-clock comparison would read ~0 lag while nothing
runs — blind to the precise failure this guards against. The weekday count is independent
of the dead task; it is the only signal that survives a stopped worker.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.alerts.email import send_alert_email
from app.db.models import PaperV2Portfolio
from app.db.session import SessionLocal
from app.paper_v2.live_engine import PROBATION_BOOK_NAME

log = logging.getLogger(__name__)

# Matches the FE StalenessBanner LOCKED threshold (11_PAPER_BOOK_VIZ_TASKS V11.6 #4):
# in healthy steady state the clock trails ~1–2 weekdays (the held-back trailing edge,
# §4c, plus beat timing), so a lag of 3+ means the worker missed a full extra day.
WATCHDOG_LAG_THRESHOLD_TD = 2

_IST = ZoneInfo("Asia/Kolkata")


@dataclass
class StalenessReport:
    """The watchdog's verdict for one check (pure data; the email is a side effect)."""

    book_armed: bool
    is_stale: bool
    lag_trading_days: int
    last_processed: date | None
    reference: date  # the baseline lag is measured from (clock, or arming date if None)
    today: date
    threshold: int


def weekday_lag(reference: date, today: date) -> int:
    """Count weekdays (Mon–Fri) strictly after ``reference`` and on/before ``today``.

    Deterministic (Rule 5) — the holiday-blind trading-day proxy described in the module
    docstring. Returns 0 when ``today <= reference``.
    """
    if today <= reference:
        return 0
    n = 0
    d = reference + datetime.timedelta(days=1)
    while d <= today:
        if d.weekday() < 5:  # 0=Mon … 4=Fri
            n += 1
        d += datetime.timedelta(days=1)
    return n


def _ist_today() -> date:
    return datetime.datetime.now(datetime.timezone.utc).astimezone(_IST).date()


def check_staleness(session: Session, today: date | None = None) -> StalenessReport:
    """Compute the staleness verdict for the probation book without side effects.

    Reads the book by name (never creates one — that is the daily task's job, not the
    watchdog's). If the book is not armed there is nothing to watch ⇒ not stale. When the
    clock is still ``None`` (armed but never replayed), lag is measured from the arming
    date so a worker that never started is still caught.
    """
    today = today or _ist_today()
    pf = (
        session.query(PaperV2Portfolio)
        .filter(PaperV2Portfolio.name == PROBATION_BOOK_NAME)
        .one_or_none()
    )
    if pf is None:
        return StalenessReport(
            book_armed=False,
            is_stale=False,
            lag_trading_days=0,
            last_processed=None,
            reference=today,
            today=today,
            threshold=WATCHDOG_LAG_THRESHOLD_TD,
        )

    # Clock None ⇒ never replayed; baseline = the arming (created_at) IST date so a
    # worker that never ran is still flagged once it lags past the threshold.
    reference = pf.last_processed_date or pf.created_at.astimezone(_IST).date()
    lag = weekday_lag(reference, today)
    return StalenessReport(
        book_armed=True,
        is_stale=lag > WATCHDOG_LAG_THRESHOLD_TD,
        lag_trading_days=lag,
        last_processed=pf.last_processed_date,
        reference=reference,
        today=today,
        threshold=WATCHDOG_LAG_THRESHOLD_TD,
    )


def build_watchdog_html(report: StalenessReport) -> str:
    last = (
        report.last_processed.isoformat()
        if report.last_processed
        else "never (book armed but not yet replayed)"
    )
    return (
        '<div><h2 style="font-family:sans-serif;color:#c0392b">'
        "⚠ S3 paper book — replay STALE</h2>"
        "<p style='font-family:sans-serif'>The daily post-close worker/beat appears to "
        "have stopped: the replay clock has not advanced for "
        f"<b>{report.lag_trading_days} trading day(s)</b> "
        f"(threshold &gt; {report.threshold}).</p>"
        "<table style='border-collapse:collapse;font-family:sans-serif;font-size:13px'>"
        f"<tr><td style='padding:4px 8px'>Last processed</td>"
        f"<td style='padding:4px 8px'><b>{last}</b></td></tr>"
        f"<tr><td style='padding:4px 8px'>Today (IST)</td>"
        f"<td style='padding:4px 8px'>{report.today.isoformat()}</td></tr>"
        f"<tr><td style='padding:4px 8px'>Lag (weekday proxy, holiday-blind)</td>"
        f"<td style='padding:4px 8px'>{report.lag_trading_days} trading day(s)</td></tr>"
        "</table>"
        "<p style='font-family:sans-serif;color:#888'>Action: check the Celery worker + "
        "beat are running, then let the daily task backfill the gap in order (11 §7.2 — "
        "missed days are fidelity-neutral once replayed before the next month-end). This "
        "is an operational hint, not a trading signal.</p></div>"
    )


def _persist_staleness_alert(
    db: Session, report: StalenessReport, subject: str, delivered: bool, commit: bool
) -> None:
    """Write a staleness alert row to ``paper_v2_alert`` (F5).

    ``commit`` is True when ``run_watchdog`` owns the session (Celery entry);
    False when the caller owns it and manages commits.
    """
    from app.db.models import PaperV2Alert, PaperV2Portfolio

    pf = db.query(PaperV2Portfolio).filter_by(name=PROBATION_BOOK_NAME).one_or_none()
    if pf is None:
        return
    row = PaperV2Alert(
        portfolio_id=pf.id,
        kind="staleness",
        subject=subject,
        body_summary=(
            f"Replay clock stale — {report.lag_trading_days} trading day(s) behind "
            f"(threshold > {report.threshold}). Last processed: {report.last_processed}."
        ),
        delivered=delivered,
        as_of=report.last_processed,
    )
    db.add(row)
    if commit:
        db.commit()
    else:
        db.flush()


def run_watchdog(
    session: Session | None = None, *, send: bool = True, today: date | None = None
) -> StalenessReport:
    """Check staleness and email an alert when stale. Returns the report either way.

    Owns its own session when called with ``session=None`` (the Celery entry point). The
    email is suppressed with ``send=False`` so tests can assert the verdict without
    external I/O (Rule 5).

    F5: stale alerts are persisted to ``paper_v2_alert`` on both send paths.
    """
    own = session is None
    db = session or SessionLocal()
    try:
        report = check_staleness(db, today=today)

        if report.is_stale:
            log.warning(
                "S3 paper watchdog: replay STALE — last_processed=%s lag=%d td (> %d)",
                report.last_processed,
                report.lag_trading_days,
                report.threshold,
            )
            subject = (
                f"⚠ S3 paper book replay STALE — "
                f"{report.lag_trading_days} trading days behind"
            )
            if send:
                send_alert_email(subject, build_watchdog_html(report))
            _persist_staleness_alert(db, report, subject, delivered=send, commit=own)
        else:
            log.info(
                "S3 paper watchdog: OK (book_armed=%s lag=%d td)",
                report.book_armed,
                report.lag_trading_days,
            )
    finally:
        if own:
            db.close()

    return report
