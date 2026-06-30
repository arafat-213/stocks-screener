"""API for the v2 S3 probation paper book (specs/v3/11).

Surfaces the frozen forward paper book to the frontend, plus pipeline
status/trigger endpoints for the System page. The book view is read-only
(S3 probation is a frozen experiment — no manual entry, no close). The
pipeline endpoints allow manual triggering of the daily post-close job via
the System UI (replaces the retired v1 pipeline trigger).

Per project law (§2 Pydantic Enforcement) the responses are validated Pydantic
models, unlike the older ``paper_trading`` router which predates that rule.
"""

from __future__ import annotations

import datetime
import logging
from zoneinfo import ZoneInfo

import redis as _redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backtest_v2.costs import CostConfig, effective_price, fill_cost
from app.core.celery_app import redis_url
from app.db.models import (
    PaperV2Alert,
    PaperV2DailySnapshot,
    PaperV2ParityCheck,
    PaperV2PendingFill,
    PaperV2Portfolio,
    PaperV2Position,
    PaperV2Run,
)
from app.db.session import get_db
from app.paper_v2.s3_config import S3_EXPECTED_TURNOVER_TWO_WAY_PCT

router = APIRouter(prefix="/v2/paper", tags=["paper-v2"])

_IST = ZoneInfo("Asia/Kolkata")
_log = logging.getLogger(__name__)

# Must stay in sync with tasks.py — the same lock key the Celery task uses.
_PAPER_LOCK_KEY = "paper_daily_task_running"


class PaperV2BookResponse(BaseModel):
    """Book-level header for the S3 probation: NAV, cash and replay freshness."""

    name: str
    is_active: bool
    starting_capital: float
    cash: float
    holdings_value: float  # Σ shares × last_price (MTM, from DB — no live fetch)
    nav: float  # cash + holdings_value
    total_return_pct: float  # (nav − starting_capital) / starting_capital × 100
    n_positions: int
    # The replay clock (11 §4c): last trading day whose daily post-close job ran.
    last_processed_date: datetime.date | None
    # IST date the book was created — the P11.2 forward-window anchor (11 §6).
    go_live_date: datetime.date | None


class PaperV2PositionResponse(BaseModel):
    """One open S3 holding, MTM-valued at the last stored close."""

    isin: str
    symbol: str
    shares: float
    cost_basis: float  # avg cost per share, incl. fees (backtest_v2 Position)
    last_price: float | None  # close_tr at last MTM
    market_value: float  # shares × last_price
    unrealized_pct: float | None  # (last_price − cost_basis) / cost_basis × 100
    weight_pct: float | None  # market_value / nav × 100
    entry_date: datetime.date
    days_held: int
    rank: int | None
    composite_score: float | None
    target_weight: float | None
    regime_state_at_entry: str | None


def _active_book(db: Session) -> PaperV2Portfolio | None:
    """The single active S3 probation book (11 §1 — there is exactly one)."""
    return db.query(PaperV2Portfolio).filter_by(is_active=True).first()


def _holdings_value(positions: list[PaperV2Position]) -> float:
    """MTM holdings value from stored ``last_price`` (treats a missing MTM as 0)."""
    return sum(p.shares * (p.last_price or 0.0) for p in positions)


@router.get("/book", response_model=PaperV2BookResponse)
def get_book(db: Session = Depends(get_db)) -> PaperV2BookResponse:
    book = _active_book(db)
    if not book:
        raise HTTPException(
            status_code=404,
            detail="No active S3 probation book. The 11 forward run is not armed.",
        )

    positions = db.query(PaperV2Position).filter_by(portfolio_id=book.id).all()
    holdings_value = _holdings_value(positions)
    nav = book.cash + holdings_value
    total_return_pct = (
        (nav - book.starting_capital) / book.starting_capital * 100.0
        if book.starting_capital
        else 0.0
    )
    go_live = book.created_at.astimezone(_IST).date() if book.created_at else None

    return PaperV2BookResponse(
        name=book.name,
        is_active=book.is_active,
        starting_capital=book.starting_capital,
        cash=book.cash,
        holdings_value=holdings_value,
        nav=nav,
        total_return_pct=total_return_pct,
        n_positions=len(positions),
        last_processed_date=book.last_processed_date,
        go_live_date=go_live,
    )


