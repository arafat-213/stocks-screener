"""Tests for the read-only v2 S3 paper-book API (app/routers/paper_v2.py).

These encode WHY (Rule 9): the frontend must see the *frozen* book's true NAV
and per-holding MTM/weight derived purely from stored state — never a live
fetch — and an unarmed probation must degrade cleanly, not 500.
"""

import datetime

import pytest

from app.db import models


def _make_book(db, *, cash, starting_capital=1_000_000.0, name="s3_probation"):
    book = models.PaperV2Portfolio(
        name=name,
        starting_capital=starting_capital,
        cash=cash,
        is_active=True,
        last_processed_date=datetime.date(2026, 6, 18),
    )
    db.add(book)
    db.commit()
    return book


def _add_position(db, book, **kw):
    defaults = dict(
        portfolio_id=book.id,
        shares=10.0,
        cost_basis=100.0,
        last_price=120.0,
        entry_date=datetime.date(2026, 1, 1),
        days_held=5,
    )
    defaults.update(kw)
    pos = models.PaperV2Position(**defaults)
    db.add(pos)
    db.commit()
    return pos


def test_book_404_when_not_armed(client, db):
    # No active book yet — the probation is not armed. Must 404, not 500.
    response = client.get("/api/v2/paper/book")
    assert response.status_code == 404


def test_book_nav_and_return(client, db):
    # cash 200k + one holding worth 10×120 = 1.2k → NAV 201.2k on 1.0M start.
    book = _make_book(db, cash=200_000.0)
    _add_position(
        db, book, isin="INE111A01011", symbol="ACME", shares=10.0, last_price=120.0
    )

    response = client.get("/api/v2/paper/book")
    assert response.status_code == 200
    data = response.json()

    assert data["cash"] == 200_000.0
    assert data["holdings_value"] == 1_200.0  # 10 × 120
    assert data["nav"] == 201_200.0
    assert data["n_positions"] == 1
    # (201200 − 1000000) / 1000000 × 100
    assert abs(data["total_return_pct"] - (-79.88)) < 0.01
    assert data["last_processed_date"] == "2026-06-18"


def test_positions_mtm_weight_and_sort(client, db):
    book = _make_book(db, cash=0.0)
    # Two holdings; the bigger MTM must sort first and weights must sum sensibly.
    _add_position(
        db,
        book,
        isin="INE001A01011",
        symbol="SMALL",
        shares=10.0,
        cost_basis=100.0,
        last_price=120.0,  # MTM 1200, +20%
    )
    _add_position(
        db,
        book,
        isin="INE002A01012",
        symbol="BIG",
        shares=100.0,
        cost_basis=50.0,
        last_price=80.0,  # MTM 8000, +60%
    )

    response = client.get("/api/v2/paper/positions")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2

    # Largest holding first.
    assert rows[0]["symbol"] == "BIG"
    assert rows[0]["market_value"] == 8_000.0
    assert abs(rows[0]["unrealized_pct"] - 60.0) < 1e-6
    # NAV = cash(0) + 1200 + 8000 = 9200 → BIG weight = 8000/9200.
    assert abs(rows[0]["weight_pct"] - (8_000.0 / 9_200.0 * 100.0)) < 1e-6

    assert rows[1]["symbol"] == "SMALL"
    assert abs(rows[1]["unrealized_pct"] - 20.0) < 1e-6


def test_positions_empty_when_not_armed(client, db):
    # Unarmed probation → positions endpoint returns [] (not 404, not 500).
    response = client.get("/api/v2/paper/positions")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# V11.3 — /nav, /parity, /rebalances (read-only, persisted state only)
# ---------------------------------------------------------------------------


def _add_snapshot(db, book, d, equity, *, index_level=None, is_forward=False):
    row = models.PaperV2DailySnapshot(
        portfolio_id=book.id,
        date=d,
        equity=equity,
        cash=equity,
        invested_value=0.0,
        exposure=0.0,
        n_positions=0,
        index_level=index_level,
        is_forward=is_forward,
    )
    db.add(row)
    db.commit()
    return row


def _add_parity(db, book, as_of, *, passed, max_dev_bps, breaches=None):
    row = models.PaperV2ParityCheck(
        portfolio_id=book.id,
        as_of=as_of,
        passed=passed,
        max_dev_bps=max_dev_bps,
        tol_bps=25.0,
        breaches=breaches,
    )
    db.add(row)
    db.commit()
    return row


def _add_fill(db, book, decision_date, *, side, reason, symbol, cost_rupees=None):
    row = models.PaperV2PendingFill(
        portfolio_id=book.id,
        isin="INE" + symbol,
        symbol=symbol,
        side=side,
        qty=10.0,
        reason=reason,
        decision_date=decision_date,
        status="pending",
        cost_rupees=cost_rupees,
    )
    db.add(row)
    db.commit()
    return row


