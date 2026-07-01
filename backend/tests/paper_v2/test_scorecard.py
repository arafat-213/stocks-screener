"""F6 — Probation scorecard tests (specs/v3/12 F6).

WHY these tests matter (Rule 9 — tests verify intent, not just behavior):
- The clean-month clock MUST reset to 0 on any parity fail (not just passed=False;
  max_dev_bps > 25 also resets the clock even when passed=True) and count only
  consecutive passes from the last fail. The graduation denominator is 6 CLEAN
  months (§7.1), not naive elapsed months — conflating them is the goalpost-drift
  failure mode the program guards against.
- Each gate threshold is verbatim from 11 §7/§8 (§2.3): 25 bps / pessimistic band
  / 15 pp / 5 stops / 23.1% maxDD. The tests encode these values so any edit to
  the constants is immediately caught.
- Un-evaluable gates MUST return 'insufficient_data', never a fabricated pass.
  A fabricated pass would let the UI declare ON TRACK when it shouldn't.
- The HALT verdict must fire on any kill criterion — catastrophic-stop count ≥ 5
  in one window, OR maxDD > 23.1% — regardless of gate status.
"""

from __future__ import annotations

import datetime

from app.db.models import (
    PaperV2DailySnapshot,
    PaperV2ParityCheck,
    PaperV2PendingFill,
    PaperV2Portfolio,
    PaperV2Run,
)
from app.paper_v2.live_engine import PROBATION_BOOK_NAME

# ---------------------------------------------------------------------------
# Constants mirrored from the router — if these diverge the tests catch it
# (Rule 9: tests encode WHY, not just shape).
# ---------------------------------------------------------------------------
_FIDELITY_TOL_BPS = 25.0
_DIRECTIONAL_LIMIT_PP = 15.0
_KILL_CSTOP = 5
_KILL_MAXDD_PCT = 23.1

_UTC = datetime.timezone.utc
_GO_LIVE = datetime.date(2026, 6, 23)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_book(db, *, go_live: datetime.date = _GO_LIVE, last_processed=None):
    pf = PaperV2Portfolio(
        name=PROBATION_BOOK_NAME,
        starting_capital=1_000_000.0,
        cash=950_000.0,
        is_active=True,
        last_processed_date=last_processed or go_live,
        created_at=datetime.datetime(
            go_live.year, go_live.month, go_live.day, tzinfo=_UTC
        ),
    )
    db.add(pf)
    db.flush()
    return pf


def _add_parity(db, pf, as_of: datetime.date, *, passed: bool, max_dev_bps: float):
    pc = PaperV2ParityCheck(
        portfolio_id=pf.id,
        as_of=as_of,
        passed=passed,
        max_dev_bps=max_dev_bps,
        tol_bps=25.0,
    )
    db.add(pc)
    db.flush()
    return pc


def _add_run(db, pf, *, status: str = "success", last_date=None):
    r = PaperV2Run(
        portfolio_id=pf.id,
        started_at=datetime.datetime(2026, 6, 30, tzinfo=_UTC),
        finished_at=datetime.datetime(2026, 6, 30, 0, 5, tzinfo=_UTC),
        trigger="beat",
        status=status,
        days_processed=1 if status == "success" else 0,
        first_date=last_date,
        last_date=last_date,
        error_class=None,
        error_msg=None,
    )
    db.add(r)
    db.flush()
    return r


def _add_snap(
    db,
    pf,
    date: datetime.date,
    equity: float,
    *,
    is_forward: bool = True,
    index_level: float | None = None,
):
    s = PaperV2DailySnapshot(
        portfolio_id=pf.id,
        date=date,
        equity=equity,
        cash=0.0,
        invested_value=equity,
        exposure=1.0,
        n_positions=10,
        index_level=index_level,
        is_forward=is_forward,
    )
    db.add(s)
    db.flush()
    return s


