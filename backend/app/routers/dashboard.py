import asyncio

from fastapi import APIRouter, Depends, Response
from sqlalchemy import case, func, or_
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from app.core.cache import response_cache
from app.db.models import (
    MarketSnapshot,
    PipelineRun,
    Stock,
    TechnicalSignal,
)
from app.db.session import get_db
from app.pipeline.fetcher import fetch_market_snapshots
from app.pipeline.trade_setup import compute_trade_setup
from app.screens.base import get_latest_signal_date

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
market_lock = asyncio.Lock()


def get_live_market_data():
    # Relies entirely on requests-cache for the 60s TTL
    return fetch_market_snapshots(["^NSEI", "^BSESN"])


@router.get("/changes")
def get_signal_changes(response: Response, db: Session = Depends(get_db)):
    cache_key = "dashboard:changes"
    cached, hit = response_cache.get(cache_key)
    if hit:
        response.headers["X-Cache"] = "HIT"
        return cached

    response.headers["X-Cache"] = "MISS"

    # 1. Get the two most recent distinct dates for Daily timeframe
    dates = (
        db.query(func.date(TechnicalSignal.date))
        .filter(TechnicalSignal.timeframe == "D")
        .distinct()
        .order_by(func.date(TechnicalSignal.date).desc())
        .limit(2)
        .all()
    )

    if len(dates) < 2:
        data = {
            "changes": [],
            "as_of": str(dates[0][0]) if dates else None,
            "prev_date": None,
        }
        response_cache.set(cache_key, data, 600)
        return data

    latest_date = dates[0][0]
    prev_date = dates[1][0]

    # 2. Get signals for both dates (including all timeframes for confluence)
    # Filter by dates using func.date to match the distinct dates found
    latest_signals_raw = (
        db.query(TechnicalSignal, Stock.name)
        .join(Stock, TechnicalSignal.symbol == Stock.symbol)
        .filter(func.date(TechnicalSignal.date) == latest_date)
        .all()
    )

    prev_signals_raw = (
        db.query(TechnicalSignal)
        .filter(func.date(TechnicalSignal.date) == prev_date)
        .all()
    )

    # 3. Process into maps: symbol -> {timeframes: {D: bool, W: bool, M: bool}, ...}
    def build_signal_map(raw_signals):
        s_map = {}
        for row in raw_signals:
            # SQLAlchemy 2.0 Row objects are not tuples. Handle both cases.
            if isinstance(row, (tuple, Row)):
                sig = row[0]
                name = row[1] if len(row) > 1 else None
            else:
                sig = row
                name = None

            if sig.symbol not in s_map:
                s_map[sig.symbol] = {
                    "timeframes": {},
                    "name": name,
                    "close": None,
                    "change": None,
                    "score": None,
                }

            s_map[sig.symbol]["timeframes"][sig.timeframe] = sig.is_bullish
            if sig.timeframe == "D":
                s_map[sig.symbol]["close"] = sig.close_price
                s_map[sig.symbol]["change"] = sig.price_change_pct
                s_map[sig.symbol]["score"] = sig.entry_score
        return s_map

    latest_map = build_signal_map(latest_signals_raw)
    prev_map = build_signal_map(prev_signals_raw)

    # 4. Compute changes
    changes = []
    for symbol, latest in latest_map.items():
        if symbol not in prev_map:
            continue

        prev = prev_map[symbol]

        # Confluence calculation
        latest_conf = sum(1 for tf in latest["timeframes"].values() if tf)
        prev_conf = sum(1 for tf in prev["timeframes"].values() if tf)

        # Daily flip
        latest_d_bullish = latest["timeframes"].get("D", False)
        prev_d_bullish = prev["timeframes"].get("D", False)

        change_type = None
        if not prev_d_bullish and latest_d_bullish:
            change_type = "newly_bullish"
        elif prev_d_bullish and not latest_d_bullish:
            change_type = "turned_bearish"
        elif latest_conf > prev_conf:
            change_type = "confluence_improved"
        elif latest_conf < prev_conf:
            change_type = "confluence_dropped"

        if change_type:
            changes.append(
                {
                    "symbol": symbol,
                    "name": latest["name"],
                    "change_type": change_type,
                    "prev_score": prev.get(
                        "score"
                    ),  # Note: prev score might be from prev_map signal
                    "curr_score": latest["score"],
                    "close_price": latest["close"],
                    "price_change_pct": latest["change"],
                }
            )

    # Sort and limit: 10 bullish flips + 10 bearish flips max as per spec
    # newly_bullish/confluence_improved first, then turned_bearish/confluence_dropped
    bullish_changes = [
        c
        for c in changes
        if c["change_type"] in ["newly_bullish", "confluence_improved"]
    ]
    bearish_changes = [
        c
        for c in changes
        if c["change_type"] in ["turned_bearish", "confluence_dropped"]
    ]

    bullish_changes.sort(key=lambda x: x["curr_score"] or 0, reverse=True)
    bearish_changes.sort(key=lambda x: x["curr_score"] or 0, reverse=True)

    final_changes = bullish_changes[:10] + bearish_changes[:10]

    data = {
        "as_of": str(latest_date),
        "prev_date": str(prev_date),
        "changes": final_changes,
    }

    response_cache.set(cache_key, data, 600)
    return data


