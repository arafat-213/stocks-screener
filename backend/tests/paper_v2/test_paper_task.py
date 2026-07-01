"""TC suite for execute_paper_daily_task's own gating logic.

The DC suite (test_live_engine.py) covers process_day and confirmed_replay_days in
isolation. These tests target the orchestration layer in tasks.py that no existing
test exercises:

  TC1  go_live gate       — a rebalance day BEFORE go_live must NOT invoke parity
                            (shadow_parity suppressed during warm-start replay)
  TC2  parity HALT        — shadow_parity(passed=False) must raise RuntimeError
                            (the 6-month clock resets per prereg §7.1)
  TC3  concurrency guard  — a second invocation while locked must return without
                            processing any days (CLAUDE.md Pipeline Law §1 / 11 §4)

All tests mock every external I/O; the only code under test is the task's own
gating logic (go_live date comparison, parity halt branch, lock check).
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from app.tasks import _PAPER_LOCK_KEY, _PAPER_LOCK_TTL, execute_paper_daily_task

# ---------------------------------------------------------------------------
# Fixed dates
# ---------------------------------------------------------------------------

_GO_LIVE = datetime.date(2026, 6, 22)
_WARMUP_DAY = datetime.date(2026, 1, 31)  # rebalance day BEFORE go_live
_LIVE_DAY = datetime.date(2026, 6, 30)  # rebalance day ON/AFTER go_live


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_book(go_live: datetime.date = _GO_LIVE) -> MagicMock:
    """PaperV2Portfolio whose created_at resolves to ``go_live`` in IST."""
    from zoneinfo import ZoneInfo

    pf = MagicMock()
    pf.created_at = datetime.datetime(
        go_live.year, go_live.month, go_live.day, tzinfo=ZoneInfo("Asia/Kolkata")
    )
    pf.last_processed_date = None
    pf.id = 1
    return pf


def _fake_prices() -> pd.DataFrame:
    """Minimal prices frame: the task only uses prices["date"] for inception and
    passes the frame into mocked engine calls."""
    return pd.DataFrame({"date": pd.to_datetime(["2026-01-02", "2026-01-03"])})


def _fake_report(*, is_rebalance: bool = False) -> MagicMock:
    rep = MagicMock()
    rep.skipped = False
    rep.is_rebalance = is_rebalance
    return rep


def _fake_parity(passed: bool) -> MagicMock:
    p = MagicMock()
    p.passed = passed
    p.summary = "ok" if passed else "BREAK: equity diverged"
    return p


def _redis_unlocked() -> MagicMock:
    """Redis client mock where SET NX succeeds (lock not held)."""
    r = MagicMock()
    r.set.return_value = True
    return r


def _redis_locked() -> MagicMock:
    """Redis client mock where SET NX fails (lock already held)."""
    r = MagicMock()
    r.set.return_value = None
    return r


# ---------------------------------------------------------------------------
# Common patch stack (all external I/O; shared by TC1 and TC2)
# ---------------------------------------------------------------------------

_EXTERNAL = [
    "app.data.bhavcopy.incremental.incremental_append",
    "app.data.bhavcopy.store.read_prices_adjusted",
    "app.backtest_v2.benchmark.load_price_index",
    "app.paper_v2.live_engine.get_or_create_book",
    "app.paper_v2.live_engine.confirmed_replay_days",
    "app.paper_v2.live_engine.build_live_context",
    "app.paper_v2.live_engine.process_day",
    "app.paper_v2.alerter.emit_alerts",
    "app.paper_v2.parity.shadow_parity",
    "app.tasks.SessionLocal",
]


# ---------------------------------------------------------------------------
# TC1 — go_live gate suppresses parity during warm-start replay
# ---------------------------------------------------------------------------


def test_tc1_parity_not_called_before_go_live():
    """A rebalance day that falls BEFORE go_live must never invoke shadow_parity.

    WHY: The warm-start replay (~115 days from inception to today) replays S3
    on historical days the live book has never actually traded. Running parity
    on those days would either fire 115 spurious parity checks (slow, noisy)
    or falsely halt the task. The go_live gate exists precisely to suppress
    both alerts and parity until the counted forward window begins.
    """
    _fake_build = MagicMock(val_report=None)
    with (
        patch(
            "app.data.bhavcopy.incremental.incremental_append",
            return_value=(_fake_build, None),
        ),
        patch(
            "app.data.bhavcopy.store.read_prices_adjusted",
            return_value=_fake_prices(),
        ),
        patch("app.backtest_v2.benchmark.load_price_index", return_value=MagicMock()),
        patch(
            "app.paper_v2.live_engine.get_or_create_book",
            return_value=_fake_book(),
        ),
        patch(
            "app.paper_v2.live_engine.confirmed_replay_days",
            return_value=[_WARMUP_DAY],  # BEFORE go_live
        ),
        patch(
            "app.paper_v2.live_engine.build_live_context",
            return_value=(MagicMock(), []),
        ),
        patch(
            "app.paper_v2.live_engine.process_day",
            return_value=_fake_report(is_rebalance=True),  # rebalance, but pre-go_live
        ),
        patch("app.paper_v2.alerter.emit_alerts"),
        patch("app.paper_v2.parity.shadow_parity") as mock_parity,
        patch("app.tasks.SessionLocal"),
        patch("app.tasks._redis") as mock_redis_mod,
    ):
        mock_redis_mod.from_url.return_value = _redis_unlocked()
        execute_paper_daily_task("2026-01-31")

    mock_parity.assert_not_called()


# ---------------------------------------------------------------------------
# TC2 — parity HALT raises RuntimeError on failed parity
# ---------------------------------------------------------------------------


def test_tc2_parity_halt_raises_on_failed_parity():
    """A failed shadow_parity on a post-go_live rebalance day must raise RuntimeError.

    WHY: The parity HALT is the operational fidelity gate for the 6-month probation
    (prereg §7.1/§8). If a parity break silently passes, the live book has diverged
    from S3 but the probation clock keeps running — invalidating the entire forward
    test. The task MUST raise so the Celery worker marks the run failed and the
    operator is alerted.
    """
    _fake_build2 = MagicMock(val_report=None)
    with (
        patch(
            "app.data.bhavcopy.incremental.incremental_append",
            return_value=(_fake_build2, None),
        ),
        patch(
            "app.data.bhavcopy.store.read_prices_adjusted",
            return_value=_fake_prices(),
        ),
        patch("app.backtest_v2.benchmark.load_price_index", return_value=MagicMock()),
        patch(
            "app.paper_v2.live_engine.get_or_create_book",
            return_value=_fake_book(),
        ),
        patch(
            "app.paper_v2.live_engine.confirmed_replay_days",
            return_value=[_LIVE_DAY],  # ON/AFTER go_live
        ),
        patch(
            "app.paper_v2.live_engine.build_live_context",
            return_value=(MagicMock(), []),
        ),
        patch(
            "app.paper_v2.live_engine.process_day",
            return_value=_fake_report(is_rebalance=True),
        ),
        patch("app.paper_v2.alerter.emit_alerts"),
        # The HALT propagates through the task's except block, which fires
        # emit_failure_alert → send_alert_email (a real Resend POST). Mock it so the
        # test asserts the raise without sending a live email (Rule 5; mirrors TC4).
        patch("app.paper_v2.alerter.emit_failure_alert"),
        patch(
            "app.paper_v2.parity.shadow_parity",
            return_value=_fake_parity(passed=False),  # BREAK
        ),
        patch("app.tasks.SessionLocal"),
        patch("app.tasks._redis") as mock_redis_mod,
    ):
        mock_redis_mod.from_url.return_value = _redis_unlocked()
        with pytest.raises(RuntimeError, match="PARITY BREAK"):
            execute_paper_daily_task("2026-06-30")


# ---------------------------------------------------------------------------
# TC3 — concurrency guard: locked instance must return without processing
# ---------------------------------------------------------------------------


def test_tc3_concurrency_guard_skips_when_locked():
    """A second invocation while the advisory lock is held must return immediately
    without calling process_day or any other work.

    WHY: Two concurrent instances processing the same day sequence would both read
    the same last_processed_date, race through process_day's idempotency check, and
    potentially double-persist or corrupt the pending-fills queue. The lock ensures
    only one instance runs at a time; the TTL auto-cleans a crashed process's lock.
    """
    with (
        patch("app.paper_v2.live_engine.process_day") as mock_process,
        patch("app.tasks._redis") as mock_redis_mod,
    ):
        mock_redis_mod.from_url.return_value = _redis_locked()
        execute_paper_daily_task()

    mock_process.assert_not_called()

    # Verify the SET call used the correct key, NX flag, and TTL.
    redis_client = mock_redis_mod.from_url.return_value
    redis_client.set.assert_called_once_with(
        _PAPER_LOCK_KEY, "1", nx=True, ex=_PAPER_LOCK_TTL
    )
    # Lock must NOT be deleted when it was never acquired.
    redis_client.delete.assert_not_called()


# ---------------------------------------------------------------------------
# TC4 — pipeline failure emits an immediate alert email and still re-raises
# ---------------------------------------------------------------------------


def test_tc4_failure_alert_emitted_and_reraises():
    """A task crash must fire a failure alert email AND re-raise the exception.

    WHY: Silent failures are costly when live capital is deployed — the operator
    needs to know immediately so they can investigate and re-run. The task must
    both alert (operator gets email with traceback) and re-raise (Celery marks
    the run as FAILED and the beat does not silently skip it).
    """
    crash = RuntimeError("bhavcopy fetch failed")
    with (
        patch(
            "app.data.bhavcopy.incremental.incremental_append",
            side_effect=crash,
        ),
        patch(
            "app.data.bhavcopy.store.read_prices_adjusted",
            return_value=_fake_prices(),
        ),
        patch("app.backtest_v2.benchmark.load_price_index", return_value=MagicMock()),
        patch(
            "app.paper_v2.live_engine.get_or_create_book",
            return_value=_fake_book(),
        ),
        patch("app.paper_v2.alerter.emit_failure_alert") as mock_failure_alert,
        patch("app.tasks.SessionLocal"),
        patch("app.tasks._redis") as mock_redis_mod,
    ):
        mock_redis_mod.from_url.return_value = _redis_unlocked()
        with pytest.raises(RuntimeError, match="bhavcopy fetch failed"):
            execute_paper_daily_task("2026-06-23")

    mock_failure_alert.assert_called_once()
    exc_arg, date_arg, tb_arg = mock_failure_alert.call_args[0]
    assert exc_arg is crash
    assert date_arg == "2026-06-23"
    assert "bhavcopy fetch failed" in tb_arg


def test_tc4b_failure_alert_uses_fresh_session_not_the_poisoned_one():
    """The failure-alert session must NOT be the same object as the main ``db``.

    WHY: the main session may be mid-aborted-transaction from the very exception
    being reported (e.g. a Postgres error) — reusing it for the alert insert would
    itself raise and get swallowed by the outer except, silently losing the alert
    (this happened for real on 2026-06-30: a failed run left zero rows in
    paper_v2_alert). A fresh session, committed and closed independently, must be
    used instead — mirroring ``_persist_paper_run``'s existing rationale.
    """
    crash = RuntimeError("bhavcopy fetch failed")
    # Main task session, the failure-alert session, and _persist_paper_run's own
    # fresh session (F4) — three independent SessionLocal() calls in the failure path.
    sessions_created = [MagicMock(name=f"session{i}") for i in range(3)]
    with (
        patch(
            "app.data.bhavcopy.incremental.incremental_append",
            side_effect=crash,
        ),
        patch(
            "app.data.bhavcopy.store.read_prices_adjusted",
            return_value=_fake_prices(),
        ),
        patch("app.backtest_v2.benchmark.load_price_index", return_value=MagicMock()),
        patch(
            "app.paper_v2.live_engine.get_or_create_book",
            return_value=_fake_book(),
        ),
        patch("app.paper_v2.alerter.emit_failure_alert") as mock_failure_alert,
        patch("app.tasks.SessionLocal", side_effect=sessions_created),
        patch("app.tasks._redis") as mock_redis_mod,
    ):
        mock_redis_mod.from_url.return_value = _redis_unlocked()
        with pytest.raises(RuntimeError, match="bhavcopy fetch failed"):
            execute_paper_daily_task("2026-06-23")

    main_db, alert_db, _run_record_db = sessions_created
    used_session = mock_failure_alert.call_args.kwargs["session"]
    assert used_session is alert_db
    assert used_session is not main_db
    alert_db.commit.assert_called_once()
    alert_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# TC5 — transient network errors auto-retry; real halts do not
# ---------------------------------------------------------------------------


def test_tc5_autoretries_only_on_transient_network_errors():
    """Only requests.Timeout/ConnectionError are configured to auto-retry.

    WHY: the 2026-06-30 19:30 IST beat run hit a niftyindices read-timeout and
    needed a manual re-fire — nothing retried automatically. But a RuntimeError
    (parity BREAK, ghost-risk HALT) is a real halt (11 §8/§7.1) that must
    propagate immediately, not be masked by a retry loop.
    """
    autoretry_for = execute_paper_daily_task.autoretry_for
    assert requests.Timeout in autoretry_for
    assert requests.ConnectionError in autoretry_for
    assert RuntimeError not in autoretry_for
    assert execute_paper_daily_task.max_retries == 3
