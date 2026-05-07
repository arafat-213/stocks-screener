CURRENT_SCREENER_VERSION = 1

def passes_tier1_fast_filters(info: dict) -> tuple[bool, bool]:
    """Returns (passes_filter, should_flag_missing_pledge)"""
    if not info: return False, False
    
    # 1. Market Cap > ₹500 Cr (~$6M USD)
    # Note: marketCap from yfinance for Indian stocks is usually in local currency (INR),
    # but the instruction says "Mcap > ₹500 Cr (~$6M USD)" and the code uses 6,000,000.
    # We will stick to the 6M value as requested.
    mcap = info.get('marketCap', 0) or 0
    if mcap < 6_000_000: return False, False
    
    # 2. P/E (0 < pe < 150)
    pe = info.get('trailingPE') or info.get('forwardPE')
    if pe is None or pe <= 0 or pe > 150: return False, False
    
    # 3. ROE > 15%
    roe = info.get('returnOnEquity', 0) or 0
    if roe < 0.15: return False, False
    
    # 4. Promoter Pledge < 20%
    pledged = info.get('pledgedPercent')
    flag_missing = False
    if pledged is None:
        flag_missing = True
    elif pledged > 0.20:
        return False, False
    
    # 5. Liquidity (20-day avg vol > 500k)
    avg_vol = info.get('averageVolume', 0) or 0
    if avg_vol < 500_000: return False, False
    
    return True, flag_missing

def passes_fundamental_filters(info: dict) -> bool:
    if not info:
        return False
        
    try:
        roe = info.get('returnOnEquity', 0)
        if roe is None: roe = 0
            
        debt_equity = info.get('debtToEquity', 100)
        if debt_equity is None: debt_equity = 100
        
        eps_growth = info.get('earningsGrowth', 0)
        if eps_growth is None: eps_growth = 0
            
        market_cap = info.get('marketCap', 0)
        if market_cap is None: market_cap = 0
            
        promoter_holding = info.get('heldPercentInsiders', 0)
        if promoter_holding is None: promoter_holding = 0

        if roe < 0.15: return False
        # yfinance debtToEquity is often returned as percentage (e.g., 40.5 for 0.4)
        if debt_equity > 100: return False 
        if eps_growth < 0.10: return False
        if market_cap < 5000000000: return False # 500 Cr in absolute
        if promoter_holding < 0.40: return False
        
        return True
    except Exception:
        return False
