import re
import time

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

STOCKS = [
    "RELIANCE",
    "TCS",
    "HDFCBANK",
    "INFY",
    "KPITTECH",
    "DIXON",
    "RVNL",
    "IEX",
    "SUZLON",
    "SHAKTIPUMP",
]


def get_screener_data(symbol):
    """Fetches key ratios from screener.in public page."""
    try:
        url = f"https://www.screener.in/company/{symbol}/"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        ratios = {}

        # Screener stores top ratios in a specific list
        items = soup.find_all("li", class_="flex flex-space-between")
        for item in items:
            name = item.find("span", class_="name").text.strip()
            value_span = item.find("span", class_="number")
            if not value_span:
                continue
            value = value_span.text.strip().replace(",", "")

            if "Stock P/E" in name:
                ratios["pe"] = float(value)
            if "Debt to equity" in name:
                ratios["de"] = float(value)
            if "ROE" in name:
                ratios["roe"] = float(value) / 100.0
            if "Promoter holding" in name:
                ratios["pledge_potential"] = value  # Pledging is deeper in the page

        # Pledging is often in the 'Shareholding Pattern' table as a sub-note or percentage of holding
        # For simplicity, we'll try to find the 'Pledged' text if it exists
        if "Pledged" in resp.text:
            # Simple regex to find pledged % if it's visible in the summary or tables
            match = re.search(r"Pledged percentage\s+([\d\.]+)", resp.text)
            ratios["pledge"] = float(match.group(1)) / 100.0 if match else 0.0
        else:
            ratios["pledge"] = 0.0

        return ratios
    except Exception:
        return None


print(
    f"{'Symbol':<12} | {'YF PE':<8} | {'SCR PE':<8} | {'YF D/E':<8} | {'SCR D/E':<8} | {'YF Pledge':<10} | {'SCR Pledge':<10}"
)
print("-" * 90)

results = []
for sym in STOCKS:
    # YF
    ticker = yf.Ticker(f"{sym}.NS")
    info = ticker.info
    yf_pe = info.get("trailingPE") or info.get("forwardPE")
    yf_de = info.get("debtToEquity")
    yf_pledge = info.get("pledgedPercent")

    # Screener
    scr = get_screener_data(sym)
    time.sleep(1)  # Be polite

    if scr:
        print(
            f"{sym:<12} | {str(yf_pe)[:8]:<8} | {str(scr.get('pe'))[:8]:<8} | {str(yf_de)[:8]:<8} | {str(scr.get('de'))[:8]:<8} | {str(yf_pledge)[:10]:<10} | {str(scr.get('pledge'))[:10]:<10}"
        )
        results.append(
            {
                "sym": sym,
                "yf_pe": yf_pe,
                "scr_pe": scr.get("pe"),
                "yf_de": yf_de,
                "scr_de": scr.get("de"),
                "yf_pledge": yf_pledge,
                "scr_pledge": scr.get("pledge"),
            }
        )

df = pd.DataFrame(results).dropna(subset=["yf_pe", "scr_pe"])
df["pe_var"] = (abs(df["yf_pe"] - df["scr_pe"]) / df["scr_pe"]) * 100
print(f"\nAverage PE Variance: {df['pe_var'].mean():.2f}%")
print(f"Max PE Variance: {df['pe_var'].max():.2f}%")
