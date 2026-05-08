from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db import models
from app.screens.registry import SCREEN_REGISTRY
from typing import List, Optional
import logging

router = APIRouter(prefix="/screens", tags=["screens"])
logger = logging.getLogger(__name__)

@router.get("/")
def list_screens():
    return [
        {"slug": slug, "label": meta["label"], "description": meta["description"], "category": meta["category"]}
        for slug, meta in SCREEN_REGISTRY.items()
    ]

@router.get("/{slug}")
def get_screen_results(
    slug: str, 
    live: bool = Query(False),
    db: Session = Depends(get_db)
):
    if slug not in SCREEN_REGISTRY:
        raise HTTPException(status_code=404, detail="Screen not found")
    
    screen_meta = SCREEN_REGISTRY[slug]
    results = []

    if not live:
        # Try fetching from DB
        db_results = (
            db.query(
                models.ScreenResult,
                models.Stock,
                models.FundamentalCache,
                models.TechnicalSignal
            )
            .join(models.Stock, models.ScreenResult.symbol == models.Stock.symbol)
            .outerjoin(models.FundamentalCache, models.Stock.symbol == models.FundamentalCache.symbol)
            .outerjoin(
                models.TechnicalSignal, 
                (models.Stock.symbol == models.TechnicalSignal.symbol) & (models.TechnicalSignal.timeframe == 'D')
            )
            .filter(models.ScreenResult.screen_slug == slug)
            .order_by(models.ScreenResult.rank)
            .all()
        )
        
        if db_results:
            for sr, stock, fund, tech in db_results:
                results.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "rank": sr.rank,
                    "score": sr.score_used,
                    "sector": stock.sector,
                    "market_cap": stock.market_cap,
                    "price": tech.close_price if tech else None,
                    "change_pct": tech.price_change_pct if tech else None,
                    "rsi": tech.rsi if tech else None,
                    "indicators": {
                        "fundamental": {
                            "pe": fund.peg_ratio if fund else None,
                            "roe": fund.roe if fund else None,
                        },
                        "technical": {
                            "rsi": tech.rsi if tech else None,
                            "is_bullish": tech.is_bullish if tech else None
                        }
                    }
                })
            return results

    # Fallback or explicit live execution
    logger.info(f"Executing live screen for {slug}")
    try:
        live_tuples = screen_meta["fn"](db) # Returns list of (symbol, score)
        if live_tuples:
            # Handle both list of symbols and list of (symbol, score) tuples
            if isinstance(live_tuples[0], tuple):
                live_symbols = [t[0] for t in live_tuples]
                score_map = {t[0]: t[1] for t in live_tuples}
            else:
                live_symbols = live_tuples
                score_map = {}
            
            enriched = (
                db.query(models.Stock, models.FundamentalCache, models.TechnicalSignal)
                .outerjoin(models.FundamentalCache, models.Stock.symbol == models.FundamentalCache.symbol)
                .outerjoin(
                    models.TechnicalSignal, 
                    (models.Stock.symbol == models.TechnicalSignal.symbol) & (models.TechnicalSignal.timeframe == 'D')
                )
                .filter(models.Stock.symbol.in_(live_symbols))
                .all()
            )
            
            # Map for quick lookup
            data_map = {s.symbol: (s, f, t) for s, f, t in enriched}
            
            for i, symbol in enumerate(live_symbols):
                if symbol in data_map:
                    stock, fund, tech = data_map[symbol]
                    results.append({
                        "symbol": symbol,
                        "name": stock.name,
                        "rank": i + 1,
                        "score": score_map.get(symbol),
                        "sector": stock.sector,
                        "market_cap": stock.market_cap,
                        "price": tech.close_price if tech else None,
                        "change_pct": tech.price_change_pct if tech else None,
                        "rsi": tech.rsi if tech else None,
                        "indicators": {
                            "fundamental": {
                                "pe": fund.peg_ratio if fund else None,
                                "roe": fund.roe if fund else None,
                            },
                            "technical": {
                                "rsi": tech.rsi if tech else None,
                                "is_bullish": tech.is_bullish if tech else None
                            }
                        }
                    })
    except Exception as e:
        logger.error(f"Live screen {slug} failed: {e}")
        raise HTTPException(status_code=500, detail=f"Error executing screen: {str(e)}")

    return results
