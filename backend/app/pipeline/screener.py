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
