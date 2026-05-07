from sqlalchemy.orm import Session
from app.db.models import Stock, TechnicalSignal, FundamentalData, PipelineRun, FundamentalCache
from app.pipeline.fetcher import get_nse_symbols, fetch_stock_data
from app.pipeline.screener import (
    passes_tier1_fast_filters, 
    fetch_and_cache_deep_fundamentals,
    CURRENT_SCREENER_VERSION
)
from app.pipeline.scorer import calculate_combined_score
from app.pipeline.utils import resample_ohlcv
from app.pipeline.reporter import generate_daily_report
import datetime
import logging
import traceback

logger = logging.getLogger(__name__)

def run_pipeline(db: Session):
    run = PipelineRun(status="running", stocks_fetched=0, stocks_scored=0, errors="")
    db.add(run)
    db.commit()
    
    current_symbol = "STARTUP"
    try:
        symbols = get_nse_symbols()
        if not symbols:
            raise ValueError("No symbols fetched")
            
        scored_count = 0
        fetched_count = 0
        
        # 1. Tier 1 Screening
        tier1_survivors = []
        hist_cache = {} # Temporary cache for hist data and info to avoid re-fetching
        
        logger.info(f"Starting Tier 1 screening for {len(symbols)} symbols")
        for symbol in symbols:
            current_symbol = symbol
            hist, info = fetch_stock_data(symbol, period="3y")
            fetched_count += 1
            
            if hist is None or info is None:
                # Update progress even if fetch failed
                if fetched_count % 50 == 0:
                    run.stocks_fetched = fetched_count
                    db.commit()
                continue
            
            # Upsert Stock Info
            stock = db.query(Stock).filter(Stock.symbol == symbol).first()
            if not stock:
                stock = Stock(symbol=symbol, name=info.get('longName', symbol), sector=info.get('sector', ''), industry=info.get('industry', ''), market_cap=info.get('marketCap', 0))
                db.add(stock)
            else:
                stock.market_cap = info.get('marketCap', 0)
            
            passes_t1, flag_missing_pledge = passes_tier1_fast_filters(info)
            if passes_t1:
                tier1_survivors.append(symbol)
                hist_cache[symbol] = (hist, info)
            
            # Periodically commit to keep DB updated with stock info and progress
            if fetched_count % 50 == 0:
                run.stocks_fetched = fetched_count
                db.commit()
        
        db.commit()
        logger.info(f"Tier 1 complete. {len(tier1_survivors)} survivors.")
        
        # 2. Tier 2 Screening & Caching
        to_refresh = []
        seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        
        for symbol in tier1_survivors:
            current_symbol = f"{symbol} (Tier 2 Check)"
            cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()
            
            if not cache or cache.last_updated < seven_days_ago or cache.cache_version < CURRENT_SCREENER_VERSION:
                to_refresh.append(symbol)
        
        if to_refresh:
            current_symbol = "BATCH_REFRESH"
            logger.info(f"Refreshing Tier 2 data for {len(to_refresh)} symbols")
            fetch_and_cache_deep_fundamentals(to_refresh, db)
        
        # 3. Final Filtering & Scoring
        logger.info("Applying Tier 2 filters and scoring")
        scored_at = datetime.datetime.utcnow()
        for symbol in tier1_survivors:
            current_symbol = f"{symbol} (Scoring)"
            cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()
            
            # If still no cache (fetch failed), skip
            if not cache:
                continue
                
            # Tier 2 Filters
            if not cache.profitability_streak_passed or not cache.de_check_passed:
                continue
            
            # Score
            cache_data = hist_cache.get(symbol)
            if cache_data is None: # Should not happen if in survivors
                continue
            
            hist, info = cache_data
            
            # Multi-timeframe loop
            for tf, freq in [('D', None), ('W', 'W-FRI'), ('M', 'ME')]:
                working_df = hist if tf == 'D' else resample_ohlcv(hist, freq)
                if working_df.empty: continue
                
                signal_date = working_df.index[-1].date()
                ta_data = calculate_combined_score(working_df, info, timeframe=tf)
                
                # Explicit Upsert into TechnicalSignal
                signal = db.query(TechnicalSignal).filter_by(
                    symbol=symbol, date=signal_date, timeframe=tf
                ).first()
                if not signal:
                    signal = TechnicalSignal(symbol=symbol, date=signal_date, timeframe=tf)
                    db.add(signal)
                
                signal.entry_score = ta_data['score']
                signal.is_bullish = ta_data['is_bullish']
                signal.rsi = ta_data['rsi']
                signal.macd = ta_data['macd']
                signal.ema_signal = ta_data['ema_signal']
                signal.volume_signal = ta_data.get('volume_signal', 'neutral')
                signal.rsi_signal = ta_data.get('rsi_signal', 'neutral')
                signal.scored_at = scored_at
                
            scored_count += 1
            if scored_count % 10 == 0:
                db.commit()
        
        # 4. Generate Daily Report
        logger.info("Generating daily report")
        generate_daily_report(db)
            
        run.status = "complete"
        run.stocks_fetched = fetched_count
        run.stocks_scored = scored_count
        db.commit()
        
    except Exception as e:
        error_msg = f"Failed at {current_symbol}: {str(e)}\n{traceback.format_exc()}"
        logger.error(f"Pipeline failed: {error_msg}")
        db.rollback()
        run.status = "failed"
        run.errors = error_msg
        db.commit()