@router.get("/positions", response_model=list[PaperV2PositionResponse])
def get_positions(db: Session = Depends(get_db)) -> list[PaperV2PositionResponse]:
    book = _active_book(db)
    if not book:
        return []

    positions = db.query(PaperV2Position).filter_by(portfolio_id=book.id).all()
    holdings_value = _holdings_value(positions)
    nav = book.cash + holdings_value

    out = []
    for p in positions:
        market_value = p.shares * (p.last_price or 0.0)
        unrealized_pct = (
            (p.last_price - p.cost_basis) / p.cost_basis * 100.0
            if p.last_price is not None and p.cost_basis
            else None
        )
        weight_pct = (market_value / nav * 100.0) if nav else None
        out.append(
            PaperV2PositionResponse(
                isin=p.isin,
                symbol=p.symbol,
                shares=p.shares,
                cost_basis=p.cost_basis,
                last_price=p.last_price,
                market_value=market_value,
                unrealized_pct=unrealized_pct,
                weight_pct=weight_pct,
                entry_date=p.entry_date,
                days_held=p.days_held,
                rank=p.rank,
                composite_score=p.composite_score,
                target_weight=p.target_weight,
                regime_state_at_entry=p.regime_state_at_entry,
            )
        )

    # Largest holding first (most intuitive for a read-only book view).
    out.sort(key=lambda r: r.market_value, reverse=True)
    return out


# ---------------------------------------------------------------------------
# V11.3 — NAV curve, parity history, rebalance log (all read-only, persisted state)
# ---------------------------------------------------------------------------


class NavPointResponse(BaseModel):
    """One persisted daily NAV snapshot (paper_v2_daily_snapshot, V11.1)."""

    date: datetime.date
    equity: float  # book NAV: cash + Σ shares·close_tr
    cash: float
    invested_value: float
    exposure: float  # invested_value / equity (0–1) — risk-on/off proxy
    n_positions: int
    index_level: float | None  # Nifty200 Mom30 TRI close (None on a gap)
    # Benchmark rebased to the book's starting capital so the FE overlays book-NAV vs
    # index on one axis without client math (anchored to the first non-null index level).
    index_rebased: float | None
    is_forward: bool  # date >= go_live (warm-start replay vs counted forward)


class NavSeriesResponse(BaseModel):
    """The NAV curve envelope: the go-live divider + ascending points (one source of
    truth for where warm-start replay ends and the counted forward window begins)."""

    go_live_date: datetime.date | None
    points: list[NavPointResponse]


class ParityCheckResponse(BaseModel):
    """One persisted monthly shadow-parity check (paper_v2_parity_check, V11.2)."""

    as_of: datetime.date
    passed: bool
    max_dev_bps: float
    tol_bps: float
    breaches: list[tuple[str, float]]  # (isin, dev_bps)


class ParitySeriesResponse(BaseModel):
    latest: ParityCheckResponse | None  # max as_of — drives the header fidelity badge
    history: list[ParityCheckResponse]  # ascending by as_of


class RebalanceFillResponse(BaseModel):
    """One fill within a rebalance/stop event (from paper_v2_pending_fills)."""

    symbol: str
    isin: str
    side: str  # buy | sell | trim
    qty: float
    # Pre-trade holding the fill acts on (shares held before it applies; 0 = fresh
    # entry). Lets the FE render "holding (Δ)": a trim shows "10 (-2)", a full exit
    # "25 (-25)". Nullable for legacy rows queued before this field existed.
    holding_before: float | None
    reason: str  # rebalance | catastrophic_stop | force_exit
    status: str  # pending | filled
    decision_price: float | None
    fill_date: datetime.date | None
    fill_price: float | None
    cost_rupees: float | None


class RebalanceEventResponse(BaseModel):
    """All fills queued on one decision date, grouped into a single event."""

    decision_date: datetime.date
    reason: (
        str  # rebalance | catastrophic_stop | force_exit (precedence in get_rebalances)
    )
    # Regime overlay's deployable fraction on the decision day (1.0 = risk-on; lower =
    # risk-off / scaled-out). Lets the FE badge a regime-driven risk-off rebalance.
    # Nullable for legacy rows.
    deployable_fraction: float | None
    n_buys: int
    n_sells: int
    n_trims: int
    total_cost_rupees: float
    fills: list[RebalanceFillResponse]


