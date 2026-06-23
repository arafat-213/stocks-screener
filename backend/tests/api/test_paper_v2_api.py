"""Tests for the read-only v2 S3 paper-book API (app/routers/paper_v2.py).

These encode WHY (Rule 9): the frontend must see the *frozen* book's true NAV
and per-holding MTM/weight derived purely from stored state — never a live
fetch — and an unarmed probation must degrade cleanly, not 500.
"""

import datetime

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