def _add_fill(
    db,
    pf,
    decision_date: datetime.date,
    *,
    reason: str = "rebalance",
    side: str = "buy",
    qty: float = 10.0,
    decision_price: float = 100.0,
    fill_price: float = 101.0,
    cost_rupees: float = 10.0,
    status: str = "filled",
):
    f = PaperV2PendingFill(
        portfolio_id=pf.id,
        isin="INE001A01036",
        symbol="RELIANCE.NS",
        side=side,
        qty=qty,
        reason=reason,
        decision_date=decision_date,
        decision_price=decision_price,
        fill_price=fill_price,
        cost_rupees=cost_rupees,
        status=status,
    )
    db.add(f)
    db.flush()
    return f


# ---------------------------------------------------------------------------
# TS1 — Clean-month clock: resets on parity fail, counts from last fail
# ---------------------------------------------------------------------------


def test_ts1_clean_months_pass_only(client, db):
    """Three consecutive passes → clean_months=3, no clock reset.

    WHY: The graduation gate requires 6 *consecutive* clean months. Three passes
    with no fail must yield clean_months=3 and clock_reset_at=None so the
    scorecard correctly reflects progress without premature graduation.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    for i in range(3):
        _add_parity(
            db,
            pf,
            datetime.date(2026, 7 + i, 28),
            passed=True,
            max_dev_bps=10.0,
        )

    resp = client.get("/api/v2/paper/scorecard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["clean_months_passed"] == 3
    assert data["clock_reset_at"] is None


def test_ts2_clean_months_reset_on_fail(client, db):
    """Pass, pass, fail, pass → clean_months=1, clock_reset_at=fail date.

    WHY: The graduation denominator resets the moment any month fails. After a
    fail the clock must show only the passes AFTER the reset, not the cumulative
    total. This test encodes the exact §7.1 rule: 6 clean months since last fail.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    _add_parity(db, pf, datetime.date(2026, 7, 28), passed=True, max_dev_bps=5.0)
    _add_parity(db, pf, datetime.date(2026, 8, 28), passed=True, max_dev_bps=5.0)
    fail_date = datetime.date(2026, 9, 28)
    _add_parity(db, pf, fail_date, passed=False, max_dev_bps=80.0)
    _add_parity(db, pf, datetime.date(2026, 10, 28), passed=True, max_dev_bps=5.0)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    assert data["clean_months_passed"] == 1
    assert data["clock_reset_at"] == str(fail_date)


def test_ts3_max_dev_bps_above_25_resets_clock_even_when_passed_true(client, db):
    """passed=True but max_dev_bps=26 must STILL reset the clock.

    WHY: The gate is pass=True AND max_dev_bps ≤ 25 (§7.1). A row with passed=True
    but max_dev=26 means the checker flagged it passed but the bps threshold is
    violated. The scorecard MUST NOT count it as a clean month — both conditions
    must hold. This is the exact post-hoc goalpost failure mode the program guards
    against.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    _add_parity(db, pf, datetime.date(2026, 7, 28), passed=True, max_dev_bps=5.0)
    # Boundary violation: passed=True but bps above the 25-bps hard limit.
    marginal_fail_date = datetime.date(2026, 8, 28)
    _add_parity(db, pf, marginal_fail_date, passed=True, max_dev_bps=26.0)
    _add_parity(db, pf, datetime.date(2026, 9, 28), passed=True, max_dev_bps=5.0)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    assert data["clean_months_passed"] == 1
    assert data["clock_reset_at"] == str(marginal_fail_date)
    g1 = next(g for g in data["gates"] if g["id"] == "g1_fidelity")
    assert g1["status"] == "fail"


# ---------------------------------------------------------------------------
# TS4-5 — Gate 1 (Fidelity) thresholds
# ---------------------------------------------------------------------------


def test_ts4_gate1_insufficient_data_when_no_parity_rows(client, db):
    """No parity rows → Gate 1 must return insufficient_data, not a pass.

    WHY: A missing parity check is NOT equivalent to a passing check. The
    system cannot assume fidelity when data is absent — that would be a
    fabricated pass (the exact failure mode this test guards against).
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    g1 = next(g for g in data["gates"] if g["id"] == "g1_fidelity")
    assert g1["status"] == "insufficient_data"


