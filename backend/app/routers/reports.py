from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from app.db.session import get_db
from app.db.models import Stock, TechnicalSignal
from datetime import datetime
from pathlib import Path
import json

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.get("/digest/latest")
def get_latest_digest():
    reports_dir = Path(__file__).resolve().parent.parent.parent / "reports"
    digests = sorted(reports_dir.glob("digest_*.json"), reverse=True)
    if not digests:
        raise HTTPException(status_code=404, detail="No digest found")
    try:
        return json.loads(digests[0].read_text())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading digest: {e}")

@router.get("/digest/{date}")
def get_digest_by_date(date: str):
    reports_dir = Path(__file__).resolve().parent.parent.parent / "reports"
    path = reports_dir / f"digest_{date}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Digest not found for this date")
    try:
        return json.loads(path.read_text())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading digest: {e}")

@router.get("")
def list_reports(db: Session = Depends(get_db)):
    # Get unique dates from technical_signals table, using func.date to remove time component
    dates = db.query(func.distinct(func.date(TechnicalSignal.date))).\
        order_by(func.date(TechnicalSignal.date).desc()).all()
    return [d[0] for d in dates if d[0]]

@router.get("/latest")
def get_latest_report(db: Session = Depends(get_db)):
    # Find the most recent date in the technical_signals table
    max_date = db.query(func.max(TechnicalSignal.date)).scalar()
    if not max_date:
        return []
    
    # If it's a string (SQLite might return it as such), just take the date part
    if isinstance(max_date, str):
        date_str = max_date.split(' ')[0]
    else:
        date_str = max_date.strftime("%Y-%m-%d")
        
    return get_report_by_date(date_str, db)

@router.get("/{date}")
def get_report_by_date(date: str, db: Session = Depends(get_db)):
    try:
        # Validate format
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Join TechnicalSignal with Stock
    query_results = db.query(TechnicalSignal, Stock).\
        join(Stock, TechnicalSignal.symbol == Stock.symbol).\
        filter(func.date(TechnicalSignal.date) == date).all()

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

