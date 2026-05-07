from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.db.models import Stock, TechnicalSignal, FundamentalData, PipelineRun, MarketSnapshot

router = APIRouter()

@router.get("/screener/results")
def get_dashboard_results(db: Session = Depends(get_db)):
    # 1. Get latest date from signals
    max_date = db.query(func.max(TechnicalSignal.date)).scalar()
    if not max_date:
        return []
        
    # 2. Latest Fundamental Subquery (Max date per symbol)
    latest_fund = db.query(
        FundamentalData.symbol,
        func.max(FundamentalData.date).label("max_date")
    ).group_by(FundamentalData.symbol).subquery()
    
    # 3. Join Query
    query_results = db.query(TechnicalSignal, Stock, FundamentalData).\
        join(Stock, TechnicalSignal.symbol == Stock.symbol).\
        outerjoin(latest_fund, Stock.symbol == latest_fund.c.symbol).\
        outerjoin(FundamentalData, (FundamentalData.symbol == latest_fund.c.symbol) & (FundamentalData.date == latest_fund.c.max_date)).\
        filter(TechnicalSignal.date == max_date).all()
        
    # 4. Python grouping
    stocks_map = {}
    for signal, stock, fund in query_results:
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
                    "roe": fund.roe if fund else None,
                    "market_cap": fund.market_cap if fund else stock.market_cap
                }
            }
        
        # Add timeframe signal
        stocks_map[stock.symbol]["timeframes"][signal.timeframe] = {
            "is_bullish": signal.is_bullish,
            "score": signal.entry_score,
            "rsi": signal.rsi,
            "ema_signal": signal.ema_signal
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

    return final_results

@router.get("/pipeline/latest")
def get_pipeline_status(db: Session = Depends(get_db)):
    run = db.query(PipelineRun).order_by(PipelineRun.timestamp.desc()).first()
    if not run:
        return {"status": "never_run", "market_context": []}
        
    # MarketSnapshot uses Date, PipelineRun uses DateTime
    market = db.query(MarketSnapshot).filter(MarketSnapshot.date == run.timestamp.date()).all()
    
    return {
        "status": run.status,
        "scored_at": run.timestamp,
        "stocks_fetched": run.stocks_fetched,
        "tier1_count": run.tier1_count,
        "tier2_count": run.tier2_count,
        "stocks_scored": run.stocks_scored,
        "market_context": [
            {"symbol": m.symbol, "close": m.close, "change_pct": m.change_pct} 
            for m in market
        ]
    }