@router.get("/nav", response_model=NavSeriesResponse)
def get_nav(db: Session = Depends(get_db)) -> NavSeriesResponse:
    """Full since-inception NAV curve + benchmark overlay (V11.1/V11.3)."""
    book = _active_book(db)
    if not book:
        return NavSeriesResponse(go_live_date=None, points=[])

    rows = (
        db.query(PaperV2DailySnapshot)
        .filter_by(portfolio_id=book.id)
        .order_by(PaperV2DailySnapshot.date.asc())
        .all()
    )
    go_live = book.created_at.astimezone(_IST).date() if book.created_at else None

    # Rebase anchor = the earliest snapshot carrying a non-null index level.
    anchor = next((r.index_level for r in rows if r.index_level is not None), None)
    points = [
        NavPointResponse(
            date=r.date,
            equity=r.equity,
            cash=r.cash,
            invested_value=r.invested_value,
            exposure=r.exposure,
            n_positions=r.n_positions,
            index_level=r.index_level,
            index_rebased=(
                r.index_level / anchor * book.starting_capital
                if r.index_level is not None and anchor
                else None
            ),
            is_forward=r.is_forward,
        )
        for r in rows
    ]
    return NavSeriesResponse(go_live_date=go_live, points=points)


@router.get("/parity", response_model=ParitySeriesResponse)
def get_parity(db: Session = Depends(get_db)) -> ParitySeriesResponse:
    """Monthly shadow-parity history + latest (V11.2/V11.3)."""
    book = _active_book(db)
    if not book:
        return ParitySeriesResponse(latest=None, history=[])

    rows = (
        db.query(PaperV2ParityCheck)
        .filter_by(portfolio_id=book.id)
        .order_by(PaperV2ParityCheck.as_of.asc())
        .all()
    )

    def _to_resp(r: PaperV2ParityCheck) -> ParityCheckResponse:
        return ParityCheckResponse(
            as_of=r.as_of,
            passed=r.passed,
            max_dev_bps=r.max_dev_bps,
            tol_bps=r.tol_bps,
            breaches=[(isin, dev) for isin, dev in (r.breaches or [])],
        )

    history = [_to_resp(r) for r in rows]
    return ParitySeriesResponse(
        latest=history[-1] if history else None, history=history
    )


@router.get("/rebalances", response_model=list[RebalanceEventResponse])
def get_rebalances(db: Session = Depends(get_db)) -> list[RebalanceEventResponse]:
    """Rebalance/stop log grouped by decision date (V11.3), newest first. Reads the
    pending-fills queue — no new table."""
    book = _active_book(db)
    if not book:
        return []

    fills = (
        db.query(PaperV2PendingFill)
        .filter_by(portfolio_id=book.id)
        .order_by(PaperV2PendingFill.decision_date.asc(), PaperV2PendingFill.id.asc())
        .all()
    )

    # Group by decision_date preserving insertion order within a date.
    grouped: dict[datetime.date, list[PaperV2PendingFill]] = {}
    for f in fills:
        grouped.setdefault(f.decision_date, []).append(f)

    events: list[RebalanceEventResponse] = []
    for decision_date, group in grouped.items():
        # Event-level reason by precedence: a rebalance can co-occur with a same-day
        # force-exit or stop, so the headline reflects the most significant action —
        # rebalance > catastrophic_stop > force_exit. Individual fills keep their own
        # reason badge.
        reasons = {f.reason for f in group}
        if "rebalance" in reasons:
            reason = "rebalance"
        elif "catastrophic_stop" in reasons:
            reason = "catastrophic_stop"
        else:
            reason = "force_exit"
        # Regime fraction is a per-day property; take it from any fill carrying one.
        deployable_fraction = next(
            (f.deployable_fraction for f in group if f.deployable_fraction is not None),
            None,
        )
        events.append(
            RebalanceEventResponse(
                decision_date=decision_date,
                reason=reason,
                deployable_fraction=deployable_fraction,
                n_buys=sum(1 for f in group if f.side == "buy"),
                n_sells=sum(1 for f in group if f.side == "sell"),
                n_trims=sum(1 for f in group if f.side == "trim"),
                total_cost_rupees=sum(f.cost_rupees or 0.0 for f in group),
                fills=[
                    RebalanceFillResponse(
                        symbol=f.symbol,
                        isin=f.isin,
                        side=f.side,
                        qty=f.qty,
                        holding_before=f.holding_before,
                        reason=f.reason,
                        status=f.status,
                        decision_price=f.decision_price,
                        fill_date=f.fill_date,
                        fill_price=f.fill_price,
                        cost_rupees=f.cost_rupees,
                    )
                    for f in group
                ],
            )
        )

    # Newest decision_date first.
    events.sort(key=lambda e: e.decision_date, reverse=True)
    return events


