from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db import models
from app.screens.registry import SCREEN_REGISTRY
from app.screens.cache import screen_cache
from app.pipeline.trade_setup import compute_trade_setup
from typing import List, Optional
import logging

router = APIRouter(prefix="/screens", tags=["screens"])
logger = logging.getLogger(__name__)

def _build_screen_response(symbol, name, rank, score, sector, market_cap, tech, fund):
    setup = compute_trade_setup(tech) if tech else None
    
    return {
        "symbol": symbol,
        "name": name,
        "rank": rank,
        "score": score,
        "sector": sector,
        "market_cap": market_cap,
        "rs_score": tech.rs_score if tech else None,
        "momentum_1m": tech.momentum_1m if tech else None,
        "momentum_3m": tech.momentum_3m if tech else None,
        "adx": tech.adx if tech else None,
        "ema_slope": tech.ema_slope_20 if tech else None,
        "pct_from_52w_high": tech.pct_from_52w_high if tech else None,
        "pct_from_52w_low": tech.pct_from_52w_low if tech else None,
        "week52_high": tech.week52_high if tech else None,
        "week52_low": tech.week52_low if tech else None,
        "pct_from_resistance": tech.pct_from_resistance if tech else None,
        "volume_breakout": tech.volume_breakout if tech else None,
        "above_200ema": tech.above_200ema if tech else None,
        "peg_ratio": fund.peg_ratio if fund else None,
        "ev_to_ebitda": fund.ev_to_ebitda if fund else None,
        "dividend_yield": fund.dividend_yield if fund else None,
        "roce": fund.roce if fund else None,
        "de_ratio": fund.de_ratio if fund else None,
        "fcf_positive": fund.fcf_positive if fund else None,
        "dividend_consistency": fund.dividend_consistency if fund else None,
        "market_cap_category": fund.market_cap_category if fund else None,
        "price": tech.close_price if tech else None,
        "change_pct": tech.price_change_pct if tech else None,
        "rsi": tech.rsi if tech else None,
        "setup": setup,
        "indicators": {
            "fundamental": {
                "pe": None,
                "roe": fund.roe if fund else None,
            },
            "technical": {
                "rsi": tech.rsi if tech else None,
                "is_bullish": tech.is_bullish if tech else None
            }
        }
    }

@router.get("/")
def list_screens():
    return [
        {"slug": slug, "label": meta["label"], "description": meta["description"], "category": meta["category"]}
        for slug, meta in SCREEN_REGISTRY.items()
    ]

@router.post("/cache/clear")
def clear_screens_cache():
    screen_cache.invalidate()
    return {"status": "success", "message": "Screens cache cleared"}

