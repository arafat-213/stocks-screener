import logging
from app.core.logging_manager import logging_manager
from sqlalchemy.orm import Session
from app.db.models import (
    Stock, TechnicalSignal, FundamentalData, PipelineRun, 
    FundamentalCache, PipelineCheckpoint, PipelineError
)
from app.pipeline.fetcher import (
    get_nse_symbols, fetch_stock_data, fetch_market_snapshots,
    pipeline_session, slice_bulk_df
)
from app.pipeline.screener import (
    passes_tier1_fast_filters, 
    fetch_and_cache_deep_fundamentals,
    needs_cache_refresh,
    CURRENT_SCREENER_VERSION
)
from app.pipeline.scorer import calculate_combined_score
from app.pipeline.utils import resample_ohlcv
from app.pipeline.reporter import generate_daily_report
from app.pipeline.errors import classify_error
from app.pipeline.rs_ranks import compute_rs_ranks
from app.core.cache import response_cache
from app.screens.cache import screen_cache
from app.pipeline.ohlcv_cache import OHLCVCache
import datetime
import traceback
import json
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

_ohlcv_cache = OHLCVCache()

def request_pipeline_stop(db: Session):
    run = db.query(PipelineRun).filter(PipelineRun.status == "running").order_by(PipelineRun.timestamp.desc()).first()
    if run:
        if run.stop_requested:
            # Second stop request acts as a force-stop
            run.status = "stopped"
            run.errors = "Force stopped by user (Double-stop)"
            db.commit()
            logger.info(f"Pipeline FORCE stopped for run {run.run_id}.")
        else:
            run.stop_requested = True
            db.commit()
            logger.info(f"Pipeline stop requested for run {run.run_id}. Send another stop request to force-fail if it doesn't respond.")
    else:
        logger.warning("No running pipeline found to stop.")

def cleanup_zombie_runs(db: Session):
    """Mark any runs stuck in 'running' state as failed/interrupted on startup."""
    zombies = db.query(PipelineRun).filter(PipelineRun.status == "running").all()
    if zombies:
        logger.info(f"Cleaning up {len(zombies)} zombie pipeline runs.")
        zombie_ids = [run.run_id for run in zombies]
        for run in zombies:
            run.status = "failed"
            run.errors = "Interrupted by system restart or crash"
        
        # Also clear checkpoints for zombie runs so they don't block a fresh resume
        db.query(PipelineCheckpoint).filter(
            PipelineCheckpoint.run_id.in_(zombie_ids)
        ).delete(synchronize_session=False)
        db.commit()

def _is_stop_requested(db: Session, run_id: str) -> bool:
    # Refresh to get latest DB state
    db.expire_all()
    run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
    return run.stop_requested if run else False

def _get_completed_symbols(db: Session, run_id: str, phase: str) -> set:
    checkpoint = db.query(PipelineCheckpoint).filter_by(run_id=run_id, phase=phase).first()
    if checkpoint and checkpoint.completed_symbols:
        try:
            return set(json.loads(checkpoint.completed_symbols))
        except Exception:
            return set()
    return set()

def _save_checkpoint(db: Session, run_id: str, phase: str, symbols: set):
    checkpoint = db.query(PipelineCheckpoint).filter_by(run_id=run_id, phase=phase).first()
    if not checkpoint:
        checkpoint = PipelineCheckpoint(run_id=run_id, phase=phase, started_at=datetime.datetime.utcnow())
        db.add(checkpoint)
    checkpoint.completed_symbols = json.dumps(list(symbols))
    checkpoint.completed_at = datetime.datetime.utcnow()
    db.commit()

def _log_pipeline_error(db: Session, run_id: str, symbol: str, phase: str, e: Exception):
    error_type = classify_error(e)
    p_error = PipelineError(
        run_id=run_id,
        symbol=symbol,
        phase=phase,
        error_type=error_type,
        message=str(e),
        traceback=traceback.format_exc()
    )
    db.add(p_error)
    db.commit()

