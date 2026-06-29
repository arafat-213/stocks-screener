"""F5 — Alert log tests (specs/v3/12 F5).

WHY these tests matter (Rule 9):
- Every alert kind must produce exactly one persisted row with the correct kind /
  as_of / delivered flag. This proves the paper trail is complete for the month-6
  decision audit and that the send=False test path persists (delivered=False) without
  performing any Resend I/O.
- The kind filter on /alerts must narrow results; without it an operator's stop-watch
  query would return noise from every other event type.
- The delivered flag must reflect the send argument, not be hard-coded — the existing
  test suite relies on send=False paths to avoid real emails, and those runs must still
  show up in the alert feed (just marked undelivered).

All tests are I/O-free: send_alert_email is cleared by the conftest _no_live_email
fixture (env vars stripped); we additionally assert it is not called on send=False paths.
"""

from __future__ import annotations

import datetime
from datetime import date
from unittest.mock import MagicMock, patch

from app.db.models import PaperV2Alert, PaperV2Portfolio
from app.paper_v2 import alerter, watchdog
from app.paper_v2.live_engine import PROBATION_BOOK_NAME

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_book(db, *, last_processed: date | None = None) -> PaperV2Portfolio:
    pf = PaperV2Portfolio(
        name=PROBATION_BOOK_NAME,
        starting_capital=1_000_000.0,
        cash=1_000_000.0,
        is_active=True,
        last_processed_date=last_processed,
        created_at=datetime.datetime(2026, 6, 23, tzinfo=datetime.timezone.utc),
    )
    db.add(pf)
    db.flush()
    return pf


def _make_report(
    process_date: date,
    *,
    fills_executed=None,
    queued=None,
    is_rebalance: bool = False,
    skipped: bool = False,
    snapshot=None,
):
    """Build a minimal ProcessReport stub sufficient for alerter.emit_alerts."""
    report = MagicMock()
    report.process_date = process_date
    report.fills_executed = fills_executed or []
    report.queued = queued or []
    report.is_rebalance = is_rebalance
    report.skipped = skipped
    report.snapshot = snapshot
    return report


def _alerts(db, portfolio_id: int, kind: str | None = None) -> list[PaperV2Alert]:
    q = db.query(PaperV2Alert).filter_by(portfolio_id=portfolio_id)
    if kind:
        q = q.filter_by(kind=kind)
    return q.order_by(PaperV2Alert.created_at.asc()).all()


# ---------------------------------------------------------------------------
# alerter.emit_alerts — persistence per kind
# ---------------------------------------------------------------------------


def _mock_fill(side: str = "buy") -> MagicMock:
    """Fill stub with numeric qty so _rows() format string (:,.2f) doesn't crash."""
    f = MagicMock()
    f.side = side
    f.qty = 10.0
    f.symbol = "TEST.NS"
    f.isin = "INE000000000"
    return f


def test_fill_confirm_persists_row_with_correct_fields(db):
    """fill_confirm kind is written when fills_executed is non-empty; as_of = process_date."""
    pf = _make_book(db)
    fill = _mock_fill("buy")
    report = _make_report(date(2026, 6, 24), fills_executed=[fill])

    alerter.emit_alerts(report, send=False, session=db)

    rows = _alerts(db, pf.id, kind="fill_confirm")
    assert len(rows) == 1
    assert rows[0].as_of == date(2026, 6, 24)
    assert "fill" in rows[0].body_summary.lower()
    # send=False → not delivered
    assert rows[0].delivered is False


def test_fill_confirm_delivered_true_when_send_true(db):
    """delivered=True when send=True path is taken (even without a real Resend key)."""
    _make_book(db)
    fill = _mock_fill("buy")
    report = _make_report(date(2026, 6, 24), fills_executed=[fill])

    with patch("app.paper_v2.alerter.send_alert_email"):
        alerter.emit_alerts(report, send=True, session=db)

    rows = _alerts(db, 1, kind="fill_confirm")
    assert rows[0].delivered is True


def test_rebalance_preview_persists_row(db):
    """rebalance_preview kind is written on a month-end with queued fills."""
    pf = _make_book(db)
    buy = _mock_fill("buy")
    sell = _mock_fill("sell")
    report = _make_report(
        date(2026, 7, 31),
        queued=[buy, sell],
        is_rebalance=True,
    )

    alerter.emit_alerts(report, send=False, session=db)

    rows = _alerts(db, pf.id, kind="rebalance_preview")
    assert len(rows) == 1
    assert rows[0].as_of == date(2026, 7, 31)
    assert rows[0].delivered is False


def test_stop_alert_persists_row(db):
    """stop kind is written when queued fills exist on a non-rebalance day."""
    pf = _make_book(db)
    sell = _mock_fill("sell")
    report = _make_report(date(2026, 6, 25), queued=[sell], is_rebalance=False)

    alerter.emit_alerts(report, send=False, session=db)

    rows = _alerts(db, pf.id, kind="stop")
    assert len(rows) == 1
    assert "stop" in rows[0].body_summary.lower()
    assert rows[0].delivered is False


def test_skipped_report_persists_nothing(db):
    """Skipped reports produce no alert rows (warm-start replay, non-forward days)."""
    pf = _make_book(db)
    report = _make_report(date(2026, 6, 24), skipped=True)

    alerter.emit_alerts(report, send=False, session=db)

    assert len(_alerts(db, pf.id)) == 0


