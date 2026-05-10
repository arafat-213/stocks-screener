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

def request_pipeline_stop(db: Session):
    run = db.query(PipelineRun).filter(PipelineRun.status == "running").order_by(PipelineRun.timestamp.desc()).first()
    if run:
        run.stop_requested = True
        db.commit()
        logger.info(f"Pipeline stop requested for run {run.run_id}.")
    else:
        logger.warning("No running pipeline found to stop.")

def _is_stop_requested(db: Session, run_id: str) -> bool:
    # Refresh to get latest DB state
    db.expire_all()
    run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
    return run.stop_requested if run else False

def _compute_rs_ranks(db: Session, signal_date: datetime.date):
    """
    Computes RS percentile rank based on 12-month momentum against a benchmark.
    Uses bulk update for efficiency.
    """
    RS_BENCHMARK_CANDIDATES = ["^CRSLDX", "^NSEI"] # Nifty 500, Nifty 50
    benchmark_symbol = None
    benchmark_return = 0.0

    logger.info("Resolving RS benchmark candidate...")
    for candidate in RS_BENCHMARK_CANDIDATES:
        hist, _ = fetch_stock_data(candidate, append_ns=False, period="2y")
        if hist is not None and len(hist) >= 252:
            benchmark_symbol = candidate
            # 12-month return: (price_now / price_252_bars_ago - 1) * 100
            benchmark_return = (hist['Close'].iloc[-1] / hist['Close'].iloc[-252] - 1) * 100
            logger.info(f"Selected RS benchmark: {benchmark_symbol} with 12m return: {benchmark_return:.2f}%")
            break
    
    if not benchmark_symbol:
        logger.warning("No suitable RS benchmark found with enough history. Skipping RS computation.")
        return

    # Get all TechnicalSignals for signal_date and timeframe == 'D'
    signals = db.query(TechnicalSignal).filter(
        TechnicalSignal.date == signal_date,
        TechnicalSignal.timeframe == 'D'
    ).all()

    if not signals:
        logger.info(f"No signals found for {signal_date} to compute RS ranks.")
        return

    # Filter signals that have momentum_12m
    valid_signals = [s for s in signals if s.momentum_12m is not None]
    if not valid_signals:
        logger.info("No signals with 12m momentum found.")
        return

    # Sort signals by excess return (momentum_12m - benchmark_return)
    # Percentile = (Rank / Count) * 100
    valid_signals.sort(key=lambda x: (x.momentum_12m - benchmark_return))
    count = len(valid_signals)
    
    updates = []
    for i, s in enumerate(valid_signals):
        rank = ((i + 1) / count) * 100
        updates.append({"id": s.id, "rs_score": rank})
    
    if updates:
        db.bulk_update_mappings(TechnicalSignal, updates)
        db.commit()
        logger.info(f"Successfully updated RS scores (percentile ranks) for {len(updates)} stocks.")

