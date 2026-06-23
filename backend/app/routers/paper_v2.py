"""Read-only API for the v2 S3 probation paper book (specs/v3/11).

Surfaces the frozen forward paper book to the frontend. **Strictly read-only:**
the S3 probation is a frozen experiment (``11`` §1 — every knob frozen for the
6-month window), so this router exposes NO write endpoints (no manual entry, no
close). Every figure is derived from persisted book/position state — in
particular the ``last_price`` stored at the last daily MTM — so the endpoints
never fetch a live price (project law: never hit live NSE/yfinance).

Per project law (§2 Pydantic Enforcement) the responses are validated Pydantic
models, unlike the older ``paper_trading`` router which predates that rule.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import PaperV2Portfolio, PaperV2Position
from app.db.session import get_db

router = APIRouter(prefix="/v2/paper", tags=["paper-v2"])

_IST = ZoneInfo("Asia/Kolkata")


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
