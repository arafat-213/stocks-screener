import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.utils import sanitize_for_json
from app.db.models import PaperPortfolio, PaperPosition, PaperTrade
from app.db.session import get_db
from app.pipeline.ohlcv_cache import OHLCVCache

router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


@router.get("/portfolio")
def get_portfolio_summary(db: Session = Depends(get_db)):
    portfolio = db.query(PaperPortfolio).filter_by(is_active=True).first()
    if not portfolio:
        return {
            "status": "no_portfolio",
            "message": "No active paper portfolio. Run a pipeline cycle to initialise.",
        }

    closed_trades = db.query(PaperTrade).filter_by(portfolio_id=portfolio.id).all()
    open_positions = (
        db.query(PaperPosition)
        .filter_by(portfolio_id=portfolio.id, status="open")
        .all()
    )
    pending_orders = (
        db.query(PaperPosition)
        .filter_by(portfolio_id=portfolio.id, status="pending")
        .all()
    )

    total_pnl = sum(t.pnl for t in closed_trades)
    total_trades = len(closed_trades)
    wins = [t for t in closed_trades if t.return_pct > 0]
    losses = [t for t in closed_trades if t.return_pct <= 0]

    # Current open position value
    cache = OHLCVCache()
    unrealised_pnl = 0.0
    for pos in open_positions:
        df = cache.get(pos.symbol, period="1y")
        if df is not None and not df.empty:
            latest_close = float(df.iloc[-1]["Close"])
            unrealised_pnl += (latest_close - pos.entry_price) * pos.shares

    avg_win = sum(t.return_pct for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t.return_pct for t in losses) / len(losses) if losses else 0.0
    profit_factor = (
        (len(wins) * avg_win) / (len(losses) * abs(avg_loss))
        if losses and avg_loss != 0
        else 0.0
    )
    avg_holding = (
        round(
            sum((t.exit_date - t.entry_date).days for t in closed_trades) / total_trades
        )
        if total_trades
        else 0
    )

    result = {
        "portfolio_id": portfolio.id,
        "started_at": portfolio.created_at.isoformat(),
        "starting_capital": portfolio.starting_capital,
        "realised_pnl": round(total_pnl, 2),
        "unrealised_pnl": round(unrealised_pnl, 2),
        "total_return_pct": round(total_pnl / portfolio.starting_capital * 100, 2),
        "total_trades": total_trades,
        "open_positions": len(open_positions),
        "pending_orders": len(pending_orders),
        "win_rate": round(len(wins) / total_trades * 100, 2) if total_trades else 0,
        "avg_return_pct": round(
            sum(t.return_pct for t in closed_trades) / total_trades, 2
        )
        if total_trades
        else 0,
        "profit_factor": round(profit_factor, 2),
        "avg_holding_days": avg_holding,
    }
    return sanitize_for_json(result)


@router.get("/pending")
def get_pending_orders(db: Session = Depends(get_db)):
    portfolio = db.query(PaperPortfolio).filter_by(is_active=True).first()
    if not portfolio:
        return []

    pending = (
        db.query(PaperPosition)
        .filter_by(portfolio_id=portfolio.id, status="pending")
        .order_by(desc(PaperPosition.signal_date))
        .all()
    )

    result = [
        {
            "id": p.id,
            "symbol": p.symbol,
            "sector": p.sector,
            "signal_date": p.signal_date.isoformat(),
            "signal_score": p.signal_score,
            "ema_signal": p.ema_signal,
            "wait_days": p.wait_days_elapsed,
            "closeness_pct": round(p.pending_highest_closeness_pct, 2)
            if p.pending_highest_closeness_pct != 999.0
            else None,
        }
        for p in pending
    ]
    return sanitize_for_json(result)


@router.get("/positions")
def get_open_positions(db: Session = Depends(get_db)):
    portfolio = db.query(PaperPortfolio).filter_by(is_active=True).first()
    if not portfolio:
        return []

    positions = (
        db.query(PaperPosition)
        .filter_by(portfolio_id=portfolio.id, status="open")
        .order_by(desc(PaperPosition.entry_date))
        .all()
    )

    cache = OHLCVCache()
    results = []
    for pos in positions:
        df = cache.get(pos.symbol, period="1y")
        current_price = (
            float(df.iloc[-1]["Close"]) if df is not None and not df.empty else None
        )
        unrealised_pct = (
            ((current_price - pos.entry_price) / pos.entry_price * 100)
            if current_price
            else None
        )
        holding_days = (datetime.date.today() - pos.entry_date).days

        results.append(
            {
                "symbol": pos.symbol,
                "sector": pos.sector,
                "entry_date": pos.entry_date.isoformat(),
                "entry_price": pos.entry_price,
                "current_price": current_price,
                "stop_loss": pos.stop_loss_price,
                "target": pos.target_price,
                "unrealised_pct": round(unrealised_pct, 2)
                if unrealised_pct is not None
                else None,
                "holding_days": holding_days,
                "position_size": pos.position_size,
                "entry_type": pos.entry_type,
            }
        )
    return sanitize_for_json(results)


@router.get("/trades")
def get_closed_trades(limit: int = 50, db: Session = Depends(get_db)):
    portfolio = db.query(PaperPortfolio).filter_by(is_active=True).first()
    if not portfolio:
        return []

    trades = (
        db.query(PaperTrade)
        .filter_by(portfolio_id=portfolio.id)
        .order_by(desc(PaperTrade.exit_date))
        .limit(limit)
        .all()
    )
    result = [
        {
            "symbol": t.symbol,
            "sector": t.sector,
            "entry_date": t.entry_date.isoformat(),
            "exit_date": t.exit_date.isoformat(),
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "return_pct": round(t.return_pct, 2),
            "pnl": round(t.pnl, 2),
            "exit_reason": t.exit_reason,
            "holding_days": t.holding_days,
        }
        for t in trades
    ]
    return sanitize_for_json(result)