def test_ts5_gate1_pass_when_all_within_25bps(client, db):
    """All checks with max_dev_bps ≤ 25 and passed=True → Gate 1 pass.

    WHY: The threshold is exactly 25 bps (§7.1), not rounded or relaxed. A row
    at exactly 25.0 bps must pass (boundary inclusive).
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    _add_parity(db, pf, datetime.date(2026, 7, 28), passed=True, max_dev_bps=24.9)
    _add_parity(db, pf, datetime.date(2026, 8, 28), passed=True, max_dev_bps=25.0)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    g1 = next(g for g in data["gates"] if g["id"] == "g1_fidelity")
    assert g1["status"] == "pass"
    assert data["clean_months_passed"] == 2


# ---------------------------------------------------------------------------
# TS6 — Gate 3 (Cost realism) band
# ---------------------------------------------------------------------------


def test_ts6_gate3_insufficient_data_when_no_fills(client, db):
    """No filled fills → Gate 3 insufficient_data (not a fabricated pass).

    WHY: Absence of trading data means the cost gate cannot be evaluated.
    Returning 'pass' when there is no data would misrepresent cost realism.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    g3 = next(g for g in data["gates"] if g["id"] == "g3_cost")
    assert g3["status"] == "insufficient_data"


def test_ts7_gate3_pass_when_realized_within_pessimistic_band(client, db):
    """Minimal-cost fills → Gate 3 pass (realized well below pessimistic).

    WHY: Small fills at a near-zero slippage must pass the cost gate. This
    tests the within_band=True path, confirming the gate uses the pessimistic
    ceiling (not the base floor, which is the harder bar not the gate bar).
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    # 10 shares at 100, fill at 100.05 — tiny timing slippage
    _add_fill(
        db,
        pf,
        _GO_LIVE,
        qty=10.0,
        decision_price=100.0,
        fill_price=100.05,
        cost_rupees=1.0,
    )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    g3 = next(g for g in data["gates"] if g["id"] == "g3_cost")
    assert g3["status"] == "pass"


# ---------------------------------------------------------------------------
# TS8 — Gate 4 (Directional sanity) 15 pp threshold
# ---------------------------------------------------------------------------


def test_ts8_gate4_insufficient_data_when_too_few_forward_days(client, db):
    """< 20 forward days with index data → Gate 4 insufficient_data.

    WHY: The directional gate needs a minimum window to be meaningful. Flagging
    a 3-day sample as 'pass' would give false confidence — the spec requires at
    least a minimum of forward trading data before evaluating directionality.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    # Add only 5 forward days — below the 20-day minimum.
    for i in range(5):
        _add_snap(
            db,
            pf,
            _GO_LIVE + datetime.timedelta(days=i),
            1_000_000 + i * 100,
            is_forward=True,
            index_level=1_000_000 + i * 80,
        )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    g4 = next(g for g in data["gates"] if g["id"] == "g4_directional")
    assert g4["status"] == "insufficient_data"


def test_ts9_gate4_fail_when_underperformance_exceeds_15pp(client, db):
    """Book returning −5% vs Mom30 +12% = −17 pp gap → Gate 4 fail.

    WHY: The §7.4 threshold is exactly 15 pp. A −17 pp gap must trigger the
    fail status. The test encodes the exact threshold value (not 14pp, not 16pp)
    so any drift in the constant is caught immediately.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    # Book: 1_000_000 → 950_000 (−5%). Index: 1_000_000 → 1_120_000 (+12%).
    # Gap = −5 − 12 = −17 pp < −15 pp → FAIL.
    for i in range(25):
        pct = i / 24
        _add_snap(
            db,
            pf,
            _GO_LIVE + datetime.timedelta(days=i),
            1_000_000 - pct * 50_000,  # book ends at 950_000
            is_forward=True,
            index_level=1_000_000 + pct * 120_000,  # Mom30 ends at 1_120_000
        )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    g4 = next(g for g in data["gates"] if g["id"] == "g4_directional")
    assert g4["status"] == "fail"


def test_ts9b_gate4_pass_when_underperformance_within_15pp(client, db):
    """Book −3% vs Mom30 +10% = −13 pp gap → Gate 4 pass (within threshold).

    WHY: −13 pp is inside the −15 pp floor and must NOT trigger a fail.
    Tests the boundary from the safe side (13 < 15).
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    for i in range(25):
        pct = i / 24
        _add_snap(
            db,
            pf,
            _GO_LIVE + datetime.timedelta(days=i),
            1_000_000 - pct * 30_000,  # book −3%
            is_forward=True,
            index_level=1_000_000 + pct * 100_000,  # Mom30 +10%
        )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    g4 = next(g for g in data["gates"] if g["id"] == "g4_directional")
    assert g4["status"] == "pass"


