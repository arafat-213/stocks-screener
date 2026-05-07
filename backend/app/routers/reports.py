from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from app.db.session import get_db
from app.db.models import Stock, TechnicalSignal
from datetime import datetime

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.get("")
def list_reports(db: Session = Depends(get_db)):
    # Get unique dates from technical_signals table, cast to Date to remove time component
    dates = db.query(func.distinct(cast(TechnicalSignal.date, Date))).\
        order_by(cast(TechnicalSignal.date, Date).desc()).all()
    return [d[0].strftime("%Y-%m-%d") for d in dates if d[0]]

@router.get("/latest")
def get_latest_report(db: Session = Depends(get_db)):
    # Find the most recent date in the technical_signals table
    max_date = db.query(func.max(TechnicalSignal.date)).scalar()
    if not max_date:
        return []
    return get_report_by_date(max_date.strftime("%Y-%m-%d"), db)

@router.get("/{date}")
def get_report_by_date(date: str, db: Session = Depends(get_db)):
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Join TechnicalSignal with Stock
    query_results = db.query(TechnicalSignal, Stock).\
        join(Stock, TechnicalSignal.symbol == Stock.symbol).\
        filter(cast(TechnicalSignal.date, Date) == date_obj).all()

    if not query_results:
        return []

    # Grouping in Python for confluence calculation
    stocks_map = {}
    for signal, stock in query_results:
        if stock.symbol not in stocks_map:
            stocks_map[stock.symbol] = {
                "symbol": stock.symbol,
                "name": stock.name,
                "confluence_count": 0,
                "total_timeframes": 0,
                "daily_score": None,
                "rsi": None
            }
        
        if signal.is_bullish:
            stocks_map[stock.symbol]["confluence_count"] += 1
        
        stocks_map[stock.symbol]["total_timeframes"] += 1
        
        if signal.timeframe == 'D':
            stocks_map[stock.symbol]["daily_score"] = signal.entry_score
            stocks_map[stock.symbol]["rsi"] = signal.rsi

    # Format the confluence string and prepare for sorting
    final_results = []
    for symbol, data in stocks_map.items():
        data["confluence"] = f"{data['confluence_count']}/{data['total_timeframes']}"
        final_results.append(data)

    # Order by confluence count DESC, then daily score DESC
    final_results.sort(key=lambda x: (x["confluence_count"], x["daily_score"] or 0), reverse=True)

    return final_results[:50]
