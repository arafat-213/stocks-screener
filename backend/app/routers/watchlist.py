from datetime import date
from typing import List, Literal, Optional

import pandas as pd
import pandas_ta_classic  # noqa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import FundamentalCache, TechnicalSignal, Watchlist
from app.db.session import get_db
from app.pipeline.ohlcv_cache import OHLCVCache
from app.pipeline.trade_setup import compute_trade_setup

router = APIRouter(prefix="/watchlist", tags=["watchlist"])
_ohlcv_cache = OHLCVCache()


class WatchlistAddRequest(BaseModel):
    symbol: str
    signal_date: date


class WatchlistStatusUpdate(BaseModel):
    status: Literal["watching", "entered", "skipped"]


class WatchlistResponse(BaseModel):
    id: int
    symbol: str
    added_date: date
    signal_date: date
    quality_tier: Optional[str] = None
    signal_score: Optional[float] = None
    planned_entry_low: Optional[float] = None
    planned_entry_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    status: str

    class Config:
        from_attributes = True


class WatchlistLiveResponse(WatchlistResponse):
    days_elapsed: int
    current_price: float
    vs_ema21_pct: float
    in_zone: bool


@router.post("/", response_model=WatchlistResponse)
def add_to_watchlist(req: WatchlistAddRequest, db: Session = Depends(get_db)):
    # 1. Check if already exists
    existing = (
        db.query(Watchlist)
        .filter_by(symbol=req.symbol, signal_date=req.signal_date)
        .first()
    )
    if existing:
        return existing

    # 2. Fetch TechnicalSignal for metadata
    # We look for 'D' timeframe signal on that date
    signal = (
        db.query(TechnicalSignal)
        .filter(
            TechnicalSignal.symbol == req.symbol,
            func.date(TechnicalSignal.date) == req.signal_date,
            TechnicalSignal.timeframe == "D",
        )
        .first()
    )

    if not signal:
        raise HTTPException(
            status_code=404, detail="Signal not found for this date and symbol"
        )

    # 3. Derive metadata
    # quality_tier from FundamentalCache
    fund = db.query(FundamentalCache).filter_by(symbol=req.symbol).first()
    quality_tier = "C"
    if fund:
        if (
            fund.profitability_streak_passed
            and fund.de_check_passed
            and fund.fcf_positive
        ):
            quality_tier = "A"
        elif fund.profitability_streak_passed or fund.de_check_passed:
            quality_tier = "B"

    # trade setup levels
    setup = compute_trade_setup(signal)

    entry_low = setup["entry_zone"]["low"] if setup else None
    entry_high = setup["entry_zone"]["high"] if setup else None
    stop_loss = setup["stop_loss"] if setup else None
    target = setup["targets"][-1]["level"] if setup and setup.get("targets") else None

    # 4. Create Watchlist entry
    new_entry = Watchlist(
        symbol=req.symbol,
        signal_date=req.signal_date,
        quality_tier=quality_tier,
        signal_score=signal.entry_score,
        planned_entry_low=entry_low,
        planned_entry_high=entry_high,
        stop_loss=stop_loss,
        target=target,
        status="watching",
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    return new_entry


def _calculate_live_metrics(entry: Watchlist, df: pd.DataFrame):
    """
    Helper to calculate live tracking metrics from OHLCV history.
    """
    if df is None or df.empty:
        return None

    # Ensure index is naive for comparison
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)

    # 1. Days elapsed since signal_date (trading sessions)
    # signal_date is date, df.index is Timestamps
    signal_ts = pd.Timestamp(entry.signal_date)
    post_signal_df = df[df.index > signal_ts]
    days_elapsed = len(post_signal_df)

    # 2. Current price
    current_price = df["Close"].iloc[-1]

    # 3. EMA21 calculation
    # We need enough data for EMA21, pandas_ta_classic handles it
    ema21_output = df.ta.ema(length=21)
    current_ema21 = None
    if ema21_output is not None and not ema21_output.empty:
        # If multiple columns (DataFrame), take the first one
        if isinstance(ema21_output, pd.DataFrame):
            val = ema21_output.iloc[-1, 0]
        else:
            val = ema21_output.iloc[-1]

        if pd.notnull(val):
            current_ema21 = float(val)

    vs_ema21_pct = 0.0
    if current_ema21 is not None:
        vs_ema21_pct = ((current_price - current_ema21) / current_ema21) * 100

    # 4. In Zone detection
    in_zone = False
    if entry.planned_entry_low and entry.planned_entry_high:
        in_zone = entry.planned_entry_low <= current_price <= entry.planned_entry_high

    return {
        "days_elapsed": days_elapsed,
        "current_price": current_price,
        "vs_ema21_pct": round(float(vs_ema21_pct), 2),
        "in_zone": in_zone,
    }