# ---------------------------------------------------------------------------
# S3 Paper Pipeline — status + manual trigger (System UI, replaces retired v1)
# ---------------------------------------------------------------------------


class PaperPipelineStatusResponse(BaseModel):
    """Runtime status of the S3 daily post-close paper job."""

    status: str  # "running" | "idle" | "never_run"
    last_processed_date: datetime.date | None
    go_live_date: datetime.date | None


@router.get("/pipeline/status", response_model=PaperPipelineStatusResponse)
def get_paper_pipeline_status(
    db: Session = Depends(get_db),
) -> PaperPipelineStatusResponse:
    """Current status of the S3 daily post-close paper engine.

    ``status`` reflects the Redis advisory lock (same key the Celery task holds):
    *  ``running``   — lock is held (task is in progress)
    *  ``idle``      — lock free, book exists and has been processed at least once
    *  ``never_run`` — no active book or ``last_processed_date`` is None
    """
    r = _redis.from_url(redis_url)
    is_running = r.exists(_PAPER_LOCK_KEY) == 1

    book = _active_book(db)
    go_live = (
        book.created_at.astimezone(_IST).date() if book and book.created_at else None
    )

    if is_running:
        return PaperPipelineStatusResponse(
            status="running",
            last_processed_date=book.last_processed_date if book else None,
            go_live_date=go_live,
        )

    if book is None or book.last_processed_date is None:
        return PaperPipelineStatusResponse(
            status="never_run",
            last_processed_date=None,
            go_live_date=go_live,
        )

    return PaperPipelineStatusResponse(
        status="idle",
        last_processed_date=book.last_processed_date,
        go_live_date=go_live,
    )


@router.post("/pipeline/run", status_code=202)
def run_paper_pipeline(db: Session = Depends(get_db)) -> dict:
    """Manually trigger the S3 daily post-close paper job via Celery.

    Returns 409 if the job is already running (Redis lock held). The task
    processes all unprocessed trading days up to today in ordered-replay
    fashion (tasks.py ``execute_paper_daily_task``).
    """
    from app.tasks import execute_paper_daily_task

    r = _redis.from_url(redis_url)
    if r.exists(_PAPER_LOCK_KEY):
        raise HTTPException(
            status_code=409, detail="S3 paper pipeline is already running"
        )

    _log.info("Manual S3 paper pipeline trigger via System UI")
    execute_paper_daily_task.delay(trigger="manual")
    return {"message": "S3 paper pipeline task queued"}


# ---------------------------------------------------------------------------
# F2 — Realized-vs-modeled cost ledger (specs/v3/12 F2)
# ---------------------------------------------------------------------------


class CostLedgerRowResponse(BaseModel):
    """Per-rebalance-event row in the cost ledger."""

    decision_date: datetime.date
    reason: str  # rebalance | catastrophic_stop | force_exit
    traded_notional: float  # Σ qty × fill_price for filled fills in this event
    realized_cost_rupees: float  # statutory (cost_rupees) + timing slippage
    realized_bps: float  # realized_cost_rupees / traded_notional × 10 000
    modeled_base_bps: float  # base CostConfig band (lower edge)
    modeled_pess_bps: float  # pessimistic CostConfig band (upper edge)


class CostLedgerResponse(BaseModel):
    """Cumulative realized-vs-modeled cost ledger for the S3 probation (F2)."""

    realized_bps_total: float
    realized_drag_pct_yr: float  # annualized by forward elapsed days
    modeled_base_bps: float  # cumulative base band in bps of total traded notional
    modeled_pessimistic_bps: float
    within_band: bool  # realized_bps_total ≤ modeled_pessimistic_bps (§2.3 gate)
    rows: list[CostLedgerRowResponse]


def _compute_modeled_cost(
    side: str,
    qty: float,
    fill_price: float,
    cfg: CostConfig,
) -> float:
    """Total modeled cost for one fill: statutory (fill_cost) + slippage impact.

    adv_20=0 → effective_price uses base_slippage_pct floor only (no participation
    component), since paper fills have no stored ADV. This matches the paper-fill
    caveat (specs/v3/12 §1.4): slippage here is impact-model slippage, not timing.
    """
    stat = fill_cost(side, qty, fill_price, 0.0, cfg)
    slipped_px = effective_price(side, fill_price, qty, 0.0, cfg)
    slip_cost = abs(slipped_px - fill_price) * qty
    return stat + slip_cost


