"""F6 scorecard snapshot — durability tests (specs/v3/14 Fix #2).

WHY these tests matter (Rule 9 — tests verify intent, not just behavior):
- The live ``/scorecard`` endpoint recomputes from mutable tables, so a later
  bhavcopy backfill can silently change a past reading. The snapshot table exists
  to freeze what the scorecard said, on what data, at a given month-end — these
  tests encode that the freeze actually holds (round-trips, doesn't get
  overwritten by a later state change, and doesn't silently duplicate on a re-run).
- ``build_scorecard`` must be the SAME code path the live endpoint and the
  snapshot writer both use — if they ever diverged, a snapshot could disagree
  with what the operator saw live at the time, defeating the whole point of a
  durable record.
"""

from __future__ import annotations

import datetime

from app.db.models import PaperV2ScorecardSnapshot
from app.routers.paper_v2 import (
    ScorecardResponse,
    _upsert_scorecard_snapshot,
    build_scorecard,
)
from tests.paper_v2.test_scorecard import _add_fill, _add_parity, _add_run, _make_book

_GO_LIVE = datetime.date(2026, 6, 23)


# ---------------------------------------------------------------------------
# TS21 — build_scorecard is the single source of truth for the live endpoint
# ---------------------------------------------------------------------------


def test_ts21_build_scorecard_matches_live_endpoint(client, db):
    """build_scorecard(db, book) must equal what GET /scorecard returns.

    WHY: Fix #2's snapshot writer calls build_scorecard directly (fresh session,
    no HTTP round-trip). If it could ever diverge from the endpoint's own
    computation, a snapshot could freeze a DIFFERENT verdict than what the
    operator actually saw live that day — silently defeating the "one source of
    truth" guarantee the spec requires.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    _add_parity(db, pf, datetime.date(2026, 7, 28), passed=True, max_dev_bps=10.0)
    _add_fill(db, pf, _GO_LIVE, qty=10.0, decision_price=100.0, fill_price=100.05)

    direct = build_scorecard(db, pf)
    resp = client.get("/api/v2/paper/scorecard")
    assert resp.status_code == 200
    assert direct.model_dump(mode="json") == resp.json()


# ---------------------------------------------------------------------------
# TS22 — insert + payload round-trip
# ---------------------------------------------------------------------------


def test_ts22_snapshot_insert_and_payload_roundtrip(db):
    """A fresh (portfolio_id, as_of_date, trigger) upsert must insert exactly one
    row whose payload round-trips to an equal ScorecardResponse.

    WHY: The whole point of the snapshot is that a future close-out review can
    reconstruct exactly what the scorecard said without re-deriving from
    (possibly since-changed) source tables. If payload didn't round-trip, the
    frozen record would be useless for that purpose.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    _add_parity(db, pf, datetime.date(2026, 7, 28), passed=True, max_dev_bps=10.0)
    scorecard = build_scorecard(db, pf)
    as_of = datetime.date(2026, 7, 28)

    _upsert_scorecard_snapshot(db, pf.id, as_of, "month_end", scorecard)
    db.flush()

    rows = db.query(PaperV2ScorecardSnapshot).filter_by(portfolio_id=pf.id).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.as_of_date == as_of
    assert row.trigger == "month_end"
    assert row.verdict == scorecard.verdict
    assert row.clean_months_passed == scorecard.clean_months_passed
    assert row.clock_reset_at == scorecard.clock_reset_at
    assert ScorecardResponse(**row.payload) == scorecard


# ---------------------------------------------------------------------------
# TS23 — idempotency: a re-run of the same month-end updates in place
# ---------------------------------------------------------------------------


def test_ts23_snapshot_upsert_idempotent_updates_in_place(db):
    """Calling the upsert twice for the same (portfolio_id, as_of_date, trigger)
    must still leave exactly one row, reflecting the SECOND (latest) state.

    WHY: 11 §11's frozen record must not silently duplicate on a task retry or a
    manual re-fire of the same processed date — the spec explicitly requires
    'updates that row, never appends' (Pipeline Law: idempotency or death).
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    as_of = datetime.date(2026, 7, 28)

    # First call: no parity yet -> Gate 1 insufficient_data, verdict ON TRACK.
    first = build_scorecard(db, pf)
    _upsert_scorecard_snapshot(db, pf.id, as_of, "month_end", first)
    db.flush()
    assert first.verdict == "ON TRACK"

    # State changes between calls (e.g. a re-fire after a later backfill): a
    # parity fail now exists, so the second build reflects AT RISK.
    _add_parity(db, pf, as_of, passed=False, max_dev_bps=80.0)
    second = build_scorecard(db, pf)
    assert second.verdict == "AT RISK"

    _upsert_scorecard_snapshot(db, pf.id, as_of, "month_end", second)
    db.flush()

    rows = db.query(PaperV2ScorecardSnapshot).filter_by(portfolio_id=pf.id).all()
    assert len(rows) == 1, "re-run must update in place, not append a second row"
    assert rows[0].verdict == "AT RISK"
    assert rows[0].clock_reset_at == as_of


# ---------------------------------------------------------------------------
# TS24 — a different trigger for the same date is a distinct row (not a collision)
# ---------------------------------------------------------------------------


def test_ts24_different_trigger_same_date_is_a_separate_row(db):
    """A 'manual' snapshot on the same as_of_date as an existing 'month_end' one
    must NOT collide with it — the uniqueness key includes trigger.

    WHY: the spec reserves 'manual' as a future admin-triggered snapshot kind; it
    must never silently clobber the month-end graduation record for that date.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    as_of = datetime.date(2026, 7, 28)
    scorecard = build_scorecard(db, pf)

    _upsert_scorecard_snapshot(db, pf.id, as_of, "month_end", scorecard)
    _upsert_scorecard_snapshot(db, pf.id, as_of, "manual", scorecard)
    db.flush()

    rows = db.query(PaperV2ScorecardSnapshot).filter_by(portfolio_id=pf.id).all()
    assert len(rows) == 2
    assert {r.trigger for r in rows} == {"month_end", "manual"}


# ---------------------------------------------------------------------------
# TS25 — GET /scorecard/snapshots endpoint
# ---------------------------------------------------------------------------


def test_ts25_snapshots_endpoint_returns_newest_first(client, db):
    """GET /scorecard/snapshots must return rows scoped to the active book,
    newest as_of_date first.

    WHY: a future close-out review timeline needs the most recent month-end
    verdict at the top, and must never leak a hypothetical prior book's rows.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    scorecard = build_scorecard(db, pf)

    older = datetime.date(2026, 7, 28)
    newer = datetime.date(2026, 8, 28)
    _upsert_scorecard_snapshot(db, pf.id, older, "month_end", scorecard)
    _upsert_scorecard_snapshot(db, pf.id, newer, "month_end", scorecard)
    db.commit()

    resp = client.get("/api/v2/paper/scorecard/snapshots")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["as_of_date"] == str(newer)
    assert data[1]["as_of_date"] == str(older)
    assert data[0]["verdict"] == scorecard.verdict


def test_ts26_snapshots_endpoint_empty_when_no_active_book(client, db):
    """No active book -> empty list, not a 404 or error (matches /alerts, /runs)."""
    resp = client.get("/api/v2/paper/scorecard/snapshots")
    assert resp.status_code == 200
    assert resp.json() == []