def test_no_session_no_persistence(db):
    """Callers that don't pass session= get no persistence (backward-compat)."""
    pf = _make_book(db)
    fill = _mock_fill("buy")
    report = _make_report(date(2026, 6, 24), fills_executed=[fill])

    alerter.emit_alerts(report, send=False)  # no session

    # db session was not used for persistence
    assert len(_alerts(db, pf.id)) == 0


def test_send_false_does_not_call_resend(db):
    """send=False path must NOT invoke send_alert_email — the in-UI feed persists
    without external I/O so test suites don't accidentally email."""
    _make_book(db)
    fill = _mock_fill("buy")
    report = _make_report(date(2026, 6, 24), fills_executed=[fill])

    with patch("app.paper_v2.alerter.send_alert_email") as mock_send:
        alerter.emit_alerts(report, send=False, session=db)

    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# alerter.emit_failure_alert
# ---------------------------------------------------------------------------


def test_pipeline_failure_persists_row(db):
    """pipeline_failure kind persists with exc type in body_summary."""
    pf = _make_book(db)

    exc = RuntimeError("disk full")
    alerter.emit_failure_alert(
        exc, "2026-06-25", "traceback here", send=False, session=db
    )

    rows = _alerts(db, pf.id, kind="pipeline_failure")
    assert len(rows) == 1
    assert "RuntimeError" in rows[0].body_summary
    assert rows[0].as_of == date(2026, 6, 25)
    assert rows[0].delivered is False


def test_pipeline_failure_as_of_parsed_from_process_date(db):
    """as_of is the date being processed when emit_failure_alert is called."""
    pf = _make_book(db)

    alerter.emit_failure_alert(
        ValueError("bad"), "2026-07-04", "", send=False, session=db
    )

    rows = _alerts(db, pf.id, kind="pipeline_failure")
    assert rows[0].as_of == date(2026, 7, 4)


# ---------------------------------------------------------------------------
# watchdog.run_watchdog — staleness alert persistence
# ---------------------------------------------------------------------------


def test_staleness_alert_persists_when_stale(db):
    """Stale watchdog run persists a staleness row (delivered=False on send=False)."""
    # Book whose clock has been frozen for 5 weekdays ⇒ stale (threshold > 2).
    _make_book(db, last_processed=date(2026, 6, 20))  # Friday

    report = watchdog.run_watchdog(session=db, send=False, today=date(2026, 6, 27))

    assert report.is_stale
    rows = _alerts(db, 1, kind="staleness")
    assert len(rows) == 1
    assert rows[0].delivered is False
    assert "stale" in rows[0].body_summary.lower()


def test_healthy_watchdog_persists_nothing(db):
    """A healthy (non-stale) watchdog run writes no alert row."""
    _make_book(db, last_processed=date(2026, 6, 26))  # Thursday

    report = watchdog.run_watchdog(session=db, send=False, today=date(2026, 6, 27))

    assert not report.is_stale
    rows = _alerts(db, 1, kind="staleness")
    assert len(rows) == 0


def test_staleness_alert_delivered_true_when_send(db):
    """delivered=True when send=True is passed to run_watchdog."""
    _make_book(db, last_processed=date(2026, 6, 20))

    with patch("app.paper_v2.watchdog.send_alert_email"):
        watchdog.run_watchdog(session=db, send=True, today=date(2026, 6, 27))

    rows = _alerts(db, 1, kind="staleness")
    assert rows[0].delivered is True


# ---------------------------------------------------------------------------
# /alerts endpoint — kind filter
# ---------------------------------------------------------------------------


def test_alerts_endpoint_returns_all_kinds(client, db):
    """GET /v2/paper/alerts returns all alert rows newest-first."""
    pf = _make_book(db)
    db.add(
        PaperV2Alert(
            portfolio_id=pf.id,
            kind="fill_confirm",
            subject="S3 paper — fills executed 2026-06-24",
            body_summary="1 fill(s) executed.",
            delivered=False,
            as_of=date(2026, 6, 24),
            created_at=datetime.datetime(2026, 6, 24, 10, tzinfo=datetime.timezone.utc),
        )
    )
    db.add(
        PaperV2Alert(
            portfolio_id=pf.id,
            kind="staleness",
            subject="⚠ stale",
            body_summary="Replay stale.",
            delivered=False,
            as_of=None,
            created_at=datetime.datetime(2026, 6, 25, 10, tzinfo=datetime.timezone.utc),
        )
    )
    db.flush()

    resp = client.get("/api/v2/paper/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Most recent first
    assert data[0]["kind"] == "staleness"
    assert data[1]["kind"] == "fill_confirm"


def test_alerts_endpoint_kind_filter(client, db):
    """GET /v2/paper/alerts?kind=fill_confirm returns only that kind."""
    pf = _make_book(db)
    db.add(
        PaperV2Alert(
            portfolio_id=pf.id,
            kind="fill_confirm",
            subject="fills",
            body_summary="1 fill.",
            delivered=False,
        )
    )
    db.add(
        PaperV2Alert(
            portfolio_id=pf.id,
            kind="staleness",
            subject="stale",
            body_summary="stale.",
            delivered=False,
        )
    )
    db.flush()

    resp = client.get("/api/v2/paper/alerts?kind=fill_confirm")
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["kind"] == "fill_confirm" for r in data)
    assert len(data) == 1


def test_alerts_endpoint_no_book_returns_empty(client):
    """GET /v2/paper/alerts returns [] when no active book is armed."""
    resp = client.get("/api/v2/paper/alerts")
    assert resp.status_code == 200
    assert resp.json() == []