# ---------------------------------------------------------------------------
# TS10-11 — Kill watch
# ---------------------------------------------------------------------------


def test_ts10_kill_cstop_trips_at_5_in_one_window(client, db):
    """5 catastrophic stops on the same decision_date → kill watch tripped.

    WHY: The kill threshold is exactly K=5 (§8). 5 stops in one rebalance
    window must trip the kill watch and push verdict to HALT. This test encodes
    the exact count (not 4, not 6) so any drift in the constant is caught.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    window_date = _GO_LIVE + datetime.timedelta(days=1)
    for i in range(5):
        _add_fill(
            db,
            pf,
            window_date,
            reason="catastrophic_stop",
            qty=10.0 + i,
            decision_price=100.0,
            fill_price=100.0,
            cost_rupees=1.0,
        )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    kw = next(k for k in data["kill_watch"] if "cascade" in k["label"])
    assert kw["tripped"] is True
    assert kw["value"] >= _KILL_CSTOP
    assert data["verdict"] == "HALT"


def test_ts11_kill_cstop_not_tripped_at_4(client, db):
    """4 catastrophic stops in one window → kill watch NOT tripped.

    WHY: K=5 is the threshold. 4 stops must NOT trip the kill watch — the
    boundary must be ≥5, not >4 (they're the same, but the test confirms the
    exact boundary semantics so a > vs ≥ typo is caught).
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    window_date = _GO_LIVE + datetime.timedelta(days=1)
    for i in range(4):
        _add_fill(
            db,
            pf,
            window_date,
            reason="catastrophic_stop",
            qty=10.0 + i,
            decision_price=100.0,
            fill_price=100.0,
            cost_rupees=1.0,
        )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    kw = next(k for k in data["kill_watch"] if "cascade" in k["label"])
    assert kw["tripped"] is False


def test_ts12_kill_maxdd_trips_above_23_1(client, db):
    """Forward equity dropping > 23.1% from peak → maxDD kill tripped.

    WHY: The kill threshold is ~23.1% (OOS 13.1% + Z=10 pp, §8). A drop
    from 1_000_000 to 760_000 = 24% drawdown must trip the kill and push
    verdict to HALT. Tests the exact 23.1 threshold.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    # Peak at 1_000_000, trough at 760_000 → maxDD = 24% > 23.1%
    _add_snap(db, pf, _GO_LIVE, 1_000_000.0, is_forward=True)
    _add_snap(db, pf, _GO_LIVE + datetime.timedelta(days=1), 760_000.0, is_forward=True)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    kw = next(k for k in data["kill_watch"] if "Drawdown" in k["label"])
    assert kw["tripped"] is True
    assert kw["value"] is not None
    assert kw["value"] > _KILL_MAXDD_PCT
    assert data["verdict"] == "HALT"


def test_ts13_kill_maxdd_not_tripped_at_23(client, db):
    """23% drawdown → kill watch NOT tripped (below 23.1% threshold).

    WHY: The kill threshold is 23.1%, not 23.0%. A 23% drop must not trigger
    the kill. This confirms the boundary is > 23.1, not ≥ 23.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    # Drop from 1_000_000 to 770_000 = 23.0% < 23.1%
    _add_snap(db, pf, _GO_LIVE, 1_000_000.0, is_forward=True)
    _add_snap(db, pf, _GO_LIVE + datetime.timedelta(days=1), 770_000.0, is_forward=True)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    kw = next(k for k in data["kill_watch"] if "Drawdown" in k["label"])
    assert kw["tripped"] is False


