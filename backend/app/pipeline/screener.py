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

def needs_cache_refresh(cache, seven_days_ago: datetime.datetime) -> bool:
    """Checks if FundamentalCache entry needs refreshing based on age, version or force flag."""
    if not cache: return True
    if getattr(cache, 'force_refresh', False): return True
    
    # Version check
    if (getattr(cache, 'cache_version', 0) or 0) < CURRENT_SCREENER_VERSION: return True
    
    # Backoff check (Takes precedence over age)
    retry_after = getattr(cache, 'retry_after', None)
    if retry_after and datetime.datetime.utcnow() < retry_after:
        return False
        
    # Age check
    last_upd = getattr(cache, 'last_updated', None)
    if not last_upd or last_upd < seven_days_ago: return True
    
    return False

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

import random

from app.pipeline.fetcher import pipeline_session as yf_session
from app.pipeline.errors import classify_error

def fetch_and_cache_deep_fundamentals(symbols: list[str], db_session: Session):
    """Fetches financials and info for symbols in batches and caches them with retries."""
    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        logger.info(f"Fetching Tier 2 data for batch: {batch}")
        
        for symbol in batch:
            cache_version = CURRENT_SCREENER_VERSION
            success = False
            max_retries = 1
            
            # 1. Get/Create Cache Entry
            cache_entry = db_session.query(FundamentalCache).filter(FundamentalCache.symbol == symbol).first()
            if not cache_entry:
                cache_entry = FundamentalCache(symbol=symbol)
                db_session.add(cache_entry)

            for attempt in range(max_retries):
                try:
                    ticker = yf.Ticker(f"{symbol}.NS", session=yf_session)
                    # Force fetch of multiple attributes to trigger potential API errors early
                    info = ticker.info
                    financials = ticker.financials
                    balance_sheet = ticker.balance_sheet
                    cashflow = ticker.cashflow
                    
                    if not info:
                        logger.warning(f"No info found for {symbol}")
                        cache_entry.last_error = "Empty info from yfinance"
                        break # Don't retry if info is explicitly empty

                    logger.info(f"Processing deep fundamentals for {symbol}")
                    
                    # 1. ROCE: EBIT / (Total Assets - Current Liabilities)
                    ebit_row = get_financial_row(financials, "ebit")
                    assets_row = get_financial_row(balance_sheet, "total_assets")
                    liab_row = get_financial_row(balance_sheet, "current_liab")
                    
                    roce = None
                    if ebit_row is not None and assets_row is not None and liab_row is not None:
                        try:
                            ebit = to_float(ebit_row.iloc[0], 0)
                            assets = to_float(assets_row.iloc[0], 0)
                            liab = to_float(liab_row.iloc[0], 0)
                            capital_employed = assets - liab
                            if capital_employed > 0:
                                roce = ebit / capital_employed
                        except (IndexError, ZeroDivisionError):
                            pass
                    
                    # 2. PEG: PE / (Growth * 100)
                    pe = to_float(info.get('trailingPE'))
                    growth = to_float(info.get('earningsGrowth'))
                    peg = None
                    if pe and growth and pe > 0 and growth > 0:
                        peg = pe / (growth * 100.0)
                        
                    # 3. FCF: Op Cash Flow - CapEx
                    ocf_row = get_financial_row(cashflow, "op_cashflow")
                    capex_row = get_financial_row(cashflow, "capex")
                    fcf = None
                    p_fcf = None
                    if ocf_row is not None and capex_row is not None:
                        try:
                            ocf = to_float(ocf_row.iloc[0], 0)
                            # CapEx is often reported as negative in yfinance cashflow
                            capex = abs(to_float(capex_row.iloc[0], 0))
                            fcf = ocf - capex
                            
                            mcap = to_float(info.get('marketCap'))
                            if mcap and fcf and fcf > 0:
                                p_fcf = mcap / fcf
                        except IndexError:
                            pass
                            
                    # 4. Dividend Consistency (Current-1, Current-2, Current-3)
                    div_consistency = False
                    try:
                        divs = ticker.dividends
                        if not divs.empty:
                            years = set(d.year for d in divs.index)
                            current_year = datetime.date.today().year
                            required_years = {current_year - 1, current_year - 2, current_year - 3}
                            if required_years.issubset(years):
                                div_consistency = True
                    except Exception:
                        pass
                        
                    # 5. Market Cap Category
                    mcap_val = to_float(info.get('marketCap'), 0)
                    # Convert to Cr (assuming mcap is in absolute INR)
                    mcap_cr = mcap_val / 10_000_000
                    if mcap_cr > 20000:
                        mcap_cat = "largecap"
                    elif mcap_cr >= 5000:
                        mcap_cat = "midcap"
                    else:
                        mcap_cat = "smallcap"
                    
                    success = True
                    break
                    
                except Exception as e:
                    error_type = classify_error(e)
                    cache_entry.last_error = f"{error_type}: {str(e)}"
                    cache_entry.fetch_attempts = (cache_entry.fetch_attempts or 0) + 1
                    
                    # Backoff logic
                    now = datetime.datetime.utcnow()
                    if error_type == "rate_limit":
                        cache_entry.retry_after = now + datetime.timedelta(hours=6)
                    elif error_type == "empty_data" and cache_entry.fetch_attempts >= 3:
                        cache_entry.retry_after = now + datetime.timedelta(hours=24)
                    else:
                        cache_entry.retry_after = now + datetime.timedelta(hours=2)
                    
                    db_session.commit()

                    wait_time = (2 ** attempt) + random.uniform(0, 0.5)
                    logger.error(f"Attempt {attempt+1} failed for {symbol}: {e}. Retrying in {wait_time:.2f}s...")
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All retries failed for {symbol}")
                        cache_version = -1
            
            try:
                # Update FundamentalCache (even if failed, to mark as attempted)
                cache_entry.last_updated = datetime.datetime.utcnow()
                cache_entry.cache_version = cache_version

                if not success:
                    db_session.commit()
                    continue

                # Reset failure state on success
                cache_entry.fetch_attempts = 0
                cache_entry.retry_after = None
                cache_entry.last_error = None
                cache_entry.force_refresh = False

                # Tier 2 Metrics
                profit_passed = check_profitability_streak(financials)
                
                sector = info.get('sector', 'default')
                de_limit = DE_LIMITS.get(sector, DE_LIMITS['default'])
                
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
                
                cache_entry.profitability_streak_passed = profit_passed
                cache_entry.de_ratio = normalized_de
                cache_entry.de_check_passed = de_check_passed
                cache_entry.pledged_data_missing = pledged_missing
                cache_entry.sector = sector
                
                # Advanced Metrics
                cache_entry.roce = roce
                cache_entry.roe = to_float(info.get('returnOnEquity'))
                cache_entry.peg_ratio = peg
                cache_entry.ev_to_ebitda = to_float(info.get('enterpriseToEbitda'))
                cache_entry.dividend_yield = to_float(info.get('dividendYield'))
                cache_entry.price_to_fcf = p_fcf
                cache_entry.dividend_consistency = div_consistency
                cache_entry.market_cap_category = mcap_cat
                cache_entry.fcf_positive = (fcf > 0) if fcf is not None else None
                
                # Update FundamentalData (latest snapshot)
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
                logger.error(f"Database error for {symbol}: {e}")
                db_session.rollback()
        
        if i + batch_size < len(symbols):
            logger.info("Batch complete. Sleeping for 4.0s...")
            time.sleep(4.0)

def passes_tier1_fast_filters(info: dict) -> tuple[bool, bool]:
    """Returns (passes_filter, should_flag_missing_pledge)"""
    if not info: return False, False
    
    # 1. Market Cap > ₹200 Cr
    # Note: marketCap from yfinance is in absolute currency units (e.g. 10000000000), not Cr/Lakhs
    mcap = to_float(info.get('marketCap'), 0)
    if mcap < 2_000_000_000: return False, False
    
    # 2. P/E (0 < pe < 300 or None)
    pe = to_float(info.get('trailingPE') or info.get('forwardPE'))
    if pe is not None and (pe <= 0 or pe > 300): return False, False
    
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
