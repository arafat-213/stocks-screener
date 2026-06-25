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

from app.core.celery_app import redis_url
from app.db.models import (
    PaperV2DailySnapshot,
    PaperV2ParityCheck,
    PaperV2PendingFill,
    PaperV2Portfolio,
    PaperV2Position,
)
from app.db.session import get_db

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
    execute_paper_daily_task.delay()
    return {"message": "S3 paper pipeline task queued"}