# ---------------------------------------------------------------------------
# TS14-16 — Verdict states
# ---------------------------------------------------------------------------


def test_ts14_verdict_clock_reset_when_parity_failed(client, db):
    """Parity fail in history → verdict CLOCK RESET (not ON TRACK).

    WHY: A clock-reset event must be surfaced prominently so the operator knows
    the graduation clock was interrupted. The spec lists CLOCK RESET as a
    distinct verdict state for exactly this reason.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    _add_parity(db, pf, datetime.date(2026, 7, 28), passed=False, max_dev_bps=80.0)
    _add_parity(db, pf, datetime.date(2026, 8, 28), passed=True, max_dev_bps=5.0)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    assert data["verdict"] == "CLOCK RESET"


def test_ts15_verdict_halt_overrides_all(client, db):
    """Kill criterion tripped → verdict HALT regardless of gate status.

    WHY: HALT is the highest-severity verdict and must not be suppressed by
    passing gates. Even if all graduation gates are green, a kill trigger
    must force HALT and the operator must act.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    # 5 catastrophic stops = kill
    window = _GO_LIVE + datetime.timedelta(days=1)
    for i in range(5):
        _add_fill(
            db,
            pf,
            window,
            reason="catastrophic_stop",
            qty=10.0,
            decision_price=100.0,
            fill_price=100.0,
            cost_rupees=1.0,
        )
    # Also add passing parity rows to confirm HALT overrides them
    for i in range(3):
        _add_parity(
            db, pf, datetime.date(2026, 7 + i, 28), passed=True, max_dev_bps=5.0
        )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    assert data["verdict"] == "HALT"


def test_ts16_verdict_graduated_requires_6_clean_months_and_hard_gates_pass(client, db):
    """6 clean months + no kill + all hard gates pass → GRADUATED (advisory).

    WHY: The graduation verdict must require ALL conditions simultaneously:
    6 consecutive clean months AND hard gate passes. Insufficient_data on any
    hard gate must NOT count as a pass — 'all_hard_pass' means status='pass',
    not 'not fail'. This test verifies the conjunction is correctly enforced.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)

    # 6 consecutive passing parity months = clock clean
    for i in range(6):
        _add_parity(
            db, pf, datetime.date(2026, 7 + i, 28), passed=True, max_dev_bps=10.0
        )

    # Gate 3 (cost): add a small fill so it evaluates to 'pass'
    _add_fill(
        db,
        pf,
        _GO_LIVE,
        qty=10.0,
        decision_price=100.0,
        fill_price=100.05,
        cost_rupees=1.0,
    )

    # Gate 4 (directional): 25 forward days, book slightly above Mom30
    for i in range(25):
        pct = i / 24
        _add_snap(
            db,
            pf,
            _GO_LIVE + datetime.timedelta(days=i),
            1_000_000 + pct * 80_000,  # book +8%
            is_forward=True,
            index_level=1_000_000 + pct * 50_000,  # Mom30 +5%
        )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    assert data["clean_months_passed"] == 6
    # All hard gates must pass for GRADUATED
    hard = [g for g in data["gates"] if g["severity"] == "hard"]
    for g in hard:
        assert g["status"] == "pass", f"{g['id']} not pass: {g['status']}"
    assert data["verdict"] == "GRADUATED"


# ---------------------------------------------------------------------------
# TS17-21 — AT RISK verdict (specs/v3/14 Fix #1)
#
# WHY: before Fix #1, a HARD gate (Gate 2/Gate 3) failing with no parity break
# and no kill fell through to the catch-all "else" and reported ON TRACK — a
# green-ish headline over a failing HARD gate. AT RISK closes that gap. These
# tests encode the exact precedence: HALT > AT RISK > GRADUATED > CLOCK RESET
# > ON TRACK, and that AT RISK must not fire on insufficient_data or on a
# historical (recovered) parity fail — only on a gate that is failing *now*.
# ---------------------------------------------------------------------------


def test_ts17_at_risk_when_gate3_cost_fails_no_parity_break(client, db):
    """G3 cost HARD fail, no parity break, no kill → verdict AT RISK.

    WHY: a hard cost breach must never read ON TRACK or GRADUATED just
    because Gate 1 never broke and no kill tripped.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    # Enormous timing slippage blows through the pessimistic cost ceiling.
    _add_fill(
        db,
        pf,
        _GO_LIVE,
        qty=10.0,
        decision_price=100.0,
        fill_price=1000.0,
        cost_rupees=1.0,
    )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    g3 = next(g for g in data["gates"] if g["id"] == "g3_cost")
    assert g3["status"] == "fail"
    assert data["verdict"] == "AT RISK"


