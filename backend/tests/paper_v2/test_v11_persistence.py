"""V11 (specs/v3/11 viz) — persistence of the NAV snapshot + parity report.

These encode the observability contract the read-only curve/badge depend on (Rule 9):
 * every processed day persists exactly one NAV snapshot (the curve's data source),
 * the snapshot upsert is idempotent so a backfill re-run replaces, never duplicates,
 * ``is_forward`` flips at ``go_live`` (the warm-start↔live divider),
 * an index gap stores NULL (the FE skips it in the overlay),
 * a parity check is durably recorded BEFORE a BREAK halts the run (V11.2), and
 * the engine's fill ``reason`` only ever emits the LOCKED two-value taxonomy.

All offline: synthetic prices, no network, in-memory sqlite (§5 law). Reuses the
fidelity-test panel builders so the snapshots come from the real ``process_day`` path.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.db.models import (
    PaperV2DailySnapshot,
    PaperV2ParityCheck,
    PaperV2PendingFill,
    PaperV2Portfolio,
)
from app.paper_v2 import live_engine, parity
from app.paper_v2.parity import ParityReport
from tests.paper_v2.test_live_engine import (
    _flat_panel,
    _make_index,
    _make_panel,
    _new_portfolio,
)

# ---------------------------------------------------------------------------
# V11.1 — daily NAV snapshot persistence
# ---------------------------------------------------------------------------


def test_v111_snapshot_per_day_forward_flag_and_index_gap(db):
    """One snapshot row per processed day; ``equity`` matches the engine snapshot;
    ``is_forward`` flips at ``go_live``; a date present in ``index_prices`` stores the
    level, a gap date stores NULL."""
    isins = ["INE001A01011", "INE002A01012"]
    prices = _flat_panel(isins, n_days=5)
    dates = sorted(d.date() for d in prices["date"].drop_duplicates())
    d0, d1 = dates[0], dates[1]
    # Index carries d0 only ⇒ d1 is a gap (NULL).
    idx = pd.Series([200.0], index=pd.DatetimeIndex([pd.Timestamp(d0)]))
    go_live = d1  # d0 = warm-start replay, d1 = first counted-forward day

    pf = _new_portfolio(db)
    r0 = live_engine.process_day(
        db, pf.id, prices, idx, d0, commit=False, go_live=go_live
    )
    r1 = live_engine.process_day(
        db, pf.id, prices, idx, d1, commit=False, go_live=go_live
    )

    snaps = (
        db.query(PaperV2DailySnapshot)
        .filter_by(portfolio_id=pf.id)
        .order_by(PaperV2DailySnapshot.date.asc())
        .all()
    )
    assert len(snaps) == 2
    assert [s.date for s in snaps] == [d0, d1]
    assert snaps[0].equity == pytest.approx(r0.snapshot.equity)
    assert snaps[1].equity == pytest.approx(r1.snapshot.equity)
    # Divider: d0 is warm-start, d1 (>= go_live) is forward.
    assert snaps[0].is_forward is False
    assert snaps[1].is_forward is True
    # Index gap handling.
    assert snaps[0].index_level == pytest.approx(200.0)
    assert snaps[1].index_level is None


def test_v111_snapshot_upsert_is_idempotent_on_backfill_rerun(db):
    """A backfill re-run of the same day upserts the snapshot — no duplicate row
    (Pipeline Law: idempotency or death)."""
    isins = ["INE001A01011", "INE002A01012"]
    prices = _flat_panel(isins, n_days=5)
    d0 = sorted(d.date() for d in prices["date"].drop_duplicates())[0]

    pf = _new_portfolio(db)
    live_engine.process_day(db, pf.id, prices, None, d0, commit=False)
    # Simulate a backfill that re-processes an already-applied day (reset the clock so
    # the idempotency guard lets it through to the upsert path).
    pf.last_processed_date = None
    db.flush()
    live_engine.process_day(db, pf.id, prices, None, d0, commit=False)

    snaps = db.query(PaperV2DailySnapshot).filter_by(portfolio_id=pf.id, date=d0).all()
    assert len(snaps) == 1  # replaced, not duplicated


# ---------------------------------------------------------------------------
# V11.2 — parity report persistence + break-before-halt durability
# ---------------------------------------------------------------------------


def _seed_book(db) -> PaperV2Portfolio:
    pf = PaperV2Portfolio(name="s3_probation_v11", cash=1_000_000.0, is_active=True)
    db.add(pf)
    db.flush()
    return pf


def test_v112_persist_parity_pass_and_idempotent_upsert(db):
    pf = _seed_book(db)
    rep = ParityReport(as_of=date(2026, 6, 30), passed=True, max_dev_bps=3.2)
    parity.persist_parity(db, pf.id, rep)
    db.flush()

    rows = db.query(PaperV2ParityCheck).filter_by(portfolio_id=pf.id).all()
    assert len(rows) == 1
    assert rows[0].passed is True
    assert rows[0].max_dev_bps == pytest.approx(3.2)
    assert rows[0].tol_bps == pytest.approx(parity.PARITY_TOL_BPS)
    assert rows[0].breaches == []

    # Re-running the same as_of upserts (e.g. a backfill) — one row, latest values.
    rep2 = ParityReport(
        as_of=date(2026, 6, 30),
        passed=False,
        max_dev_bps=40.0,
        breaches=[("INE9", 40.0)],
    )
    parity.persist_parity(db, pf.id, rep2)
    db.flush()
    rows = db.query(PaperV2ParityCheck).filter_by(portfolio_id=pf.id).all()
    assert len(rows) == 1
    assert rows[0].passed is False
    assert rows[0].breaches == [["INE9", 40.0]]  # JSON: tuples ⇒ arrays


def test_v112_break_row_persisted_then_raises(db):
    """A BREAK writes its row BEFORE the run halts (mirrors the tasks.py ordering: the
    daily task ``persist_parity`` + ``db.commit()`` then raises). The LOCKED durability
    mechanism in tasks.py is ``commit`` (not flush), so the row survives the halt's
    ``finally: db.close()`` rollback; here the fixture's open transaction makes the
    flushed row observable after the raise — the assertion the spec mandates."""
    pf = _seed_book(db)
    rep = ParityReport(
        as_of=date(2026, 7, 31),
        passed=False,
        max_dev_bps=99.0,
        breaches=[("INE9", 99.0)],
    )
    with pytest.raises(RuntimeError):
        parity.persist_parity(db, pf.id, rep)
        db.flush()
        raise RuntimeError("PARITY BREAK on 2026-07-31 — halting (11 §8)")

    row = (
        db.query(PaperV2ParityCheck)
        .filter_by(portfolio_id=pf.id, as_of=date(2026, 7, 31))
        .one()
    )
    assert row.passed is False
    assert row.max_dev_bps == pytest.approx(99.0)


# ---------------------------------------------------------------------------
# V11.3 — fill reason taxonomy is exactly the LOCKED two-value set
# ---------------------------------------------------------------------------


def test_v113_fill_reason_taxonomy_is_locked_two_values(db):
    """LOCKED (11 viz V11.3 #3): paper_v2 fills only ever carry ``rebalance`` or
    ``catastrophic_stop``. A third value would make the FE rebalance/stop badge silently
    mislabel — fail loud here (Rule 12) rather than let the FE fall through to a default.
    Runs a real momentum replay so at least one fill is actually queued."""
    isins = [f"ISIN{i:02d}" for i in range(25)]
    prices = _make_panel(isins, n_days=400)
    index = _make_index(prices)
    ctx, calendar = live_engine.build_live_context(prices, index)

    pf = _new_portfolio(db)
    for day in calendar:
        live_engine.process_day(db, pf.id, prices, index, day, commit=False, ctx=ctx)

    reasons = {
        r.reason for r in db.query(PaperV2PendingFill).filter_by(portfolio_id=pf.id)
    }
    assert reasons, "the replay must queue at least one fill for this to be meaningful"
    assert reasons <= {"rebalance", "catastrophic_stop"}