def process_symbol(symbol: str, db: Session, hist: pd.DataFrame = None, info: dict = None, cache: FundamentalCache = None, scored_at: datetime.datetime = None):
    """
    Processes a single symbol across all timeframes and saves TechnicalSignals.
    Returns a list of created/updated TechnicalSignal objects.
    """
    if hist is None:
        from app.pipeline.fetcher import fetch_stock_data
        hist, fetched_info = fetch_stock_data(symbol, period="3y")
        if info is None:
            info = fetched_info
        if hist is None or hist.empty:
            return []

    if scored_at is None:
        scored_at = datetime.datetime.utcnow()

    signals = []
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
        
        # EMA Levels
        signal.ema5_level = ta_data.get('ema5_level')
        signal.ema13_level = ta_data.get('ema13_level')
        signal.ema20_level = ta_data.get('ema20_level')
        signal.ema26_level = ta_data.get('ema26_level')
        
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
        
        # Consolidation check (requiresRaw OHLCV)
        if tf == 'D' and len(working_df) >= 17: # lookback(15) + buffer
            from app.backtest.engine import _is_consolidating
            signal.is_consolidating = _is_consolidating(
                working_df, 
                len(working_df) - 1, 
                lookback=15, 
                max_range_pct=12.0
            )
        
        signal.scored_at = scored_at
        
        # Capture price snapshots for Daily timeframe
        if tf == 'D' and len(working_df) >= 2:
            signal.close_price = float(working_df['Close'].iloc[-1])
            signal.price_change_pct = float(
                (working_df['Close'].iloc[-1] - working_df['Close'].iloc[-2]) 
                / working_df['Close'].iloc[-2] * 100
            )
        signals.append(signal)
    return signals

