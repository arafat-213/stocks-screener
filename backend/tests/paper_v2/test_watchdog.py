"""Tests for the S3 paper-book heartbeat watchdog (app.paper_v2.watchdog).

The watchdog is an operational safety hint — it emails when the replay clock falls
stale (worker dark). These tests encode the WHY (Rule 9): a stopped worker must be
*caught* (the book has gone dark twice), but healthy steady-state trailing (the §4c
held-back edge + beat timing) must NOT false-alarm. All assertions are I/O-free —
``send_alert_email`` is patched so no Resend call is made.
"""

from __future__ import annotations

import datetime
from datetime import date
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.db.models import PaperV2Portfolio
from app.paper_v2 import watchdog
from app.paper_v2.live_engine import PROBATION_BOOK_NAME

_IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# weekday_lag — pure, deterministic (Rule 5)
# ---------------------------------------------------------------------------


def test_weekday_lag_same_or_past_day_is_zero():
    d = date(2026, 6, 22)  # Monday
    assert watchdog.weekday_lag(d, d) == 0
    assert watchdog.weekday_lag(d, date(2026, 6, 19)) == 0  # today before reference


def test_weekday_lag_skips_weekend():
    # Fri 2026-06-19 → Mon 2026-06-22: only Mon counts (Sat/Sun excluded), plus nothing
    # in between is a weekday ⇒ lag 1. This is the healthy steady-state shape: the clock
    # trailing into the weekend must not read as stale.
    assert watchdog.weekday_lag(date(2026, 6, 19), date(2026, 6, 22)) == 1


def test_weekday_lag_counts_consecutive_weekdays():
    # Mon → Thu = Tue, Wed, Thu = 3 weekdays.
    assert watchdog.weekday_lag(date(2026, 6, 22), date(2026, 6, 25)) == 3


# ---------------------------------------------------------------------------
# check_staleness — verdict logic
# ---------------------------------------------------------------------------


def _arm_book(db, *, last_processed: date | None, created: datetime.datetime):
    pf = PaperV2Portfolio(name=PROBATION_BOOK_NAME)
    pf.last_processed_date = last_processed
    pf.created_at = created
    db.add(pf)
    db.commit()
    return pf


def test_no_book_is_not_armed_not_stale(db):
    rep = watchdog.check_staleness(db, today=date(2026, 6, 25))
    assert rep.book_armed is False
    assert rep.is_stale is False


def test_healthy_clock_is_not_stale(db):
    # Clock at Fri, today Mon ⇒ weekday lag 1 (≤ threshold 2) ⇒ not stale. Guards against
    # false-alarming on the normal held-back-edge trail.
    _arm_book(
        db,
        last_processed=date(2026, 6, 19),
        created=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    rep = watchdog.check_staleness(db, today=date(2026, 6, 22))
    assert rep.book_armed is True
    assert rep.lag_trading_days == 1
    assert rep.is_stale is False


def test_at_threshold_is_not_stale_strictly_greater(db):
    # Lag exactly == threshold (2) must NOT trip (the FE uses > 2, not >=).
    _arm_book(
        db,
        last_processed=date(2026, 6, 18),  # Thu
        created=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    rep = watchdog.check_staleness(db, today=date(2026, 6, 22))  # Mon: Fri+Mon = 2
    assert rep.lag_trading_days == 2
    assert rep.is_stale is False


def test_stale_clock_trips(db):
    # Clock stuck at Mon, today the next Mon ⇒ 5 weekdays elapsed ⇒ stale (worker dark).
    _arm_book(
        db,
        last_processed=date(2026, 6, 15),
        created=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    rep = watchdog.check_staleness(db, today=date(2026, 6, 22))
    assert rep.lag_trading_days == 5
    assert rep.is_stale is True


def test_never_replayed_recent_arm_is_not_stale(db):
    # Clock None (armed, never replayed) but armed today ⇒ baseline = arming date ⇒ not
    # stale yet (the first beat run will replay it).
    armed = datetime.datetime(2026, 6, 22, 6, 0, tzinfo=datetime.timezone.utc)
    _arm_book(db, last_processed=None, created=armed)
    rep = watchdog.check_staleness(db, today=date(2026, 6, 22))
    assert rep.last_processed is None
    assert rep.is_stale is False


def test_never_replayed_old_arm_is_stale(db):
    # Armed long ago but the clock never advanced ⇒ a worker that never started is caught.
    armed = datetime.datetime(2026, 6, 1, 6, 0, tzinfo=datetime.timezone.utc)
    _arm_book(db, last_processed=None, created=armed)
    rep = watchdog.check_staleness(db, today=date(2026, 6, 22))
    assert rep.last_processed is None
    assert rep.is_stale is True


# ---------------------------------------------------------------------------
# run_watchdog — email side effect gated on staleness
# ---------------------------------------------------------------------------


def test_run_watchdog_emails_only_when_stale(db):
    _arm_book(
        db,
        last_processed=date(2026, 6, 15),
        created=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    with patch("app.paper_v2.watchdog.send_alert_email") as send:
        rep = watchdog.run_watchdog(db, today=date(2026, 6, 22))
    assert rep.is_stale is True
    assert send.call_count == 1
    subject = send.call_args.args[0]
    assert "STALE" in subject


def test_run_watchdog_silent_when_healthy(db):
    _arm_book(
        db,
        last_processed=date(2026, 6, 19),
        created=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    with patch("app.paper_v2.watchdog.send_alert_email") as send:
        rep = watchdog.run_watchdog(db, today=date(2026, 6, 22))
    assert rep.is_stale is False
    send.assert_not_called()