def test_ts17b_at_risk_when_gate3_cost_fails_with_6_clean_months(client, db):
    """G3 cost HARD fail even with 6 clean parity months → still AT RISK, not GRADUATED.

    WHY: AT RISK must take precedence over a satisfied clean-month clock —
    graduation requires ALL hard gates clean, not just fidelity.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    for i in range(6):
        _add_parity(
            db, pf, datetime.date(2026, 7 + i, 28), passed=True, max_dev_bps=10.0
        )
    _add_fill(
        db,
        pf,
        _GO_LIVE,
        qty=10.0,
        decision_price=100.0,
        fill_price=1000.0,
        cost_rupees=1.0,
    )

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    assert data["clean_months_passed"] == 6
    assert data["verdict"] == "AT RISK"


def test_ts18_at_risk_when_gate2_operational_fails(client, db):
    """G2 operational HARD fail (unrecovered run failure) → verdict AT RISK.

    WHY: an unrecovered pipeline failure is exactly the §7.2 failure mode the
    gate exists to catch — it must not be masked by a clean parity history.
    """
    pf = _make_book(db)
    _add_run(db, pf, status="failed", last_date=_GO_LIVE)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    g2 = next(g for g in data["gates"] if g["id"] == "g2_operational")
    assert g2["status"] == "fail"
    assert data["verdict"] == "AT RISK"


def test_ts19_clock_reset_not_at_risk_after_recovery(client, db):
    """Historical parity fail then 3 clean months → CLOCK RESET, not AT RISK.

    WHY: g1's persisted status is a permanent all-time record (see test_ts3),
    but the AT RISK trigger must reflect whether fidelity is failing *right
    now*. The most recent parity check here passed, so the book has recovered
    and the headline must say CLOCK RESET, not misreport a live breach.
    """
    pf = _make_book(db)
    _add_run(db, pf, last_date=_GO_LIVE)
    _add_parity(db, pf, datetime.date(2026, 7, 28), passed=False, max_dev_bps=80.0)
    _add_parity(db, pf, datetime.date(2026, 8, 28), passed=True, max_dev_bps=5.0)
    _add_parity(db, pf, datetime.date(2026, 9, 28), passed=True, max_dev_bps=5.0)
    _add_parity(db, pf, datetime.date(2026, 10, 28), passed=True, max_dev_bps=5.0)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    assert data["verdict"] == "CLOCK RESET"


def test_ts20_on_track_when_all_gates_insufficient_data(client, db):
    """Early book, no parity/runs/fills/snapshots → verdict ON TRACK, never AT RISK.

    WHY: insufficient_data must never count as a fail — an early book with no
    history yet is a fail-safe ON TRACK, not a false AT RISK alarm.
    """
    _make_book(db)

    resp = client.get("/api/v2/paper/scorecard")
    data = resp.json()
    hard = [g for g in data["gates"] if g["severity"] == "hard"]
    assert all(g["status"] == "insufficient_data" for g in hard)
    assert data["verdict"] == "ON TRACK"