@router.get("/", response_model=List[WatchlistLiveResponse])
def get_watchlist(db: Session = Depends(get_db)):
    # 1. Fetch active entries
    entries = db.query(Watchlist).filter(Watchlist.status == "watching").all()

    results = []
    for entry in entries:
        # 2. Get live data
        df = _ohlcv_cache.get(entry.symbol)
        metrics = _calculate_live_metrics(entry, df)

        if not metrics:
            # Skip or return with defaults if no data
            continue

        # 3. Auto-expiration
        if metrics["days_elapsed"] > 8:
            entry.status = "expired"
            db.commit()
            continue

        # 4. Combine
        live_data_dict = {
            "id": entry.id,
            "symbol": entry.symbol,
            "added_date": entry.added_date,
            "signal_date": entry.signal_date,
            "quality_tier": entry.quality_tier,
            "signal_score": entry.signal_score,
            "planned_entry_low": entry.planned_entry_low,
            "planned_entry_high": entry.planned_entry_high,
            "stop_loss": entry.stop_loss,
            "target": entry.target,
            "status": entry.status,
            "days_elapsed": metrics["days_elapsed"],
            "current_price": metrics["current_price"],
            "vs_ema21_pct": metrics["vs_ema21_pct"],
            "in_zone": metrics["in_zone"],
        }

        results.append(WatchlistLiveResponse(**live_data_dict))

    return results


@router.patch("/{symbol}", response_model=WatchlistResponse)
def update_watchlist_status_by_symbol(
    symbol: str, req: WatchlistStatusUpdate, db: Session = Depends(get_db)
):
    entry = (
        db.query(Watchlist)
        .filter(Watchlist.symbol == symbol, Watchlist.status == "watching")
        .first()
    )

    if not entry:
        # If not found in 'watching', try to find the latest one regardless of status
        entry = (
            db.query(Watchlist)
            .filter(Watchlist.symbol == symbol)
            .order_by(Watchlist.added_date.desc())
            .first()
        )

    if not entry:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")

    entry.status = req.status
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{symbol}")
def remove_from_watchlist(symbol: str, db: Session = Depends(get_db)):
    # Remove the active 'watching' entry
    entry = (
        db.query(Watchlist)
        .filter(Watchlist.symbol == symbol, Watchlist.status == "watching")
        .first()
    )

    if not entry:
        # Fallback to latest entry if no active one
        entry = (
            db.query(Watchlist)
            .filter(Watchlist.symbol == symbol)
            .order_by(Watchlist.added_date.desc())
            .first()
        )

    if not entry:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")

    db.delete(entry)
    db.commit()
    return {"status": "success", "message": f"Removed {symbol} from watchlist"}


@router.get("/expired", response_model=List[WatchlistResponse])
def get_expired_watchlist(db: Session = Depends(get_db)):
    """
    Return all Watchlist entries where status is NOT 'watching'.
    This covers 'expired', 'entered', and 'skipped'.
    """
    entries = (
        db.query(Watchlist)
        .filter(Watchlist.status != "watching")
        .order_by(Watchlist.added_date.desc())
        .all()
    )
    return entries