@router.get("/cost-ledger", response_model=CostLedgerResponse)
def get_cost_ledger(db: Session = Depends(get_db)) -> CostLedgerResponse:
    """Realized vs modeled cost band for the S3 probation book (F2, specs/v3/12).

    Realized cost = Σ statutory cost_rupees + timing slippage (|fill − decision| × qty)
    for all *filled* fills (pending fills haven't executed and are excluded).
    Modeled band reuses costs.py fill_cost / effective_price at base and pessimistic
    CostConfig levels — no formula is re-derived here (specs/v3/12 §2.4 Rule 5).
    Annualisation uses forward elapsed days from paper_v2_daily_snapshot.
    """
    _empty = CostLedgerResponse(
        realized_bps_total=0.0,
        realized_drag_pct_yr=0.0,
        modeled_base_bps=0.0,
        modeled_pessimistic_bps=0.0,
        within_band=True,
        rows=[],
    )
    book = _active_book(db)
    if not book:
        return _empty

    # Only filled fills contribute to realized cost — pending fills haven't executed.
    fills = (
        db.query(PaperV2PendingFill)
        .filter_by(portfolio_id=book.id, status="filled")
        .order_by(PaperV2PendingFill.decision_date.asc(), PaperV2PendingFill.id.asc())
        .all()
    )
    if not fills:
        return _empty

    # Forward elapsed days for annualisation (is_forward snapshots only; warm-start
    # replay days are excluded for the same reason the NAV curve divides at go-live).
    fwd_snaps = (
        db.query(PaperV2DailySnapshot)
        .filter_by(portfolio_id=book.id, is_forward=True)
        .all()
    )
    n_forward_days = len(fwd_snaps)
    avg_nav = (
        sum(s.equity for s in fwd_snaps) / n_forward_days
        if n_forward_days
        else book.starting_capital
    )

    cfg_base = CostConfig.base()
    cfg_pess = CostConfig.pessimistic()

    # Group by decision_date (same ordering as /rebalances).
    grouped: dict[datetime.date, list[PaperV2PendingFill]] = {}
    for f in fills:
        grouped.setdefault(f.decision_date, []).append(f)

    rows: list[CostLedgerRowResponse] = []
    total_notional = 0.0
    total_realized = 0.0
    total_base = 0.0
    total_pess = 0.0

    for decision_date, group in sorted(grouped.items()):
        # Event reason by precedence (mirrors /rebalances grouping logic).
        reasons = {f.reason for f in group}
        if "rebalance" in reasons:
            reason = "rebalance"
        elif "catastrophic_stop" in reasons:
            reason = "catastrophic_stop"
        else:
            reason = "force_exit"

        grp_notional = 0.0
        grp_realized = 0.0
        grp_base = 0.0
        grp_pess = 0.0

        for f in group:
            if f.fill_price is None or f.qty is None:
                continue  # malformed row — skip (should not happen for status=filled)
            notional = f.qty * f.fill_price
            grp_notional += notional

            # Realized = statutory (stored) + next-open-vs-decision-close timing slippage.
            statutory = f.cost_rupees or 0.0
            timing_slip = (
                abs(f.fill_price - f.decision_price) * f.qty
                if f.decision_price is not None
                else 0.0
            )
            grp_realized += statutory + timing_slip

            # Modeled = statutory + impact-model slippage via costs.py (Rule 5).
            grp_base += _compute_modeled_cost(f.side, f.qty, f.fill_price, cfg_base)
            grp_pess += _compute_modeled_cost(f.side, f.qty, f.fill_price, cfg_pess)

        realized_bps = (grp_realized / grp_notional * 10_000) if grp_notional else 0.0
        base_bps = (grp_base / grp_notional * 10_000) if grp_notional else 0.0
        pess_bps = (grp_pess / grp_notional * 10_000) if grp_notional else 0.0

        rows.append(
            CostLedgerRowResponse(
                decision_date=decision_date,
                reason=reason,
                traded_notional=grp_notional,
                realized_cost_rupees=grp_realized,
                realized_bps=realized_bps,
                modeled_base_bps=base_bps,
                modeled_pess_bps=pess_bps,
            )
        )
        total_notional += grp_notional
        total_realized += grp_realized
        total_base += grp_base
        total_pess += grp_pess

    realized_bps_total = (
        (total_realized / total_notional * 10_000) if total_notional else 0.0
    )
    modeled_base_bps = (total_base / total_notional * 10_000) if total_notional else 0.0
    modeled_pess_bps = (total_pess / total_notional * 10_000) if total_notional else 0.0

    # Drag = cumulative realized cost as annualised % of average forward NAV.
    realized_drag_pct_yr = (
        (total_realized / avg_nav) * (252.0 / n_forward_days) * 100.0
        if n_forward_days and avg_nav
        else 0.0
    )

    # Gate (specs/v3/12 §2.3): realized must not exceed the pessimistic band.
    within_band = total_realized <= total_pess

    return CostLedgerResponse(
        realized_bps_total=realized_bps_total,
        realized_drag_pct_yr=realized_drag_pct_yr,
        modeled_base_bps=modeled_base_bps,
        modeled_pessimistic_bps=modeled_pess_bps,
        within_band=within_band,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# F5 — Alert log (specs/v3/12 F5): persisted feed of all emitted alerts
# ---------------------------------------------------------------------------


class PaperAlertResponse(BaseModel):
    """One persisted alert row from ``paper_v2_alert`` (F5)."""

    id: int
    created_at: datetime.datetime
    kind: str  # stop | rebalance_preview | fill_confirm | pipeline_failure | staleness
    as_of: datetime.date | None
    subject: str
    body_summary: str
    delivered: bool


@router.get("/alerts", response_model=list[PaperAlertResponse])
def get_alerts(
    limit: int = 50,
    kind: str | None = None,
    db: Session = Depends(get_db),
) -> list[PaperAlertResponse]:
    """Persisted alert feed for the S3 probation book (F5). Most recent first.

    ``limit`` caps the number of rows returned (default 50). ``kind`` filters by
    alert kind (stop | rebalance_preview | fill_confirm | pipeline_failure | staleness).
    Read-only over ``paper_v2_alert``; no live fetch.
    """
    book = _active_book(db)
    if not book:
        return []

    q = (
        db.query(PaperV2Alert)
        .filter_by(portfolio_id=book.id)
        .order_by(PaperV2Alert.created_at.desc())
    )
    if kind is not None:
        q = q.filter(PaperV2Alert.kind == kind)
    rows = q.limit(limit).all()

    return [
        PaperAlertResponse(
            id=r.id,
            created_at=r.created_at,
            kind=r.kind,
            as_of=r.as_of,
            subject=r.subject,
            body_summary=r.body_summary,
            delivered=r.delivered,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# F3 — Turnover-to-date vs backtest expectation (specs/v3/12 F3)
# ---------------------------------------------------------------------------


class TurnoverResponse(BaseModel):
    """Live two-way turnover vs frozen S3 backtest expectation (F3, specs/v3/12).

    ``live_annualized_pct`` is two-way (buys + sells counted), annualized over forward
    elapsed days — the same convention as backtest_v2 metrics._compute_annualized_turnover.
    ``expected_pct`` is the frozen S3 FINAL_OOS figure from ``10`` R10.3 (base cost);
    it comes from ``S3_EXPECTED_TURNOVER_TWO_WAY_PCT`` in s3_config.py, not from a
    live backtest (read-only law + Rule 5).
    ``ratio`` > 1.0 means the live book is churning more than the frozen S3 predicts.
    """

    live_annualized_pct: float
    expected_pct: (
        float  # frozen from FINAL_OOS R10.3 via S3_EXPECTED_TURNOVER_TWO_WAY_PCT
    )
    ratio: float  # live / expected (0.0 when no forward fills yet)
    basis: str  # always "two-way"
    n_forward_days: int


@router.get("/turnover", response_model=TurnoverResponse)
def get_turnover(db: Session = Depends(get_db)) -> TurnoverResponse:
    """Live two-way turnover vs frozen S3 backtest expectation (F3, specs/v3/12).

    Live turnover = Σ|qty × fill_price| over *forward* filled fills (decision_date ≥
    go_live) / average forward NAV, annualized by forward trading days from
    paper_v2_daily_snapshot (is_forward=True).

    Expected turnover = S3_EXPECTED_TURNOVER_TWO_WAY_PCT (581 % two-way, frozen from
    ``10`` R10.3 FINAL_OOS). Read-only; no live price fetch; no formula re-derived.
    """
    _empty = TurnoverResponse(
        live_annualized_pct=0.0,
        expected_pct=S3_EXPECTED_TURNOVER_TWO_WAY_PCT,
        ratio=0.0,
        basis="two-way",
        n_forward_days=0,
    )
    book = _active_book(db)
    if not book:
        return _empty

    go_live = book.created_at.astimezone(_IST).date() if book.created_at else None

    # Forward trading days for annualisation (is_forward snapshots only — warm-start
    # replay days excluded for the same reason the NAV curve divides at go-live).
    fwd_snaps = (
        db.query(PaperV2DailySnapshot)
        .filter_by(portfolio_id=book.id, is_forward=True)
        .all()
    )
    n_forward_days = len(fwd_snaps)
    avg_nav = (
        sum(s.equity for s in fwd_snaps) / n_forward_days
        if n_forward_days
        else book.starting_capital
    )

    # Forward fills only: decision_date >= go_live excludes warm-start replay trades.
    # Pending fills haven't executed — only status=filled counts toward turnover.
    q = db.query(PaperV2PendingFill).filter_by(portfolio_id=book.id, status="filled")
    if go_live is not None:
        q = q.filter(PaperV2PendingFill.decision_date >= go_live)
    forward_fills = q.all()

    if not forward_fills or n_forward_days == 0:
        return TurnoverResponse(
            live_annualized_pct=0.0,
            expected_pct=S3_EXPECTED_TURNOVER_TWO_WAY_PCT,
            ratio=0.0,
            basis="two-way",
            n_forward_days=n_forward_days,
        )

    # Two-way notional: |qty × fill_price| for every forward fill (buys + sells).
    total_notional = sum(
        abs(f.qty * f.fill_price)
        for f in forward_fills
        if f.fill_price is not None and f.qty is not None
    )

    # Annualized two-way turnover as % of average NAV.
    live_annualized_pct = (
        (total_notional / avg_nav) * (252.0 / n_forward_days) * 100.0
        if avg_nav
        else 0.0
    )
    ratio = (
        live_annualized_pct / S3_EXPECTED_TURNOVER_TWO_WAY_PCT
        if S3_EXPECTED_TURNOVER_TWO_WAY_PCT
        else 0.0
    )

    return TurnoverResponse(
        live_annualized_pct=live_annualized_pct,
        expected_pct=S3_EXPECTED_TURNOVER_TWO_WAY_PCT,
        ratio=ratio,
        basis="two-way",
        n_forward_days=n_forward_days,
    )


# ---------------------------------------------------------------------------
# F4 — Pipeline heartbeat / run-history strip (specs/v3/12 F4)
# ---------------------------------------------------------------------------


class PaperRunResponse(BaseModel):
    """One persisted run record from ``paper_v2_run`` (F4).

    ``trigger`` is "beat" | "manual" | "backfill".
    ``status`` is "success" | "failed" | "noop" (noop = nothing left to process).
    ``days_processed`` is 0 for noop / pre-failure runs.
    ``error_class`` / ``error_msg`` are populated only on failed runs.
    """

    id: int
    started_at: datetime.datetime
    finished_at: datetime.datetime | None
    trigger: str
    status: str
    days_processed: int
    first_date: datetime.date | None
    last_date: datetime.date | None
    error_class: str | None
    error_msg: str | None


@router.get("/runs", response_model=list[PaperRunResponse])
def get_runs(
    limit: int = 30,
    db: Session = Depends(get_db),
) -> list[PaperRunResponse]:
    """Run history for the S3 paper pipeline (F4, specs/v3/12).

    Returns the most recent ``limit`` run records (default 30), newest first.
    Each row corresponds to one execute_paper_daily_task invocation that reached
    the book-setup stage (concurrent guard skips are never recorded).
    Read-only over ``paper_v2_run``; no live fetch.
    """
    book = _active_book(db)
    if not book:
        return []

    rows = (
        db.query(PaperV2Run)
        .filter_by(portfolio_id=book.id)
        .order_by(PaperV2Run.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        PaperRunResponse(
            id=r.id,
            started_at=r.started_at,
            finished_at=r.finished_at,
            trigger=r.trigger,
            status=r.status,
            days_processed=r.days_processed,
            first_date=r.first_date,
            last_date=r.last_date,
            error_class=r.error_class,
            error_msg=r.error_msg,
        )
        for r in rows
    ]
