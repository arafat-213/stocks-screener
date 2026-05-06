from sqlalchemy.orm import Session
from app.db.models import Stock, DailyScore, FundamentalData, PipelineRun
from app.pipeline.fetcher import get_nse_symbols, fetch_stock_data
from app.pipeline.screener import passes_fundamental_filters
from app.pipeline.scorer import calculate_technical_score
import datetime
import logging

logger = logging.getLogger(__name__)

def run_pipeline(db: Session):
    run = PipelineRun(status="running", stocks_fetched=0, stocks_scored=0, errors="")
    db.add(run)
    db.commit()
    
    try:
        symbols = get_nse_symbols()
        if not symbols:
            raise ValueError("No symbols fetched")
            
        scored_count = 0
        fetched_count = 0
        
        for symbol in symbols:
            hist, info = fetch_stock_data(symbol)
            fetched_count += 1
            
            if hist is None or info is None:
                continue
                
            # Upsert Stock Info
            stock = db.query(Stock).filter(Stock.symbol == symbol).first()
            if not stock:
                stock = Stock(symbol=symbol, name=info.get('longName', symbol), sector=info.get('sector', ''), industry=info.get('industry', ''), market_cap=info.get('marketCap', 0))
                db.add(stock)
            
            # Screen
            if not passes_fundamental_filters(info):
                continue
                
            # Score
            ta_data = calculate_technical_score(hist)
            scored_count += 1
            
            # Persist Score
            score_entry = db.query(DailyScore).filter(DailyScore.symbol == symbol, DailyScore.date == datetime.datetime.utcnow().date()).first()
            if not score_entry:
                score_entry = DailyScore(symbol=symbol, date=datetime.datetime.utcnow().date())
                db.add(score_entry)
            
            score_entry.entry_score = ta_data['score']
            score_entry.rsi = ta_data['rsi']
            score_entry.macd = ta_data['macd']
            score_entry.ema_signal = ta_data['ema_signal']
            score_entry.volume_signal = ta_data['volume_signal']
            
            db.commit()
            
        run.status = "complete"
        run.stocks_fetched = fetched_count
        run.stocks_scored = scored_count
        db.commit()
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        run.status = "failed"
        run.errors = str(e)
        db.commit()