@router.get("/{slug}")
def get_screen_results(
    slug: str, 
    response: Response,
    live: bool = Query(False),
    db: Session = Depends(get_db)
):
    if slug not in SCREEN_REGISTRY:
        raise HTTPException(status_code=404, detail="Screen not found")
    
    cache_key = f"screen:{slug}:{live}"
    cached_val = screen_cache.get(cache_key)
    if cached_val is not None:
        response.headers["X-Cache"] = "HIT"
        return cached_val

    response.headers["X-Cache"] = "MISS"
    screen_meta = SCREEN_REGISTRY[slug]
    results = []

    if not live:
        # 1. Find the latest computed_at for this specific screen
        latest_run = (
            db.query(func.max(models.ScreenResult.computed_at))
            .filter(models.ScreenResult.screen_slug == slug)
            .scalar()
        )
        
        if not latest_run:
            # No data in DB, will fallback to live
            db_results = []
        else:
            # 2. Latest TechnicalSignal subquery
            latest_signal_sub = (
                db.query(
                    models.TechnicalSignal.symbol,
                    func.max(models.TechnicalSignal.date).label("max_date")
                )
                .filter(models.TechnicalSignal.timeframe == 'D')
                .group_by(models.TechnicalSignal.symbol)
                .subquery()
            )

            # 3. Fetch from DB with proper joins and latest run filter
            db_results = (
                db.query(
                    models.ScreenResult,
                    models.Stock,
                    models.FundamentalCache,
                    models.TechnicalSignal
                )
                .join(models.Stock, models.ScreenResult.symbol == models.Stock.symbol)
                .outerjoin(models.FundamentalCache, models.Stock.symbol == models.FundamentalCache.symbol)
                .outerjoin(latest_signal_sub, models.Stock.symbol == latest_signal_sub.c.symbol)
                .outerjoin(
                    models.TechnicalSignal, 
                    (models.Stock.symbol == models.TechnicalSignal.symbol) & 
                    (models.TechnicalSignal.timeframe == 'D') &
                    (models.TechnicalSignal.date == latest_signal_sub.c.max_date)
                )
                .filter(models.ScreenResult.screen_slug == slug)
                .filter(models.ScreenResult.computed_at == latest_run)
                .order_by(models.ScreenResult.rank)
                .all()
            )
        
        if db_results:
            for sr, stock, fund, tech in db_results:
                results.append(
                    _build_screen_response(
                        symbol=stock.symbol,
                        name=stock.name,
                        rank=sr.rank,
                        score=sr.score_used,
                        sector=stock.sector,
                        market_cap=stock.market_cap,
                        tech=tech,
                        fund=fund
                    )
                )

    # Fallback or explicit live execution
    if (live or not results) and slug in SCREEN_REGISTRY:
        logger.info(f"Executing live screen for {slug}")
        try:
            live_data = screen_meta["fn"](db) # Returns list of (symbol, score) or symbols
            if live_data:
                # Handle both list of symbols and list of (symbol, score) tuples/Rows
                # Check if first element is tuple-like (has at least 1 element and is not a string)
                first_item = live_data[0]
                is_tuple_like = hasattr(first_item, "__iter__") and not isinstance(first_item, (str, bytes))
                
                if is_tuple_like:
                    live_symbols = [t[0] for t in live_data]
                    score_map = {t[0]: t[1] for t in live_data if len(t) > 1}
                else:
                    live_symbols = live_data
                    score_map = {}
                
                # Latest TechnicalSignal subquery
                latest_signal_sub = (
                    db.query(
                        models.TechnicalSignal.symbol,
                        func.max(models.TechnicalSignal.date).label("max_date")
                    )
                    .filter(models.TechnicalSignal.timeframe == 'D')
                    .group_by(models.TechnicalSignal.symbol)
                    .subquery()
                )

                enriched = (
                    db.query(models.Stock, models.FundamentalCache, models.TechnicalSignal)
                    .outerjoin(models.FundamentalCache, models.Stock.symbol == models.FundamentalCache.symbol)
                    .outerjoin(latest_signal_sub, models.Stock.symbol == latest_signal_sub.c.symbol)
                    .outerjoin(
                        models.TechnicalSignal, 
                        (models.Stock.symbol == models.TechnicalSignal.symbol) & 
                        (models.TechnicalSignal.timeframe == 'D') &
                        (models.TechnicalSignal.date == latest_signal_sub.c.max_date)
                    )
                    .filter(models.Stock.symbol.in_(live_symbols))
                    .all()
                )
                
                # Map for quick lookup
                data_map = {s.symbol: (s, f, t) for s, f, t in enriched}
                
                for i, symbol in enumerate(live_symbols):
                    if symbol in data_map:
                        stock, fund, tech = data_map[symbol]
                        results.append(
                            _build_screen_response(
                                symbol=symbol,
                                name=stock.name,
                                rank=i + 1,
                                score=score_map.get(symbol),
                                sector=stock.sector,
                                market_cap=stock.market_cap,
                                tech=tech,
                                fund=fund
                            )
                        )
        except Exception as e:
            logger.error(f"Live screen {slug} failed: {e}")
            raise HTTPException(status_code=500, detail=f"Error executing screen: {str(e)}")

    # 4. Cache write — after both paths
    screen_cache.set(cache_key, results, 60 if live else 900)
    return results
