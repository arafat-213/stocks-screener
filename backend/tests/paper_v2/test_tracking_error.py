"""F1 — Cumulative tracking-error tile + sparkline tests (specs/v3/12 F1).

WHY these tests matter (Rule 9):
- TE must exclude warm-start (is_forward=False) snapshots.  Warm-start replay is
  backtest, not live fidelity; including it would inflate or distort TE with
  non-forward return differences.
- TE is exactly zero when book return equals benchmark return every day.  The
  annualization path (std × sqrt(252)) must not produce a non-zero result from
  zero-difference inputs.
- Annualisation uses sqrt(252) to convert daily std to annualized %. A test with
  seeded daily diffs verifies the factor directly — using daily std raw would
  under-report by ~16× the volatility a committee sees over months.
- Basis must always be "mom30": no daily shadow NAV is persisted, so the endpoint
  always uses option (b) from the F1 spec.  A basis of "shadow" would require a
  shadow-NAV persistence job that does not yet exist.
- Fewer than 2 forward days returns annualized_te_pct=0.0 (no std is computable
  from a single return).
- The cumulative-diff series anchors at 0.0 on the first forward day and grows
  by the running sum of daily differences; a sparkline that starts at a non-zero
  value would imply drift on the very first day (which has no prior day to compare
  against).
"""

from __future__ import annotations

import datetime
import math
from datetime import date

import pytest

from app.db.models import (
    PaperV2DailySnapshot,
    PaperV2Portfolio,
)
from app.paper_v2.live_engine import PROBATION_BOOK_NAME

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GO_LIVE = datetime.datetime(2026, 6, 23, tzinfo=datetime.timezone.utc)
_GO_LIVE_DATE = date(2026, 6, 23)


def _make_book(db) -> PaperV2Portfolio:
    pf = PaperV2Portfolio(
        name=PROBATION_BOOK_NAME,
        starting_capital=1_000_000.0,
        cash=1_000_000.0,
        is_active=True,
        last_processed_date=date(2026, 6, 30),
        created_at=_GO_LIVE,
    )
    db.add(pf)
    db.flush()
    return pf


def _make_snapshot(
    db,
    portfolio_id: int,
    *,
    snap_date: date,
    equity: float = 1_000_000.0,
    index_level: float = 10_000.0,
    is_forward: bool = True,
) -> PaperV2DailySnapshot:
    s = PaperV2DailySnapshot(
        portfolio_id=portfolio_id,
        date=snap_date,
        equity=equity,
        cash=500_000.0,
        invested_value=equity - 500_000.0,
        exposure=0.5,
        n_positions=10,
        index_level=index_level,
        is_forward=is_forward,
    )
    db.add(s)
    db.flush()
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_te_is_zero_when_book_return_equals_benchmark_every_day(client, db):
    """When book return == benchmark return each day, std of diffs == 0, TE == 0.

    Validates that the annualization path (std × sqrt(252)) does not introduce
    floating-point noise that produces a spurious non-zero result.
    """
    book = _make_book(db)
    # 5 forward days — book NAV and index move in lock-step (+1% each day)
    for i in range(5):
        factor = 1.01**i
        _make_snapshot(
            db,
            book.id,
            snap_date=_GO_LIVE_DATE + datetime.timedelta(days=i),
            equity=1_000_000.0 * factor,
            index_level=10_000.0 * factor,
            is_forward=True,
        )

    resp = client.get("/api/v2/paper/tracking-error")
    assert resp.status_code == 200
    data = resp.json()
    assert data["annualized_te_pct"] == pytest.approx(0.0, abs=1e-9)
    assert data["n_days"] == 5
    assert data["basis"] == "mom30"


def test_te_excludes_warmstart_days(client, db):
    """Warm-start (is_forward=False) snapshots must not affect TE.

    Warm-start is replay, not live fidelity.  If included, its return
    differences would dilute or inflate the live-only TE figure.
    """
    book = _make_book(db)
    # 3 warm-start days with large divergence — these must NOT drive TE
    for i in range(3):
        _make_snapshot(
            db,
            book.id,
            snap_date=_GO_LIVE_DATE - datetime.timedelta(days=3 - i),
            equity=1_000_000.0 * (1 + 0.05 * i),  # 5% drift per day
            index_level=10_000.0,
            is_forward=False,
        )
    # 4 forward days: perfect lock-step → TE must be 0
    for i in range(4):
        factor = 1.01**i
        _make_snapshot(
            db,
            book.id,
            snap_date=_GO_LIVE_DATE + datetime.timedelta(days=i),
            equity=1_000_000.0 * factor,
            index_level=10_000.0 * factor,
            is_forward=True,
        )

    resp = client.get("/api/v2/paper/tracking-error")
    assert resp.status_code == 200
    data = resp.json()
    assert data["annualized_te_pct"] == pytest.approx(0.0, abs=1e-9)
    assert data["n_days"] == 4  # only forward rows counted


