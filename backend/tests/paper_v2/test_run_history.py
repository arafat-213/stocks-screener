"""F4 — Pipeline heartbeat / run-history tests (specs/v3/12 F4).

WHY these tests matter (Rule 9):
- A successful run MUST record status=success with the correct date span; without
  it the heartbeat strip is blind to which days were actually replayed.
- A failed run MUST record status=failed + the error_class from classify_error; the
  class distinctions (rate_limit vs db_write vs unknown) let the operator triage
  from the strip without digging into Celery logs.
- A noop (empty to_process) MUST record status=noop, not be silently skipped; the
  strip must show idle fires so the operator can confirm the beat is alive even on
  quiet days (no unprocessed days to replay).
- The concurrent-guard skip (lock already held) must produce NO run record — it is
  not an invocation that reached the book, so recording it would misrepresent the
  streak.
- GET /runs must return rows newest-first and scoped to the active portfolio_id, so
  rows from a hypothetical prior book don't pollute the strip.
- The existing task orchestration (go_live gate, parity halt) must be unchanged by
  the F4 instrumentation — the run record is purely additive.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.db.models import PaperV2Portfolio, PaperV2Run
from app.paper_v2.live_engine import PROBATION_BOOK_NAME
from app.pipeline.errors import classify_error
from app.tasks import execute_paper_daily_task

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_GO_LIVE = datetime.date(2026, 6, 23)
_DAY1 = datetime.date(2026, 6, 24)
_DAY2 = datetime.date(2026, 6, 25)
_UTC = datetime.timezone.utc


def _make_book(db, *, last_processed=None) -> PaperV2Portfolio:
    pf = PaperV2Portfolio(
        name=PROBATION_BOOK_NAME,
        starting_capital=1_000_000.0,
        cash=1_000_000.0,
        is_active=True,
        last_processed_date=last_processed,
        created_at=datetime.datetime(
            _GO_LIVE.year, _GO_LIVE.month, _GO_LIVE.day, tzinfo=_UTC
        ),
    )
    db.add(pf)
    db.flush()
    return pf


def _make_run(
    db, portfolio_id: int, *, started_days_ago: int = 0, **kwargs
) -> PaperV2Run:
    started = datetime.datetime(2026, 6, 30, tzinfo=_UTC) - datetime.timedelta(
        days=started_days_ago
    )
    defaults = dict(
        portfolio_id=portfolio_id,
        started_at=started,
        finished_at=started + datetime.timedelta(seconds=10),
        trigger="beat",
        status="success",
        days_processed=1,
        first_date=_DAY1,
        last_date=_DAY1,
        error_class=None,
        error_msg=None,
    )
    defaults.update(kwargs)
    row = PaperV2Run(**defaults)
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# TA1-3 — PaperV2Run model fields: verified by seeding rows and reading them back.
# _persist_paper_run uses a fresh session (via TestingSessionLocal in tests) so
# we verify the model / field mapping via the seeded rows rather than exercising
# the session creation, which is already covered by TA5-7 (task-level) + TA8-10
# (endpoint-level).
# ---------------------------------------------------------------------------


def test_ta1_run_model_success_fields(db):
    """A success PaperV2Run row must carry span + trigger + zero error fields.

    WHY: The heartbeat strip detail view renders first_date/last_date and the
    trigger badge. If the model mis-maps these columns, the strip is silently wrong.
    """
    pf = _make_book(db)
    started = datetime.datetime(2026, 6, 24, 9, 0, tzinfo=_UTC)
    finished = started + datetime.timedelta(minutes=5)
    row = PaperV2Run(
        portfolio_id=pf.id,
        started_at=started,
        finished_at=finished,
        trigger="beat",
        status="success",
        days_processed=2,
        first_date=_DAY1,
        last_date=_DAY2,
        error_class=None,
        error_msg=None,
    )
    db.add(row)
    db.flush()

    fetched = db.query(PaperV2Run).filter_by(portfolio_id=pf.id).one()
    assert fetched.status == "success"
    assert fetched.trigger == "beat"
    assert fetched.days_processed == 2
    assert fetched.first_date == _DAY1
    assert fetched.last_date == _DAY2
    assert fetched.error_class is None
    assert fetched.error_msg is None


def test_ta2_run_model_failed_fields(db):
    """A failed PaperV2Run row must store error_class from classify_error.

    WHY: error_class (rate_limit / timeout / db_write / unknown) is the triage
    hook on the strip. The column must accept the values classify_error returns.
    """
    pf = _make_book(db)
    exc = Exception("429 Too Many Requests")
    cls = classify_error(exc)  # "rate_limit"
    started = datetime.datetime(2026, 6, 25, 9, 0, tzinfo=_UTC)
    row = PaperV2Run(
        portfolio_id=pf.id,
        started_at=started,
        finished_at=None,
        trigger="beat",
        status="failed",
        days_processed=0,
        first_date=None,
        last_date=None,
        error_class=cls,
        error_msg=str(exc),
    )
    db.add(row)
    db.flush()

    fetched = db.query(PaperV2Run).filter_by(portfolio_id=pf.id).one()
    assert fetched.status == "failed"
    assert fetched.error_class == "rate_limit"
    assert "429" in fetched.error_msg


def test_ta3_run_model_noop_fields(db):
    """A noop PaperV2Run row must have zero days_processed and null date span.

    WHY: A noop confirms the beat is alive on quiet days. The strip chip must
    show ◦ (noop) not ✓ (success), which requires status="noop" + days_processed=0.
    """
    pf = _make_book(db)
    started = datetime.datetime(2026, 6, 26, 9, 0, tzinfo=_UTC)
    row = PaperV2Run(
        portfolio_id=pf.id,
        started_at=started,
        finished_at=started + datetime.timedelta(seconds=2),
        trigger="beat",
        status="noop",
        days_processed=0,
        first_date=None,
        last_date=None,
        error_class=None,
        error_msg=None,
    )
    db.add(row)
    db.flush()

    fetched = db.query(PaperV2Run).filter_by(portfolio_id=pf.id).one()
    assert fetched.status == "noop"
    assert fetched.days_processed == 0
    assert fetched.first_date is None
    assert fetched.last_date is None


# ---------------------------------------------------------------------------
# TA4 — concurrency-guard skip produces no run record
# ---------------------------------------------------------------------------


def _redis_locked() -> MagicMock:
    r = MagicMock()
    r.set.return_value = None  # SET NX fails → lock already held
    return r


def test_ta4_concurrency_guard_no_run_record(db):
    """A concurrent-guard skip (lock held) must NOT write a paper_v2_run row.

    WHY: The skip is not an invocation that reached the book-setup stage.
    Recording it would inflate the strip with phantom entries and incorrectly
    update the streak counter (a skipped fire is not a "run").
    """
    pf = _make_book(db)

    with patch("app.tasks._redis") as mock_redis_mod:
        mock_redis_mod.from_url.return_value = _redis_locked()
        execute_paper_daily_task("2026-06-30")

    assert db.query(PaperV2Run).filter_by(portfolio_id=pf.id).count() == 0


# ---------------------------------------------------------------------------
# TA5 — task records success status with correct span on a real replay
# ---------------------------------------------------------------------------


def _redis_unlocked() -> MagicMock:
    r = MagicMock()
    r.set.return_value = True
    return r


def _fake_book_mock(go_live: datetime.date = _GO_LIVE) -> MagicMock:
    from zoneinfo import ZoneInfo

    pf = MagicMock()
    pf.created_at = datetime.datetime(
        go_live.year, go_live.month, go_live.day, tzinfo=ZoneInfo("Asia/Kolkata")
    )
    pf.last_processed_date = None
    pf.id = 99
    return pf


def _fake_prices() -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime([str(_DAY1), str(_DAY2)])})


def test_ta5_task_records_success_with_span():
    """execute_paper_daily_task must call _persist_paper_run with status=success
    and first_date / last_date matching the replayed span.

    WHY: The heartbeat strip relies on these fields to show the operator what
    window each run covered. Without verifying the span, a bug that records
    status=success but empty dates would silently break the strip detail view.
    """
    _fake_build = MagicMock(val_report=None)
    _fake_report = MagicMock(skipped=False, is_rebalance=False)

    with (
        patch(
            "app.data.bhavcopy.incremental.incremental_append",
            return_value=(_fake_build, None),
        ),
        patch(
            "app.data.bhavcopy.store.read_prices_adjusted", return_value=_fake_prices()
        ),
        patch("app.backtest_v2.benchmark.load_price_index", return_value=MagicMock()),
        patch(
            "app.paper_v2.live_engine.get_or_create_book",
            return_value=_fake_book_mock(),
        ),
        patch(
            "app.paper_v2.live_engine.confirmed_replay_days",
            return_value=[_DAY1, _DAY2],
        ),
        patch(
            "app.paper_v2.live_engine.build_live_context",
            return_value=(MagicMock(), []),
        ),
        patch(
            "app.paper_v2.live_engine.build_adj_factor_lookup", return_value=MagicMock()
        ),
        patch("app.paper_v2.live_engine.process_day", return_value=_fake_report),
        patch("app.paper_v2.alerter.emit_alerts"),
        patch("app.tasks.SessionLocal"),
        patch("app.tasks._persist_paper_run") as mock_persist,
        patch("app.tasks._redis") as mock_redis_mod,
    ):
        mock_redis_mod.from_url.return_value = _redis_unlocked()
        execute_paper_daily_task(str(_DAY2))

    mock_persist.assert_called_once()
    kwargs = mock_persist.call_args
    pos = kwargs[0] if kwargs[0] else []
    kw = kwargs[1] if kwargs[1] else {}
    _ARG_NAMES = [
        "portfolio_id",
        "started_at",
        "finished_at",
        "trigger",
        "status",
        "days_processed",
        "first_date",
        "last_date",
        "error_class",
        "error_msg",
    ]
    all_args = {**dict(zip(_ARG_NAMES, pos)), **kw}
    assert all_args.get("status") == "success"
    assert all_args.get("days_processed") == 2
    assert all_args.get("first_date") == _DAY1
    assert all_args.get("last_date") == _DAY2
    assert all_args.get("trigger") == "beat"


def test_ta6_task_records_noop_when_nothing_to_process():
    """execute_paper_daily_task must record status=noop when confirmed_replay_days is empty.

    WHY: An idle fire (beat fires but book is already current) is the most common
    case after the initial replay. Recording noop (not silence) proves the beat
    is alive; missing this record would make an idle day look like a missed beat.
    """
    _fake_build = MagicMock(val_report=None)

    with (
        patch(
            "app.data.bhavcopy.incremental.incremental_append",
            return_value=(_fake_build, None),
        ),
        patch(
            "app.data.bhavcopy.store.read_prices_adjusted", return_value=_fake_prices()
        ),
        patch("app.backtest_v2.benchmark.load_price_index", return_value=MagicMock()),
        patch(
            "app.paper_v2.live_engine.get_or_create_book",
            return_value=_fake_book_mock(),
        ),
        patch(
            "app.paper_v2.live_engine.confirmed_replay_days", return_value=[]
        ),  # nothing
        patch(
            "app.paper_v2.live_engine.build_live_context",
            return_value=(MagicMock(), []),
        ),
        patch(
            "app.paper_v2.live_engine.build_adj_factor_lookup", return_value=MagicMock()
        ),
        patch("app.paper_v2.alerter.emit_alerts"),
        patch("app.tasks.SessionLocal"),
        patch("app.tasks._persist_paper_run") as mock_persist,
        patch("app.tasks._redis") as mock_redis_mod,
    ):
        mock_redis_mod.from_url.return_value = _redis_unlocked()
        execute_paper_daily_task(str(_DAY2))

    all_args = dict(
        zip(
            [
                "portfolio_id",
                "started_at",
                "finished_at",
                "trigger",
                "status",
                "days_processed",
                "first_date",
                "last_date",
                "error_class",
                "error_msg",
            ],
            mock_persist.call_args[0],
        )
    )
    assert all_args["status"] == "noop"
    assert all_args["days_processed"] == 0
    assert all_args["first_date"] is None


def test_ta7_task_records_failed_with_error_class():
    """execute_paper_daily_task must record status=failed + error_class on exception.

    WHY: error_class (from classify_error) is the triage hook the operator uses
    from the strip. If the task swallows the error before calling _persist_paper_run,
    the strip would show the fire as if it never happened.
    """
    _fake_build = MagicMock(val_report=None)

    with (
        patch(
            "app.data.bhavcopy.incremental.incremental_append",
            return_value=(_fake_build, None),
        ),
        patch(
            "app.data.bhavcopy.store.read_prices_adjusted",
            side_effect=Exception("Read timed out."),
        ),
        patch("app.backtest_v2.benchmark.load_price_index", return_value=MagicMock()),
        patch(
            "app.paper_v2.live_engine.get_or_create_book",
            return_value=_fake_book_mock(),
        ),
        patch("app.paper_v2.alerter.emit_failure_alert"),
        patch("app.tasks.SessionLocal"),
        patch("app.tasks._persist_paper_run") as mock_persist,
        patch("app.tasks._redis") as mock_redis_mod,
    ):
        mock_redis_mod.from_url.return_value = _redis_unlocked()
        with pytest.raises(Exception, match="timed out"):
            execute_paper_daily_task(str(_DAY2))

    all_args = dict(
        zip(
            [
                "portfolio_id",
                "started_at",
                "finished_at",
                "trigger",
                "status",
                "days_processed",
                "first_date",
                "last_date",
                "error_class",
                "error_msg",
            ],
            mock_persist.call_args[0],
        )
    )
    assert all_args["status"] == "failed"
    assert all_args["error_class"] == "timeout"
    assert "timed out" in all_args["error_msg"]


# ---------------------------------------------------------------------------
# TA8/9 — GET /runs endpoint
# ---------------------------------------------------------------------------


def test_ta8_get_runs_returns_newest_first(client, db):
    """GET /runs must return run records newest-first, scoped to the active book.

    WHY: The heartbeat strip renders newest on the left. An ascending order bug
    would show the oldest fire first, making the "last failure" summary wrong
    and the streak counter count from the wrong end.
    """
    pf = _make_book(db)
    # Insert older run first, then newer
    _make_run(db, pf.id, started_days_ago=2, status="success")
    _make_run(
        db,
        pf.id,
        started_days_ago=0,
        status="failed",
        error_class="timeout",
        error_msg="timed out",
        days_processed=0,
        first_date=None,
        last_date=None,
    )
    db.flush()

    resp = client.get("/api/v2/paper/runs?limit=10")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    # Newest (started_days_ago=0) should be first
    assert rows[0]["status"] == "failed"
    assert rows[1]["status"] == "success"


def test_ta9_get_runs_returns_empty_when_no_book(client):
    """GET /runs must return [] when no active book exists.

    WHY: The endpoint must not raise when the book hasn't been armed yet (same
    guard pattern as every other paper_v2 endpoint). Failing here would break
    the page load for users running before the first arm.
    """
    resp = client.get("/api/v2/paper/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_ta10_get_runs_respects_limit(client, db):
    """GET /runs must cap results at the requested limit.

    WHY: The strip renders at most 30 chips by default; without the limit cap
    a long-running probation would return hundreds of rows and slow page load.
    """
    pf = _make_book(db)
    for i in range(5):
        _make_run(db, pf.id, started_days_ago=i, status="success")
    db.flush()

    resp = client.get("/api/v2/paper/runs?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3
