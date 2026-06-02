import logging
import time

import pandas as pd
import yfinance as yf
from nsepython import nse_eq

# Disable noisy logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

STOCKS = {
    "Large": ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"],
    "Mid": ["KPITTECH", "TATAELXSI", "DIXON", "MAZDOCK", "RVNL"],
    "Small": ["IEX", "CDSL", "KEI", "SUZLON", "ZENSARTECH"],
    "Micro": ["SHAKTIPUMP", "ELECON", "PITTIENG", "EXCELINDUS", "SIGACHI"],
}


def to_float(val):
    try:
        if val is None:
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


def fetch_nse_data(symbol):
    """
    Attempts to fetch P/E and MCap from NSE official via nsepython.
    Note: NSE website is heavily throttled.
    """
    try:
        # nsepython nse_eq returns a lot of data. We need metadata and priceInfo
        data = nse_eq(symbol)
        metadata = data.get("metadata", {})
        price_info = data.get("priceInfo", {})

        # NSE PE is often in 'metadata' or 'priceInfo' depending on the API version
        # For simplicity in this debug script, we'll try to extract common fields
        nse_pe = to_float(metadata.get("pdSymbolPe")) or to_float(price_info.get("pe"))

        # NSE Market Cap is often not in the basic eq() response in a clean way,
        # but sometimes it's in 'securityWiseDP' or similar.
        # We'll focus on PE for this comparison as it's the most 'flaky' in YF.
        return {"pe": nse_pe}
    except Exception as e:
        return {"pe": None, "error": str(e)}


results = []

print(
    f"{'Symbol':<12} | {'Tier':<6} | {'YF PE':<8} | {'NSE PE':<8} | {'YF ROE':<8} | {'YF Debt/Eq':<10} | {'YF Pledge':<8}"
)
print("-" * 80)

for tier, symbols in STOCKS.items():
    for sym in symbols:
        # 1. Fetch YFinance
        yf_sym = f"{sym}.NS"
        ticker = yf.Ticker(yf_sym)
        info = ticker.info

        yf_pe = info.get("trailingPE") or info.get("forwardPE")
        yf_roe = info.get("returnOnEquity")
        yf_de = info.get("debtToEquity")
        yf_pledge = info.get("pledgedPercent")

        # 2. Fetch NSE (Ground Truth for PE)
        # We'll sleep to avoid 403
        time.sleep(1)
        nse_data = fetch_nse_data(sym)
        nse_pe = nse_data.get("pe")

        results.append(
            {
                "Symbol": sym,
                "Tier": tier,
                "YF_PE": yf_pe,
                "NSE_PE": nse_pe,
                "YF_ROE": yf_roe,
                "YF_DE": yf_de,
                "YF_Pledge": yf_pledge,
            }
        )

        print(
            f"{sym:<12} | {tier:<6} | {str(yf_pe)[:8]:<8} | {str(nse_pe)[:8]:<8} | {str(yf_roe)[:8]:<8} | {str(yf_de)[:10]:<10} | {str(yf_pledge)[:8]:<8}"
        )

df = pd.DataFrame(results)
print("\n" + "=" * 30)
print("FLAKINESS SUMMARY")
print("=" * 30)

# 1. Missing PE Rate
missing_yf_pe = df["YF_PE"].isna().sum()
print(
    f"YFinance Missing PE: {missing_yf_pe}/{len(df)} ({missing_yf_pe / len(df) * 100:.1f}%)"
)

# 2. Variance check (where both exist)
valid_pe = df.dropna(subset=["YF_PE", "NSE_PE"])
if not valid_pe.empty:
    valid_pe = valid_pe.copy()
    valid_pe["variance"] = (
        abs(valid_pe["YF_PE"] - valid_pe["NSE_PE"]) / valid_pe["NSE_PE"]
    ) * 100
    avg_var = valid_pe["variance"].mean()
    print(f"Average PE Variance (YF vs NSE): {avg_var:.2f}%")
    print(f"Max PE Variance: {valid_pe['variance'].max():.2f}%")

# 3. Missing critical metrics in YF
for col in ["YF_ROE", "YF_DE", "YF_Pledge"]:
    missing = df[col].isna().sum()
    print(
        f"YFinance Missing {col[3:]}: {missing}/{len(df)} ({missing / len(df) * 100:.1f}%)"
    )

print("\nConclusion:")
if missing_yf_pe > 0 or (not valid_pe.empty and avg_var > 10):
    print(
        "CRITICAL: YFinance is unreliable for NSE fundamentals. Variance or missing data detected."
    )
else:
    print(
        "YFinance seems okay for this small sample, but caution is advised for Microcaps."
    )