def run_pipeline(db: Session, limit: int = None):
    # Secondary Concurrency Guard
    existing = db.query(PipelineRun).filter(PipelineRun.status == "running").first()
    if existing:
        logger.error(f"Cannot start pipeline: Run {existing.run_id} is already in progress.")
        return

    run = PipelineRun(
        status="running", 
        stocks_fetched=0, 
        stocks_scored=0, 
        tier1_count=0, 
        tier2_count=0, 
        errors="",
        stop_requested=False
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    
    current_symbol = "STARTUP"
    try:
        symbols = get_nse_symbols(limit=limit)
        if not symbols:
            raise ValueError("No symbols fetched")
            
        scored_count = 0
        fetched_count = 0
        
        # 1. Tier 1 Screening
        tier1_survivors = []
        hist_cache = {} # Temporary cache for hist data and info to avoid re-fetching
        
        logger.info(f"Starting Tier 1 screening for {len(symbols)} symbols")
        for symbol in symbols:
            if _is_stop_requested(db, run.run_id):
                logger.info("Pipeline stop signal received during scoring.")
                run.status = "stopped"
                run.errors = "Manually stopped during scoring"
                db.commit()
                return

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
        
        run.tier1_count = len(tier1_survivors)
        db.commit()
        logger.info(f"Tier 1 complete. {len(tier1_survivors)} survivors.")
        
        # MEMORY OPTIMIZATION: If survivors are many, clear hist_cache and re-fetch as needed
        use_lazy_loading = len(tier1_survivors) > 300
        if use_lazy_loading:
            logger.info("Survivors > 300. Clearing hist_cache to save memory (Lazy Loading enabled).")
            hist_cache.clear()

        # 2. Tier 2 Screening & Caching
        to_refresh = []
        seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        
        for symbol in tier1_survivors:
            if _is_stop_requested(db, run.run_id):
                logger.info("Pipeline stop signal received during Tier 2 check.")
                run.status = "stopped"
                run.errors = "Manually stopped during Tier 2"
                db.commit()
                return

            current_symbol = f"{symbol} (Tier 2 Check)"
            cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()
            
            if not cache or cache.last_updated < seven_days_ago or cache.cache_version < CURRENT_SCREENER_VERSION:
                to_refresh.append(symbol)
        
        if to_refresh:
            current_symbol = "BATCH_REFRESH"
            logger.info(f"Refreshing Tier 2 data for {len(to_refresh)} symbols")
            # Note: fetch_and_cache_deep_fundamentals doesn't currently check _STOP_SIGNAL internally
            # but it processes in batches of 50. For a true kill switch, we might want to pass signal there too.
            fetch_and_cache_deep_fundamentals(to_refresh, db)
        
        # 3. Final Filtering & Scoring
        logger.info("Applying Tier 2 filters and scoring")
        scored_at = datetime.datetime.utcnow()
        tier2_survivors_count = 0
        for symbol in tier1_survivors:
            scored_count += 1
            run.stocks_scored = scored_count
            if _is_stop_requested(db, run.run_id):
                logger.info("Pipeline stop signal received during scoring.")
                run.status = "stopped"
                run.errors = "Manually stopped during scoring"
                db.commit()
                return

            current_symbol = f"{symbol} (Scoring)"
            cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()
            
            # If still no cache or cache failed (version -1), skip
            if not cache or cache.cache_version == -1:
                continue
                
            tier2_survivors_count += 1
            # Score (MEMORY OPTIMIZATION: Re-fetch if hist_cache was cleared)
            cache_data = hist_cache.get(symbol)
            if cache_data is None:
                # Lazy load if cleared for memory
                hist, info = fetch_stock_data(symbol, period="3y")
                if hist is None or info is None:
                    continue
            else:
                hist, info = cache_data
            
            # Multi-timeframe loop
            for tf, freq in [('D', None), ('W', 'W'), ('M', 'ME')]:
                working_df = hist if tf == 'D' else resample_ohlcv(hist, freq)
                if working_df.empty: continue
                
                signal_date = working_df.index[-1].date()
                ta_data = calculate_combined_score(working_df, info, timeframe=tf, fund_cache=cache)
                
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
                signal.atr = ta_data.get('atr')
                
                # Momentum and New Technical Fields
                signal.momentum_1m = ta_data.get('momentum_1m')
                signal.momentum_3m = ta_data.get('momentum_3m')
                signal.momentum_6m = ta_data.get('momentum_6m')
                signal.momentum_12m = ta_data.get('momentum_12m')
                signal.adx = ta_data.get('adx')
                signal.above_200ema = ta_data.get('above_200ema')
                signal.ema_slope_20 = ta_data.get('ema_slope_20')
                signal.week52_high = ta_data.get('week52_high')
                signal.week52_low = ta_data.get('week52_low')
                signal.pct_from_52w_high = ta_data.get('pct_from_52w_high')
                signal.pct_from_52w_low = ta_data.get('pct_from_52w_low')
                signal.resistance_level = ta_data.get('resistance_level')
                signal.pct_from_resistance = ta_data.get('pct_from_resistance')
                signal.volume_breakout = ta_data.get('volume_breakout', False)
                
                signal.scored_at = scored_at
                
                # Capture price snapshots for Daily timeframe
                if tf == 'D' and len(working_df) >= 2:
                    signal.close_price = float(working_df['Close'].iloc[-1])
                    signal.price_change_pct = float(
                        (working_df['Close'].iloc[-1] - working_df['Close'].iloc[-2]) 
                        / working_df['Close'].iloc[-2] * 100
                    )
                
            if scored_count % 10 == 0:
                db.commit()
        
        run.tier2_count = tier2_survivors_count
        db.commit() # Ensure all signals are committed before RS computation

        if _is_stop_requested(db, run.run_id):
            run.status = "stopped"
            db.commit()
            return

        # 4. Market/Index Snapshots
        from app.db.models import MarketSnapshot
        
        # Derive signal_date from the same logic used in scoring loop
        final_signal_date = None
        if tier1_survivors:
            if tier1_survivors[0] in hist_cache:
                first_hist, _ = hist_cache[tier1_survivors[0]]
                final_signal_date = first_hist.index[-1].date()
            else:
                # Re-fetch just one to get the date if cache was cleared
                h, _ = fetch_stock_data(tier1_survivors[0], period="1d")
                if h is not None and not h.empty:
                    final_signal_date = h.index[-1].date()
        
        if not final_signal_date:
            final_signal_date = datetime.date.today()

        # 3b. Compute RS Ranks
        logger.info(f"Computing RS ranks for {final_signal_date}")
        _compute_rs_ranks(db, final_signal_date)

        indices = ["^NSEI", "^BSESN"]
        logger.info(f"Fetching market snapshots for {indices}")
        for idx in indices:
            hist, _ = fetch_stock_data(idx, append_ns=False, period="5d")
            if hist is not None and len(hist) >= 2:
                val = MarketSnapshot(
                    date=final_signal_date,
                    symbol=idx,
                    close=float(hist['Close'].iloc[-1]),
                    change_pct=float((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100)
                )
                db.merge(val) # Upsert
        db.commit()

        # 5. Generate Daily Report
        logger.info("Generating daily report")
        generate_daily_report(db)

        # 6. Materialize Named Screens
        from app.screens.materializer import materialize_all_screens
        materialize_all_screens(db)
            
        run.status = "complete"
        run.stocks_fetched = fetched_count
        run.stocks_scored = scored_count
        db.commit()
        
    except Exception as e:
        if _is_stop_requested(db, run.run_id):
            run.status = "stopped"
            run.errors = "Stopped during exception"
        else:
            error_msg = f"Failed at {current_symbol}: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"Pipeline failed: {error_msg}")
            db.rollback()
            run.status = "failed"
            run.errors = error_msg
        db.commit()