@router.get("/market/live")
async def get_live_market(response: Response):
    cache_key = "dashboard:market_live"
    cached, hit = response_cache.get(cache_key)
    if hit:
        response.headers["X-Cache"] = "HIT"
        return cached

    async with market_lock:
        # Re-check cache after acquiring lock
        cached, hit = response_cache.get(cache_key)
        if hit:
            response.headers["X-Cache"] = "HIT"
            return cached

        response.headers["X-Cache"] = "MISS"
        # Offload blocking yfinance call to a thread
        market_data = await asyncio.to_thread(get_live_market_data)
        data = {"market_context": market_data}
        response_cache.set(cache_key, data, 60)
        return data


def get_market_cap_category(mcap_float: float | None) -> str:
    """Calculates market cap category based on standard Indian thresholds."""
    if not mcap_float:
        return "unknown"
    # Thresholds: Large > 20,000 Cr, Mid 5,000 - 20,000 Cr, Small < 5,000 Cr
    # Mcap in absolute INR: 5,000 Cr = 50,000,000,000
    if mcap_float >= 200_000_000_000:
        return "largecap"
    if mcap_float >= 50_000_000_000:
        return "midcap"
    return "smallcap"


@router.get("/screener/results")
def get_dashboard_results(
    response: Response,
    db: Session = Depends(get_db),
    offset: int = 0,
    limit: int = 50,
    sector: str = None,
    confluence: str = None,
    symbols: str = None,
    sort_by: str = "confluence",
    fundamental_filter: bool = True,
):
    # Create a cache key that includes parameters
    params_str = f"off:{offset}:lim:{limit}:sec:{sector}:conf:{confluence}:sym:{symbols}:sort:{sort_by}"
    cache_key = f"dashboard:screener_results:{params_str}"

    cached, hit = response_cache.get(cache_key)
    if hit:
        response.headers["X-Cache"] = "HIT"
        return cached

    response.headers["X-Cache"] = "MISS"

    # 1. Get latest dates for each timeframe to avoid slow subqueries
    latest_date_d = get_latest_signal_date(db, "D")
    latest_date_w = get_latest_signal_date(db, "W")
    latest_date_m = get_latest_signal_date(db, "M")

    # 2. Confluence calculation query
    # We want to group by symbol and count bullish signals across timeframes
    # We filter by the latest dates discovered above to use indexes efficiently
    confluence_sub = (
        db.query(
            TechnicalSignal.symbol,
            func.sum(case((TechnicalSignal.is_bullish, 1), else_=0)).label(
                "confluence_count"
            ),
        )
        .filter(
            or_(
                (TechnicalSignal.timeframe == "D")
                & (func.date(TechnicalSignal.date) == latest_date_d),
                (TechnicalSignal.timeframe == "W")
                & (func.date(TechnicalSignal.date) == latest_date_w),
                (TechnicalSignal.timeframe == "M")
                & (func.date(TechnicalSignal.date) == latest_date_m),
            )
        )
        .group_by(TechnicalSignal.symbol)
        .subquery()
    )

    # 3. Base Query for filtering and counting
    query = db.query(
        Stock,
        confluence_sub.c.confluence_count,
    ).join(confluence_sub, Stock.symbol == confluence_sub.c.symbol)

    # Apply filters
    if sector:
        sector_list = [s.strip() for s in sector.split(",")]
        query = query.filter(Stock.sector.in_(sector_list))

    if confluence:
        if confluence == "3":
            query = query.filter(confluence_sub.c.confluence_count == 3)
        elif confluence == "2+":
            query = query.filter(confluence_sub.c.confluence_count >= 2)

    if symbols:
        symbol_list = [s.strip() for s in symbols.split(",")]
        query = query.filter(Stock.symbol.in_(symbol_list))

    # 4. Total Count
    total = query.count()

    # 5. Ordering and Pagination
    # For ordering, we also need the Daily signal's score, RSI and bullish status
    daily_signal = (
        db.query(
            TechnicalSignal.symbol,
            TechnicalSignal.is_bullish,
            TechnicalSignal.entry_score,
            TechnicalSignal.rsi,
        )
        .filter(
            TechnicalSignal.timeframe == "D",
            func.date(TechnicalSignal.date) == latest_date_d,
        )
        .subquery()
    )

    query = query.outerjoin(daily_signal, Stock.symbol == daily_signal.c.symbol)

    if sort_by == "score":
        query = query.order_by(func.coalesce(daily_signal.c.entry_score, 0).desc())
    elif sort_by == "rsi":
        query = query.order_by(func.coalesce(daily_signal.c.rsi, 0).desc())
    else:  # confluence (default)
        query = query.order_by(
            confluence_sub.c.confluence_count.desc(),
            func.coalesce(daily_signal.c.is_bullish, False).desc(),
            func.coalesce(daily_signal.c.entry_score, 0).desc(),
        )

    # Execute with pagination
    paged_stocks = query.offset(offset).limit(limit).all()

    # 6. Fetch full data for the paged symbols
    paged_symbols = [stock.symbol for stock, count in paged_stocks]

    if not paged_symbols:
        result = {
            "total": 0,
            "offset": offset,
            "limit": limit,
            "has_more": False,
            "items": [],
        }
        response_cache.set(cache_key, result, 600)
        return result

    # Fetch all signals for these symbols
    all_signals = (
        db.query(TechnicalSignal)
        .filter(TechnicalSignal.symbol.in_(paged_symbols))
        .filter(
            or_(
                (TechnicalSignal.timeframe == "D")
                & (func.date(TechnicalSignal.date) == latest_date_d),
                (TechnicalSignal.timeframe == "W")
                & (func.date(TechnicalSignal.date) == latest_date_w),
                (TechnicalSignal.timeframe == "M")
                & (func.date(TechnicalSignal.date) == latest_date_m),
            )
        )
        .all()
    )

    # 7. Reconstruct into the same enriched data structure
    stocks_map = {
        stock.symbol: {
            "symbol": stock.symbol,
            "name": stock.name,
            "sector": stock.sector,
            "confluence_count": count,
            "close_price": None,
            "price_change_pct": None,
            "timeframes": {},
            "fundamentals": {
                "market_cap": stock.market_cap,
                "market_cap_category": get_market_cap_category(stock.market_cap),
            },
        }
        for stock, count in paged_stocks
    }

    for sig in all_signals:
        if sig.symbol in stocks_map:
            stocks_map[sig.symbol]["timeframes"][sig.timeframe] = {
                "is_bullish": sig.is_bullish,
                "score": sig.entry_score,
                "rsi": sig.rsi,
                "ema_signal": sig.ema_signal,
                "rs_score": sig.rs_score,
                "momentum_3m": sig.momentum_3m,
                "momentum_1m": sig.momentum_1m,
                "adx": sig.adx,
                "above_200ema": sig.above_200ema,
                "volume_breakout": sig.volume_breakout,
                "pct_from_52wh": sig.pct_from_52w_high,
                "atr": sig.atr,
            }
            if sig.timeframe == "D":
                stocks_map[sig.symbol]["close_price"] = sig.close_price
                stocks_map[sig.symbol]["price_change_pct"] = sig.price_change_pct
                stocks_map[sig.symbol]["setup"] = compute_trade_setup(sig)

    # Maintain original order from paged_stocks
    items = [stocks_map[symbol] for symbol in paged_symbols]

    result = {
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
        "items": items,
    }

    response_cache.set(cache_key, result, 600)
    return result


