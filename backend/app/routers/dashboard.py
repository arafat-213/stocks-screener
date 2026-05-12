from fastapi import APIRouter, Depends, Response
import asyncio
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.engine import Row
from app.db.session import get_db
from app.db.models import Stock, TechnicalSignal, FundamentalData, PipelineRun, MarketSnapshot, FundamentalCache
from app.pipeline.fetcher import fetch_stock_data, fetch_market_snapshots
from app.core.cache import response_cache

router = APIRouter()
market_lock = asyncio.Lock()

def get_live_market_data():
    # Relies entirely on requests-cache for the 60s TTL
    return fetch_market_snapshots(["^NSEI", "^BSESN"])

@router.get("/dashboard/changes")
def get_signal_changes(response: Response, db: Session = Depends(get_db)):
    cache_key = "dashboard:changes"
    cached, hit = response_cache.get(cache_key)
    if hit:
        response.headers["X-Cache"] = "HIT"
        return cached

    response.headers["X-Cache"] = "MISS"
    
    # 1. Get the two most recent distinct dates for Daily timeframe
    dates = db.query(func.date(TechnicalSignal.date)).\
        filter(TechnicalSignal.timeframe == 'D').\
        distinct().order_by(func.date(TechnicalSignal.date).desc()).limit(2).all()
    
    if len(dates) < 2:
        data = {"changes": [], "as_of": str(dates[0][0]) if dates else None, "prev_date": None}
        response_cache.set(cache_key, data, 600)
        return data
    
    latest_date = dates[0][0]
    prev_date = dates[1][0]

    # 2. Get signals for both dates (including all timeframes for confluence)
    # Filter by dates using func.date to match the distinct dates found
    latest_signals_raw = db.query(TechnicalSignal, Stock.name).\
        join(Stock, TechnicalSignal.symbol == Stock.symbol).\
        filter(func.date(TechnicalSignal.date) == latest_date).all()
        
    prev_signals_raw = db.query(TechnicalSignal).\
        filter(func.date(TechnicalSignal.date) == prev_date).all()

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
                s_map[sig.symbol] = {"timeframes": {}, "name": name, "close": None, "change": None, "score": None}
            
            s_map[sig.symbol]["timeframes"][sig.timeframe] = sig.is_bullish
            if sig.timeframe == 'D':
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
        latest_d_bullish = latest["timeframes"].get('D', False)
        prev_d_bullish = prev["timeframes"].get('D', False)
        
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
            changes.append({
                "symbol": symbol,
                "name": latest["name"],
                "change_type": change_type,
                "prev_score": prev.get("score"), # Note: prev score might be from prev_map signal
                "curr_score": latest["score"],
                "close_price": latest["close"],
                "price_change_pct": latest["change"]
            })

    # Sort and limit: 10 bullish flips + 10 bearish flips max as per spec
    # newly_bullish/confluence_improved first, then turned_bearish/confluence_dropped
    bullish_changes = [c for c in changes if c["change_type"] in ["newly_bullish", "confluence_improved"]]
    bearish_changes = [c for c in changes if c["change_type"] in ["turned_bearish", "confluence_dropped"]]
    
    bullish_changes.sort(key=lambda x: x["curr_score"] or 0, reverse=True)
    bearish_changes.sort(key=lambda x: x["curr_score"] or 0, reverse=True)
    
    final_changes = bullish_changes[:10] + bearish_changes[:10]

    data = {
        "as_of": str(latest_date),
        "prev_date": str(prev_date),
        "changes": final_changes
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

@router.get("/screener/results")
def get_dashboard_results(response: Response, db: Session = Depends(get_db)):
    cache_key = "dashboard:screener_results"
    cached, hit = response_cache.get(cache_key)
    if hit:
        response.headers["X-Cache"] = "HIT"
        return cached

    response.headers["X-Cache"] = "MISS"
    # 1. Latest TechnicalSignal Subquery (Max date per symbol/timeframe)
    latest_signal = db.query(
        TechnicalSignal.symbol,
        TechnicalSignal.timeframe,
        func.max(TechnicalSignal.date).label("max_date")
    ).group_by(TechnicalSignal.symbol, TechnicalSignal.timeframe).subquery()
        
    # 2. Latest Fundamental Subquery (Max date per symbol)
    latest_fund = db.query(
        FundamentalData.symbol,
        func.max(FundamentalData.date).label("max_date")
    ).group_by(FundamentalData.symbol).subquery()
    
    # 3. Join Query
    query_results = db.query(TechnicalSignal, Stock, FundamentalData, FundamentalCache).\
        join(Stock, TechnicalSignal.symbol == Stock.symbol).\
        join(latest_signal, (TechnicalSignal.symbol == latest_signal.c.symbol) & \
                           (TechnicalSignal.timeframe == latest_signal.c.timeframe) & \
                           (TechnicalSignal.date == latest_signal.c.max_date)).\
        outerjoin(latest_fund, Stock.symbol == latest_fund.c.symbol).\
        outerjoin(FundamentalData, (FundamentalData.symbol == latest_fund.c.symbol) & (FundamentalData.date == latest_fund.c.max_date)).\
        outerjoin(FundamentalCache, Stock.symbol == FundamentalCache.symbol).\
        filter(FundamentalCache.profitability_streak_passed == True).\
        filter(FundamentalCache.de_check_passed == True).all()
        
    # 4. Python grouping
    stocks_map = {}
    for signal, stock, fund, cache in query_results:
        if stock.symbol not in stocks_map:
            stocks_map[stock.symbol] = {
                "symbol": stock.symbol,
                "name": stock.name,
                "sector": stock.sector,
                "close_price": signal.close_price if signal.timeframe == 'D' else None,
                "price_change_pct": signal.price_change_pct if signal.timeframe == 'D' else None,
                "timeframes": {},
                "fundamentals": {
                    "pe": fund.pe if fund else None,
                    "pb": fund.pb if fund else None,
                    "roe": cache.roe if (cache and cache.roe is not None) else (fund.roe if fund else None),
                    "roce": cache.roce if cache else None,
                    "peg": cache.peg_ratio if cache else None,
                    "yield": cache.dividend_yield if cache else None,
                    "debt_equity": cache.de_ratio if cache else (fund.debt_equity if fund else None),
                    "market_cap": fund.market_cap if fund else stock.market_cap,
                    "market_cap_category": cache.market_cap_category if cache else None
                }
            }
        
        # Add timeframe signal
        stocks_map[stock.symbol]["timeframes"][signal.timeframe] = {
            "is_bullish": signal.is_bullish,
            "score": signal.entry_score,
            "rsi": signal.rsi,
            "ema_signal": signal.ema_signal,
            "rs_score": signal.rs_score,
            "momentum_3m": signal.momentum_3m,
            "momentum_1m": signal.momentum_1m,
            "adx": signal.adx,
            "above_200ema": signal.above_200ema,
            "volume_breakout": signal.volume_breakout,
            "pct_from_52wh": signal.pct_from_52w_high,
            "atr": signal.atr
        }
        
        # Ensure D price info is captured even if row order varies
        if signal.timeframe == 'D':
            stocks_map[stock.symbol]["close_price"] = signal.close_price
            stocks_map[stock.symbol]["price_change_pct"] = signal.price_change_pct

    # 5. Final Confluence & Sorting
    final_results = list(stocks_map.values())
    for item in final_results:
        item["confluence_count"] = sum(1 for tf in item["timeframes"].values() if tf["is_bullish"])
    
    # Sort: Confluence DESC -> Daily Bullish DESC -> Daily Score DESC
    final_results.sort(key=lambda x: (
        x["confluence_count"],
        x["timeframes"].get('D', {}).get('is_bullish', False),
        x["timeframes"].get('D', {}).get('score', 0)
    ), reverse=True)

    response_cache.set(cache_key, final_results, 600)
    return final_results

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
    market = db.query(MarketSnapshot).filter(MarketSnapshot.date == run.timestamp.date()).all()
    
    # Calculate age
    import datetime
    age_delta = datetime.datetime.utcnow() - run.timestamp
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
        "tier2_count": run.tier2_count,
        "stocks_scored": run.stocks_scored,
        "market_context": [
            {"symbol": m.symbol, "close": m.close, "change_pct": m.change_pct} 
            for m in market
        ]
    }
    response_cache.set(cache_key, data, 30)
    return data
