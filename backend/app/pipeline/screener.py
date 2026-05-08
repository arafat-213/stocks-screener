import yfinance as yf
import time
import datetime
import logging
from sqlalchemy.orm import Session
from app.db.models import FundamentalCache, FundamentalData
from app.pipeline.utils import to_float, get_financial_row

logger = logging.getLogger(__name__)

CURRENT_SCREENER_VERSION = 1

DE_LIMITS = {
    "Financial Services": 10,
    "Insurance": 8,
    "Real Estate": 4,
    "Utilities": 3,
    "default": 2
}

def check_profitability_streak(financials) -> bool:
    """Checks if Net Income and Revenue are positive for last 3 years."""
    try:
        if financials is None or financials.empty or len(financials.columns) < 3: return False
        
        ni_row = get_financial_row(financials, "net_income")
        rev_row = get_financial_row(financials, "revenue")
        
        if ni_row is None or rev_row is None: return False
        
        # yf returns reverse chrono: iloc[0:3] are last 3 years
        for i in range(3):
            ni = to_float(ni_row.iloc[i], 0)
            rev = to_float(rev_row.iloc[i], 0)
            if ni <= 0 or rev <= 0: return False
        return True
    except Exception:
        return False

def fetch_and_cache_deep_fundamentals(symbols: list[str], db_session: Session):
    """Fetches financials and info for symbols in batches and caches them."""
    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        logger.info(f"Fetching Tier 2 data for batch: {batch}")
        
        for symbol in batch:
            try:
                ticker = yf.Ticker(f"{symbol}.NS")
                financials = ticker.financials
                info = ticker.info
                
                if not info:
                    logger.warning(f"No info found for {symbol}")
                    continue

                logger.info(f"Processing deep fundamentals for {symbol}")
                # Tier 2 Metrics
                profit_passed = check_profitability_streak(financials)
                
                # Scaffolding: Stub extraction calls for future expansion
                # We'll use these in Task 5 for advanced ratios
                get_financial_row(financials, "ebit")
                get_financial_row(ticker.balance_sheet, "total_assets")
                get_financial_row(ticker.balance_sheet, "current_liab")
                get_financial_row(ticker.cashflow, "op_cashflow")
                get_financial_row(ticker.cashflow, "capex")

                if not profit_passed:
                    logger.info(f"{symbol} failed 3-year profitability streak")
                
                sector = info.get('sector', 'default')
                de_limit = DE_LIMITS.get(sector, DE_LIMITS['default'])
                
                # yfinance debtToEquity is sometimes returned as percentage (e.g. 40.5 for 0.405x)
                # We normalize it to absolute value by dividing by 100 only if > 5.
                de_ratio = info.get('debtToEquity')
                de_check_passed = True
                if de_ratio is not None:
                    normalized_de = de_ratio / 100.0 if de_ratio > 5 else de_ratio
                    if normalized_de > de_limit:
                        de_check_passed = False
                        logger.info(f"{symbol} failed D/E check: {normalized_de} > {de_limit} (Sector: {sector})")
                else:
                    normalized_de = None

                pledged = info.get('pledgedPercent')
                pledged_missing = pledged is None
                
                # Update FundamentalCache
                cache_entry = db_session.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()
                if not cache_entry:
                    cache_entry = FundamentalCache(symbol=symbol)
                    db_session.add(cache_entry)
                
                cache_entry.profitability_streak_passed = profit_passed
                cache_entry.de_ratio = normalized_de
                cache_entry.de_check_passed = de_check_passed
                cache_entry.pledged_data_missing = pledged_missing
                cache_entry.sector = sector
                cache_entry.last_updated = datetime.datetime.utcnow()
                cache_entry.cache_version = CURRENT_SCREENER_VERSION
                
                # Update FundamentalData (latest snapshot)
                # We use today's date for the snapshot
                today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                fund_data = db_session.query(FundamentalData).filter(
                    FundamentalData.symbol == symbol,
                    FundamentalData.date == today
                ).first()
                
                if not fund_data:
                    fund_data = FundamentalData(symbol=symbol, date=today)
                    db_session.add(fund_data)
                
                fund_data.pe = info.get('trailingPE') or info.get('forwardPE')
                fund_data.pb = info.get('priceToBook')
                fund_data.roe = info.get('returnOnEquity')
                fund_data.debt_equity = normalized_de
                fund_data.eps_growth = info.get('earningsGrowth')
                fund_data.promoter_holding = info.get('heldPercentInsiders')
                fund_data.pledged_percent = pledged
                fund_data.market_cap = info.get('marketCap')
                
                db_session.commit()
                
            except Exception as e:
                logger.error(f"Failed Tier 2 fetch for {symbol}: {e}")
                db_session.rollback()
        
        if i + batch_size < len(symbols):
            logger.info("Batch complete. Sleeping for 1.0s...")
            time.sleep(1.0)

def passes_tier1_fast_filters(info: dict) -> tuple[bool, bool]:
    """Returns (passes_filter, should_flag_missing_pledge)"""
    if not info: return False, False
    
    # 1. Market Cap > ₹200 Cr
    mcap = to_float(info.get('marketCap'), 0)
    if mcap < 20_000_000_000: return False, False
    
    # 2. P/E (0 < pe < 300)
    pe = to_float(info.get('trailingPE') or info.get('forwardPE'))
    if pe is None or pe <= 0 or pe > 300: return False, False
    
    # 3. ROE & Promoter Pledge (Loosened - checks removed, but still flag missing pledge)
    pledged = to_float(info.get('pledgedPercent'))
    flag_missing = False
    if pledged is None:
        flag_missing = True
    
    # 5. Liquidity (value-based: 20-day avg vol * price > ₹2 Cr)
    avg_vol = to_float(info.get('averageVolume'), 0)
    price = to_float(info.get('currentPrice') or info.get('previousClose'), 0)
    if avg_vol * price < 20_000_000: return False, False
    
    return True, flag_missing