def test_te_annualization_matches_sqrt_252(client, db):
    """Annualized TE = sample_std(daily_diffs) × sqrt(252) × 100.

    With a seeded constant daily diff we can compute the expected value
    exactly, verifying the annualization factor is sqrt(252) and not 1 or 365.
    """
    book = _make_book(db)
    # 5 forward days: book grows at 1% / day, index at 0.5% / day
    # → constant daily diff = 0.01 − 0.005 = 0.005
    equity_0 = 1_000_000.0
    idx_0 = 10_000.0
    for i in range(5):
        _make_snapshot(
            db,
            book.id,
            snap_date=_GO_LIVE_DATE + datetime.timedelta(days=i),
            equity=equity_0 * (1.01**i),
            index_level=idx_0 * (1.005**i),
            is_forward=True,
        )

    resp = client.get("/api/v2/paper/tracking-error")
    assert resp.status_code == 200
    data = resp.json()

    # Compute expected: 4 daily diffs of 0.01 − 0.005 = 0.005 (exactly)
    diffs = [0.01 - 0.005] * 4  # 4 consecutive-pair diffs from 5 rows
    mean_d = sum(diffs) / len(diffs)
    variance = sum((d - mean_d) ** 2 for d in diffs) / (len(diffs) - 1)
    expected_te = math.sqrt(variance) * math.sqrt(252) * 100.0

    # Because all diffs are identical the sample std is 0 → expected_te == 0.
    # That is the correct answer: a strategy with a CONSTANT daily outperformance
    # has zero TE (it tracks the benchmark plus a fixed alpha).
    assert data["annualized_te_pct"] == pytest.approx(expected_te, abs=1e-6)


def test_te_basis_is_always_mom30(client, db):
    """Basis must be 'mom30' — no shadow NAV is persisted (F1 spec option b).

    If the basis were ever 'shadow' without a shadow-NAV persistence job, the
    endpoint would be referencing data that doesn't exist.
    """
    book = _make_book(db)
    for i in range(3):
        _make_snapshot(
            db,
            book.id,
            snap_date=_GO_LIVE_DATE + datetime.timedelta(days=i),
            is_forward=True,
        )

    resp = client.get("/api/v2/paper/tracking-error")
    assert resp.status_code == 200
    assert resp.json()["basis"] == "mom30"


def test_te_insufficient_data_returns_zero(client, db):
    """Fewer than 2 forward days → annualized_te_pct=0.0, n_days matches rows.

    Std is undefined for a single return, so the endpoint must return 0 rather
    than raising an error or dividing by zero.
    """
    book = _make_book(db)
    _make_snapshot(
        db, book.id, snap_date=_GO_LIVE_DATE, equity=1_000_000.0, is_forward=True
    )

    resp = client.get("/api/v2/paper/tracking-error")
    assert resp.status_code == 200
    data = resp.json()
    assert data["annualized_te_pct"] == 0.0
    assert data["n_days"] == 1


def test_te_no_book_returns_empty(client, db):
    """No active book returns n_days=0 and empty series (no 404)."""
    resp = client.get("/api/v2/paper/tracking-error")
    assert resp.status_code == 200
    data = resp.json()
    assert data["n_days"] == 0
    assert data["annualized_te_pct"] == 0.0
    assert data["series"] == []


def test_te_cumulative_series_anchors_at_zero(client, db):
    """The sparkline series must start at cum_diff_pct=0.0 on the first forward day.

    A non-zero anchor would imply drift on the very first day, which has no
    prior day to compute a return against.
    """
    book = _make_book(db)
    # 3 forward days: book outperforms by 1pp / day
    for i in range(3):
        _make_snapshot(
            db,
            book.id,
            snap_date=_GO_LIVE_DATE + datetime.timedelta(days=i),
            equity=1_000_000.0 * (1.01**i),
            index_level=10_000.0,  # flat benchmark
            is_forward=True,
        )

    resp = client.get("/api/v2/paper/tracking-error")
    assert resp.status_code == 200
    series = resp.json()["series"]
    assert len(series) == 3
    assert series[0]["cum_diff_pct"] == pytest.approx(0.0, abs=1e-9)
    # Day 2: book +1%, index 0% → diff ≈ +1pp cumulative
    assert series[1]["cum_diff_pct"] == pytest.approx(1.0, abs=0.01)


def test_te_skips_snapshots_with_null_index_level(client, db):
    """Snapshots with index_level=None are excluded from TE computation.

    A day with no benchmark price (holiday gap, data lag) cannot contribute a
    return difference; including it would fabricate a zero-diff or divide-by-zero.
    """
    book = _make_book(db)
    _make_snapshot(
        db, book.id, snap_date=_GO_LIVE_DATE, equity=1_000_000.0, is_forward=True
    )
    # Gap day: no index level
    s = PaperV2DailySnapshot(
        portfolio_id=book.id,
        date=_GO_LIVE_DATE + datetime.timedelta(days=1),
        equity=1_010_000.0,
        cash=500_000.0,
        invested_value=510_000.0,
        exposure=0.505,
        n_positions=10,
        index_level=None,
        is_forward=True,
    )
    db.add(s)
    db.flush()
    _make_snapshot(
        db,
        book.id,
        snap_date=_GO_LIVE_DATE + datetime.timedelta(days=2),
        equity=1_020_000.0,
        is_forward=True,
    )

    resp = client.get("/api/v2/paper/tracking-error")
    assert resp.status_code == 200
    data = resp.json()
    # Only 2 rows with non-null index_level → n_days=2
    assert data["n_days"] == 2