@router.get("/pipeline/latest")
def get_pipeline_status(response: Response, db: Session = Depends(get_db)):
    cache_key = "dashboard:pipeline_status"
    cached, hit = response_cache.get(cache_key)
    if hit:
        response.headers["X-Cache"] = "HIT"
        return cached

    response.headers["X-Cache"] = "MISS"
    run = db.query(PipelineRun).order_by(PipelineRun.timestamp.desc()).first()
    if not run:
        data = {"status": "never_run", "market_context": []}
        response_cache.set(cache_key, data, 30)
        return data

    # MarketSnapshot uses Date, PipelineRun uses DateTime
    market = (
        db.query(MarketSnapshot)
        .filter(MarketSnapshot.date == run.timestamp.date())
        .all()
    )

    # Calculate age
    import datetime

    age_delta = datetime.datetime.now(datetime.timezone.utc) - run.timestamp
    data_age_hours = round(age_delta.total_seconds() / 3600.0, 1)
    is_stale = data_age_hours > 26

    data = {
        "status": run.status,
        "scored_at": run.timestamp,
        "data_age_hours": data_age_hours,
        "is_stale": is_stale,
        "stocks_fetched": run.stocks_fetched,
        "total_symbols": run.total_symbols or 0,
        "tier1_count": run.tier1_count,
        "stocks_scored": run.stocks_scored,
        "market_context": [
            {"symbol": m.symbol, "close": m.close, "change_pct": m.change_pct}
            for m in market
        ],
    }
    response_cache.set(cache_key, data, 30)
    return data