def test_nav_envelope_ascending_and_rebased_index(client, db):
    # starting_capital default 1e6; created_at default now ⇒ go_live_date is set.
    book = _make_book(db, cash=1_000_000.0)
    d1, d2, d3 = (
        datetime.date(2026, 6, 16),
        datetime.date(2026, 6, 17),
        datetime.date(2026, 6, 18),
    )
    # Seeded OUT OF ORDER to prove the server sorts ascending. d2 is an index gap.
    _add_snapshot(db, book, d2, 1_010_000.0, index_level=None, is_forward=True)
    _add_snapshot(db, book, d1, 1_000_000.0, index_level=200.0, is_forward=False)
    _add_snapshot(db, book, d3, 1_020_000.0, index_level=210.0, is_forward=True)

    resp = client.get("/api/v2/paper/nav")
    assert resp.status_code == 200
    data = resp.json()

    assert data["go_live_date"] is not None
    pts = data["points"]
    assert [p["date"] for p in pts] == ["2026-06-16", "2026-06-17", "2026-06-18"]
    # Rebase anchor = first non-null index level (200.0 at d1) → d1 rebased == start cap.
    assert pts[0]["index_rebased"] == pytest.approx(1_000_000.0)
    assert pts[1]["index_rebased"] is None  # gap day → NULL
    assert pts[2]["index_rebased"] == pytest.approx(210.0 / 200.0 * 1_000_000.0)
    # Divider flag carried through.
    assert pts[0]["is_forward"] is False
    assert pts[2]["is_forward"] is True


def test_nav_empty_when_not_armed(client, db):
    resp = client.get("/api/v2/paper/nav")
    assert resp.status_code == 200
    assert resp.json() == {"go_live_date": None, "points": []}


def test_parity_latest_is_max_asof_and_history_ascending(client, db):
    book = _make_book(db, cash=1_000_000.0)
    _add_parity(db, book, datetime.date(2026, 6, 30), passed=True, max_dev_bps=3.0)
    _add_parity(
        db,
        book,
        datetime.date(2026, 4, 30),
        passed=False,
        max_dev_bps=40.0,
        breaches=[["INE9", 40.0]],
    )
    _add_parity(db, book, datetime.date(2026, 5, 31), passed=True, max_dev_bps=2.0)

    resp = client.get("/api/v2/paper/parity")
    assert resp.status_code == 200
    data = resp.json()

    assert [h["as_of"] for h in data["history"]] == [
        "2026-04-30",
        "2026-05-31",
        "2026-06-30",
    ]
    assert data["latest"]["as_of"] == "2026-06-30"
    assert data["latest"]["passed"] is True
    # breaches round-trip as (isin, dev) pairs.
    assert data["history"][0]["breaches"] == [["INE9", 40.0]]


def test_parity_empty_when_not_armed(client, db):
    resp = client.get("/api/v2/paper/parity")
    assert resp.status_code == 200
    assert resp.json() == {"latest": None, "history": []}


def test_rebalances_grouped_newest_first(client, db):
    book = _make_book(db, cash=1_000_000.0)
    # Older event: a rebalance (2 buys + 1 sell).
    may = datetime.date(2026, 5, 29)
    _add_fill(db, book, may, side="buy", reason="rebalance", symbol="A")
    _add_fill(db, book, may, side="buy", reason="rebalance", symbol="B")
    _add_fill(db, book, may, side="sell", reason="rebalance", symbol="C")
    # Newer event: a catastrophic stop (single sell with a cost).
    jun = datetime.date(2026, 6, 15)
    _add_fill(
        db,
        book,
        jun,
        side="sell",
        reason="catastrophic_stop",
        symbol="D",
        cost_rupees=12.5,
    )

    resp = client.get("/api/v2/paper/rebalances")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2

    # Newest decision_date first.
    assert events[0]["decision_date"] == "2026-06-15"
    assert events[0]["reason"] == "catastrophic_stop"
    assert events[0]["n_sells"] == 1 and events[0]["n_buys"] == 0
    assert events[0]["total_cost_rupees"] == pytest.approx(12.5)
    assert len(events[0]["fills"]) == 1

    assert events[1]["decision_date"] == "2026-05-29"
    # Any rebalance fill in the group ⇒ the event is labelled a rebalance.
    assert events[1]["reason"] == "rebalance"
    assert events[1]["n_buys"] == 2 and events[1]["n_sells"] == 1


def test_rebalances_empty_when_not_armed(client, db):
    resp = client.get("/api/v2/paper/rebalances")
    assert resp.status_code == 200
    assert resp.json() == []