def run_pipeline(db: Session, limit: int = None, resume_run_id: str | None = None):
    if resume_run_id:
        run = db.query(PipelineRun).filter(PipelineRun.run_id == resume_run_id).first()
        if not run:
            logger.error(f"Cannot resume: Run {resume_run_id} not found.")
            return
        if run.status == "running":
            logger.error(f"Cannot resume: Run {resume_run_id} is already in progress.")
            return
        run.status = "running"
        run.stop_requested = False
        db.commit()
        logger.info(f"Resuming pipeline run {resume_run_id}")
    else:
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
    
    logging_manager.setup_run_logging(str(run.run_id))
    
    current_symbol = "STARTUP"
    try:
        symbols = get_nse_symbols(limit=limit)
        if not symbols:
            raise ValueError("No symbols fetched")
            
        run.total_symbols = len(symbols)
        db.commit()
            
        # 1. Tier 1 Screening (Bulk Download + Technical Filter)
        completed_t1 = _get_completed_symbols(db, run.run_id, "tier1")
        tier1_survivors = list(_get_completed_symbols(db, run.run_id, "tier1_survivors"))
        
        fetched_count = run.stocks_fetched
        batch_size = 100
        remaining_symbols = [s for s in symbols if s not in completed_t1]
        
        logger.info(f"Starting Tier 1 screening for {len(remaining_symbols)} remaining symbols (Batch size: {batch_size})")
        
        for i in range(0, len(remaining_symbols), batch_size):
            # Use a fresh check to avoid session caching issues
            db.expire_all()
            if _is_stop_requested(db, run.run_id):
                logger.info("Pipeline stop signal received during Tier 1.")
                run.status = "stopped"
                run.errors = "Manually stopped during Tier 1"
                db.commit()
                return

            batch = remaining_symbols[i:i+batch_size]
            batch_ns = [s + ".NS" for s in batch]
            
            logger.info(f"Downloading Tier 1 batch {i//batch_size + 1}: {len(batch)} symbols")
            try:
                # Add a timeout via proxy/session if needed, but smaller batches are better.
                # yfinance download doesn't have a clean timeout param for the whole operation.
                bulk_data = yf.download(batch_ns, period="3y", progress=False, timeout=30, auto_adjust=False)
                
                for symbol in batch:
                    try:
                        current_symbol = symbol
                        hist = slice_bulk_df(bulk_data, symbol)
                        fetched_count += 1
                        
                        if hist is not None and not hist.empty:
                            # Technical-only scoring (passing None for info triggers tech-only)
                            # Tier 1 is a wide net: any technically bullish stock OR score > 40/70 (57%) passes.
                            # We intentionally cast wide here to avoid missing good setups due to a single weak indicator.
                            scores = calculate_combined_score(hist, None)
                            if scores['is_bullish'] or scores['combined_score'] > 40:
                                tier1_survivors.append(symbol)
                        
                        completed_t1.add(symbol)
                    except Exception as e:
                        logger.warning(f"Error processing {symbol} in Tier 1: {e}")
                        _log_pipeline_error(db, run.run_id, symbol, "tier1", e)
                        completed_t1.add(symbol) # Skip next time
                
                # Periodically update run and checkpoints
                run.stocks_fetched = fetched_count
                _save_checkpoint(db, run.run_id, "tier1", completed_t1)
                _save_checkpoint(db, run.run_id, "tier1_survivors", set(tier1_survivors))
                db.commit()
                
            except Exception as e:
                logger.error(f"Error processing batch {i} in Tier 1: {e}")
                _log_pipeline_error(db, run.run_id, f"BATCH_{i}", "tier1", e)
                # We don't mark symbols as completed if the whole batch failed to allow retry
        
        run.stocks_fetched = fetched_count
        _save_checkpoint(db, run.run_id, "tier1", completed_t1)
        _save_checkpoint(db, run.run_id, "tier1_survivors", set(tier1_survivors))
        db.commit()
        logger.info(f"Tier 1 complete. {len(tier1_survivors)} technical survivors.")
        
        # 1.5 Tier 1.5 (Surgical Liquidity Check & Metadata Update)
        completed_t15 = _get_completed_symbols(db, run.run_id, "tier1.5")
        final_survivors = list(_get_completed_symbols(db, run.run_id, "final_survivors"))
        
        remaining_t15 = [s for s in tier1_survivors if s not in completed_t15]
        if remaining_t15:
            logger.info(f"Starting Tier 1.5 liquidity check for {len(remaining_t15)} remaining symbols")
            for symbol in remaining_t15:
                if _is_stop_requested(db, run.run_id):
                    logger.info("Pipeline stop signal received during Tier 1.5.")
                    run.status = "stopped"
                    db.commit()
                    return

                try:
                    current_symbol = f"{symbol} (Tier 1.5)"
                    ticker = yf.Ticker(symbol + ".NS")
                    fi = ticker.fast_info
                    
                    # fast_info can return None for some fields on certain stocks
                    mcap = fi.get('marketCap') or 0
                    avg_vol = fi.get('threeMonthAverageVolume') or fi.get('lastVolume') or 0
                    price = fi.get('lastPrice') or 0
                    
                    # Liquidity Filter: Mcap > 200 Cr, Value > 2 Cr
                    if mcap > 200_000_000 and (avg_vol * price > 2_000_000):
                        # Metadata Update (requires .info)
                        info = ticker.info
                        stock = db.query(Stock).filter_by(symbol=symbol).first()
                        if not stock:
                            stock = Stock(symbol=symbol)
                            db.add(stock)
                        
                        stock.name = info.get('longName') or info.get('shortName')
                        stock.sector = info.get('sector')
                        stock.industry = info.get('industry')
                        stock.market_cap = mcap
                        final_survivors.append(symbol)
                    
                    completed_t15.add(symbol)
                    if len(completed_t15) % 50 == 0:
                        _save_checkpoint(db, run.run_id, "tier1.5", completed_t15)
                        _save_checkpoint(db, run.run_id, "final_survivors", set(final_survivors))
                        db.commit()
                except Exception as e:
                    logger.warning(f"Error in Tier 1.5 for {symbol}: {e}")
                    _log_pipeline_error(db, run.run_id, symbol, "tier1.5", e)
                    completed_t15.add(symbol)
            
            _save_checkpoint(db, run.run_id, "tier1.5", completed_t15)
            _save_checkpoint(db, run.run_id, "final_survivors", set(final_survivors))
            run.tier1_count = len(final_survivors)
            db.commit()
            logger.info(f"Tier 1.5 complete. {len(final_survivors)} final survivors.")
        else:
            run.tier1_count = len(final_survivors)
            db.commit()

        # 2. Tier 2 Screening & Caching
        to_refresh = []
        seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        
        completed_t2 = _get_completed_symbols(db, run.run_id, "tier2")
        
        for symbol in final_survivors:
            if symbol in completed_t2:
                continue

            if _is_stop_requested(db, run.run_id):
                logger.info("Pipeline stop signal received during Tier 2 check.")
                run.status = "stopped"
                run.errors = "Manually stopped during Tier 2"
                db.commit()
                return

            current_symbol = f"{symbol} (Tier 2 Check)"
            cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()
            
            if needs_cache_refresh(cache, seven_days_ago):
                to_refresh.append(symbol)
            else:
                completed_t2.add(symbol)
        
        if to_refresh:
            current_symbol = "BATCH_REFRESH"
            logger.info(f"Refreshing Tier 2 data for {len(to_refresh)} symbols")
            # We refresh in smaller batches to allow resumption if it fails deep in Tier 2
            t2_batch_size = 50
            for i in range(0, len(to_refresh), t2_batch_size):
                batch = to_refresh[i:i+t2_batch_size]
                if _is_stop_requested(db, run.run_id):
                    break
                fetch_and_cache_deep_fundamentals(batch, db)
                for s in batch: completed_t2.add(s)
                _save_checkpoint(db, run.run_id, "tier2", completed_t2)
        
        # 3. Final Filtering & Scoring
        logger.info("Applying Tier 2 filters and scoring")
        scored_at = datetime.datetime.utcnow()
        tier2_survivors_count = 0
        scored_count = run.stocks_scored
        completed_scoring = _get_completed_symbols(db, run.run_id, "scoring")

        for symbol in final_survivors:
            if symbol in completed_scoring:
                scored_count += 1
                tier2_survivors_count += 1 # We assume completed means they were survivors
                continue

            if _is_stop_requested(db, run.run_id):
                logger.info("Pipeline stop signal received during scoring.")
                run.status = "stopped"
                run.errors = "Manually stopped during scoring"
                db.commit()
                return

            current_symbol = f"{symbol} (Scoring)"
            try:
                cache = db.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()
                
                # Even if cache fetch failed (version -1) or missing, we still score technically.
                # Pass cache=None to process_symbol so fund_score defaults to 0.
                tier2_survivors_count += 1
                scoring_cache = None
                if cache and cache.cache_version != -1:
                    scoring_cache = cache
                
                # Score using persistent OHLCV cache
                hist = _ohlcv_cache.get(symbol, append_ns=True, period="3y")
                if hist is None:
                    completed_scoring.add(symbol)
                    continue
                
                info = None # Info is handled via FundamentalCache now
                process_symbol(symbol, db, hist=hist, info=info, cache=scoring_cache, scored_at=scored_at)
                
                scored_count += 1
                completed_scoring.add(symbol)
                if scored_count % 25 == 0:
                    run.stocks_scored = scored_count
                    _save_checkpoint(db, run.run_id, "scoring", completed_scoring)
            except Exception as e:
                logger.warning(f"Error scoring {symbol}: {e}")
                _log_pipeline_error(db, run.run_id, symbol, "scoring", e)
                completed_scoring.add(symbol)
        
        run.stocks_scored = scored_count
        run.tier2_count = tier2_survivors_count
        _save_checkpoint(db, run.run_id, "scoring", completed_scoring)
        db.commit() # Ensure all signals are committed before RS computation

        if _is_stop_requested(db, run.run_id):
            run.status = "stopped"
            db.commit()
            return

        # 4. Market/Index Snapshots
        from app.db.models import MarketSnapshot
        
        # Derive signal_date from the same logic used in scoring loop
        final_signal_date = None
        # Use final_survivors as they are the ones actually processed in Tier 2/Scoring
        if final_survivors:
            first_hist = _ohlcv_cache.get(final_survivors[0], append_ns=True, period="3y")
            if first_hist is not None and not first_hist.empty:
                final_signal_date = first_hist.index[-1].date()
        
        if not final_signal_date:
            final_signal_date = datetime.date.today()

        # 3b. Compute RS Ranks
        logger.info(f"Computing RS ranks for {final_signal_date}")
        compute_rs_ranks(db, final_signal_date)

        # 3c. Compute sector rotation aggregates
        from app.screens.sector_rotation import compute_sector_rotation
        logger.info("Computing sector rotation snapshots")
        compute_sector_rotation(db)

        indices = ["^NSEI", "^BSESN"]
        logger.info(f"Fetching market snapshots for {indices}")
        snapshots = fetch_market_snapshots(indices)
        for snap in snapshots:
            val = MarketSnapshot(
                date=final_signal_date,
                symbol=snap["symbol"],
                close=snap["close"],
                change_pct=snap["change_pct"]
            )
            db.merge(val) # Upsert
        db.commit()

        # 5. Generate Daily Report
        logger.info("Generating daily report")
        generate_daily_report(db)

        # 5b. Generate Signal Digest (Forward Validation)
        try:
            from app.pipeline.signal_digest import generate_signal_digest
            digest_path = generate_signal_digest(db)
            logger.info("Signal digest generated at %s", digest_path)
        except Exception as e:
            logger.error("Failed to generate signal digest: %s", e)

        # 6. Materialize Named Screens
        from app.screens.materializer import materialize_all_screens
        materialize_all_screens(db)

        # 7. Paper Trading (REMOVED - replaced by Signal Digest)
        # try:
        #     from app.paper_trading.engine import run_paper_trading_cycle
        #     pt_result = run_paper_trading_cycle(db)
        #     logger.info("Paper trading cycle result: %s", pt_result)
        # except Exception as e:
        #     logger.error("Paper trading cycle failed (non-fatal): %s", e)
        #     import traceback
        #     logger.error(traceback.format_exc())

        # 8. Alert cycle — fires email for new actionable signals
        try:
            from app.alerts.engine import run_alert_cycle, run_exit_alert_cycle
            # Entry alerts — new signals
            alert_result = run_alert_cycle(db, signal_date=final_signal_date)
            logger.info("Entry alert cycle: %s", alert_result)

            # Exit alerts — open positions
            exit_result = run_exit_alert_cycle(db, signal_date=final_signal_date)
            logger.info("Exit alert cycle: %s", exit_result)
        except Exception as e:
            logger.error("Alert cycle failed (non-fatal): %s", e)
            import traceback
            logger.error(traceback.format_exc())

        run.status = "complete"

        run.stocks_fetched = fetched_count
        run.stocks_scored = scored_count
        db.commit()

        # Invalidate all caches on success
        logger.info("Invalidating response and screens caches after successful pipeline run.")
        response_cache.invalidate()
        screen_cache.invalidate()
        
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
    finally:
        logging_manager.cleanup_run_logging()
