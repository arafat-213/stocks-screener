# Refined Stock Screener & Scorer Design
**Date:** 2026-05-07
**Status:** Approved — Ready for Implementation Plan

## Overview
An intelligent, tiered screening and scoring engine for Indian NSE stocks. The system filters the full universe (~2000 stocks) through a quality funnel and scores survivors on both technical and fundamental metrics.

## 1. Stage 1 — The Quality Funnel (Screener)

To optimize performance and quality, Stage 1 is divided into two tiers.

### Tier 1: Fast Filters (In-Memory)
Applied to the full universe using data from initial `yfinance` info fetching.
- **Market Cap:** > ₹500 Cr.
- **P/E Ratio:** `pe > 0` (Removes loss-making) and `pe < 150` (Removes anomalies).
- **ROE:** > 15%.
- **Promoter Pledge:** < 20% (if data available). Handle `None` as "Unknown/Flag".
- **Liquidity:** 20-day avg daily volume > 500,000 shares (or ₹1 Cr traded value)

### Tier 2: Deep Filters (Expensive/Cached)
Applied only to Tier 1 survivors (~400 stocks).
- **3-Year Profitability Streak:** Both Revenue and Net Income must be positive for each of the last 3 fiscal years.
- **Sector-Specific Debt/Equity (D/E):**
    - `Financial Services`: < 10
    - `Insurance`: < 8
    - `Real Estate`: < 4
    - `Utilities`: < 3
    - `Default`: < 2

## 2. Stage 2 — Scoring Engine

Scores survivors from 0 to 100.

### Technical Signals (70% Weight)
- **EMA Alignment (20%):** Bullish stack (5 > 13 > 26).
- **MACD (20%):** Recent bullish crossover.
- **RSI 14 (15%):** 40-60 recovery zone.
- **Volume (15%):** Volume > 20-day SMA.

### Fundamental/Valuation Signals (30% Weight)
- **P/E Bonus/Penalty:**
    - `pe < 25`: +10 points
    - `pe < 50`: +5 points
    - `pe < 100`: 0 points
    - `pe >= 100`: -5 points
- **Promoter Pledge Penalty:** Steep penalty if > 15% but below the 20% hard-cut.

# [Comment from User (HUman)] Fix — specify weights
- P/E Score (20%): tiered bonus/penalty as listed
- Promoter Pledge (10%): penalty if 15–20%

## 3. Caching Strategy

To keep daily runs < 5 mins:
- **Table:** `fundamental_cache`
- **Fields:** `symbol`, `profitability_streak_passed`, `last_updated`, `cache_version`, `sector` (needed to apply correct D/E limit), `de_ratio` (cache the raw value so you don't re-fetch it), `de_check_passed` (boolean result of sector-relative D/E check).
- **Logic:**
    - If `cache_version != CURRENT_VERSION` or `(today - last_updated) > 7 days`: Re-fetch 3-year financials.
    - Else: Use cached boolean for Stage 1 Tier 2.

## 4. Implementation Details & Watch-outs
- **Symbol Suffix:** Always use `.NS`.
- **Missing Data:** Treat `None` in Tier 1 as failure, except for `pledgedPercent` which should be flagged for manual review if missing.
- **Financials:** Use `yf.Ticker(symbol).financials` for income statement checks.
Two small additions worth noting:

yf.Ticker(symbol).financials returns columns in reverse chronological order — explicitly document that iloc[:,0] is most recent year, iloc[:,2] is 3 years ago, otherwise this causes silent bugs
Add: "Fetch yfinance in batches of 50 with 1–2s delay to avoid rate limiting"

## 5. Success Criteria
- Cold run (no cache): < 15 minutes acceptable.
- Minimum 30 stocks must pass Stage 1 + Stage 2; alert if below threshold.
- No loss-making or high-pledge stocks in the top 10.
- Banks/NBFCs are not automatically filtered out due to D/E.
