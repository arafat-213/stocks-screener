# Named Screener Extension Design
**Date:** 2026-05-10
**Status:** Approved — Ready for Implementation Plan

## Goal
Extend the existing two-tier pipeline into a general-purpose screener platform. The pipeline becomes a screen-agnostic data enrichment engine that computes and persists a rich set of signals daily. Named screens (e.g., Momentum Monsters, Near Breakout, Steady Compounders) are defined as query functions over that persisted data, not as separate pipeline runs. The frontend calls a screen by slug and receives a pre-shaped result list.

---

## 1. Database Schema — New and Modified Tables

### 1a. Modified: `technical_signals`
Add the following columns to support momentum, trend quality, and breakout detection screens:

- `momentum_1m`: Float — price return over last 1 month (%).
- `momentum_3m`: Float — price return over last 3 months (%).
- `momentum_6m`: Float — price return over last 6 months (%).
- `rs_score`: Float — relative strength percentile rank (0–100) vs. Benchmark (Nifty 500 or Nifty 50), computed over trailing 12 months.
- `adx`: Float — Average Directional Index (14-period), measures trend strength.
- `above_200ema`: Boolean — whether Close > EMA200 on signal date.
- `ema_slope_20`: Float — slope of EMA20 over last 5 bars (positive = rising).
- `pct_from_52w_high`: Float — percentage distance of current close from the 52-week high (negative = below high).
- `pct_from_52w_low`: Float — percentage distance of current close from the 52-week low.
- `week52_high`: Float — highest close over the trailing 52 weeks.
- `week52_low`: Float — lowest close over the trailing 52 weeks.
- `resistance_level`: Float — highest close in the 52 weeks prior to last pullback, used for breakout proximity.
- `pct_from_resistance`: Float — how far current price is below `resistance_level` (%).
- `volume_breakout`: Boolean — True if volume > 2× 20-day average on a green (up) day.

### 1b. Modified: `fundamental_cache`
Add the following columns to support value, quality, and dividend-based screens. These are refreshed on the existing 7-day cache cycle.

- `roce`: Float — Return on Capital Employed (EBIT / Capital Employed).
- `peg_ratio`: Float — PE ratio divided by 3-year EPS growth rate.
- `ev_to_ebitda`: Float — sourced from `info.get('enterpriseToEbitda')`.
- `dividend_yield`: Float — sourced from `info.get('dividendYield')`.
- `price_to_fcf`: Float — Market Cap / Free Cash Flow.
- `earnings_growth_3y`: Float — CAGR of net income over the last 3 annual periods.
- `fcf_positive`: Boolean — True if Free Cash Flow was positive in the last fiscal year.
- `dividend_consistency`: Boolean — True if the stock paid a dividend in each of the last 3 years.
- `market_cap_category`: String — `'largecap'`, `'midcap'`, or `'smallcap'` based on thresholds:
    - Large: > ₹20,000 Cr
    - Mid: ₹5,000–20,000 Cr
    - Small: < ₹5,000 Cr

### 1c. New: `screen_results`
Materialized output table, truncated and rewritten at the end of each successful pipeline run. Stores only the most recent results.

- `id`: Integer, Primary Key.
- `screen_slug`: String — e.g., `'momentum-monsters'`.
- `symbol`: String, ForeignKey(`stocks.symbol`).
- `timeframe`: String(1) — primary timeframe for the screen (`'D'`, `'W'`, or `'M'`).
- `rank`: Integer — position within the screen result.
- `score_used`: Float — primary sort metric for the given screen.
- `computed_at`: DateTime — timestamp of the pipeline run.

**Retention Policy:** `materialize_all_screens()` issues a full `DELETE FROM screen_results` before writing new rows. Only latest results are retained.

---

## 2. Pipeline Changes — Decoupled Enrichment

### 2a. Loosen Tier 1 Hard Filters
Move quality gates to screen-level filters. Revised Tier 1 survivors:

| Filter | Current Threshold | New Threshold | Reason for Change |
|---|---|---|---|
| Market Cap | > ₹500 Cr (incorrectly checked as 600M) | > ₹200 Cr (`2,000_000_000` raw INR) | Capture small-caps |
| P/E | 0 < PE < 150 | 0 < PE < 300 | Capture high-growth |
| ROE | > 15% | **Removed** | Move to screens |
| Promoter Pledge | < 20% | **Removed** | Move to screens |
| Liquidity | Avg Vol × Price > ₹5 Cr | ₹2 Cr (`20,000_000`) | Widen universe |

### 2b. Tier 2 Fetch — Rate Limit Strategy
Adaptive strategy for 1000+ survivors:
- **Inter-batch sleep:** 4.0s (up from 1.0s) for deep fetch loop.
- **Per-symbol retry:** Exponential backoff (initial 2s, max 3 attempts, jitter ±0.5s).
- **Skip-and-log:** If retries fail, write `FundamentalCache` with `cache_version = -1`. Orchestrator skips scoring for these.
- **Cache TTL:** 7 days.

### 2c. Extended Fundamental Extraction (`screener.py`)
Extend `fetch_and_cache_deep_fundamentals` to fetch `ticker.balance_sheet` and `ticker.cashflow` (in addition to `financials` and `info`). Compute the following using the robust `get_financial_row` utility:

- **ROCE:** `EBIT / (Total Assets - Current Liabilities)`. Use `iloc[:, 0]` (most recent). Wrap in `try/except` returning `None` if any component is missing.
- **PEG:** `info.get('trailingPE') / (info.get('earningsGrowth', 0) * 100)`. Set only if PE > 0 and growth > 0.
- **FCF:** `Operating Cash Flow - Capital Expenditures` from cashflow statement.
- **Price to FCF:** `marketCap / FCF` if FCF > 0.
- **Dividend Consistency:** `True` if `ticker.dividends` shows at least one payment in each of the last 3 calendar years.
- **Market Cap Category:**
    - `largecap`: > ₹20,000 Cr
    - `midcap`: ₹5,000–20,000 Cr
    - `smallcap`: < ₹5,000 Cr

### 2d. Relative Strength Score — Bulk Post-Scoring Step
1. After all symbols scored, collect `momentum_12m` for each symbol.
2. **Benchmark Resolution:** Try `^CRSLDX` (Nifty 500). If series < 250 rows, fall back to `^NSEI` (Nifty 50). Log benchmark used.
3. Compute excess return: `momentum_12m - benchmark_return`.
4. Assign percentile rank (0–100) using a simple rank formula.
5. **Bulk Update:** Fetch all `TechnicalSignal.id` for current date/timeframe. Emit a **single bulk update** via `db.bulk_update_mappings()`.

### 2e. Robust Financial Row Extraction — `utils.py`
Centralize `get_financial_row` with ordered keyword matching:
- `net_income`: `["net income", "net earnings", "profit after tax", "pat"]`
- `revenue`: `["total revenue", "revenue", "total operating revenue", "net sales"]`
- `ebit`: `["ebit", "operating income", "operating profit"]`
- `total_assets`: `["total assets"]`
- `current_liab`: `["current liabilities", "total current liabilities"]`
- `op_cashflow`: `["operating cash flow", "cash from operations", "net cash from operating"]`
- `capex`: `["capital expenditure", "purchase of fixed assets", "capex"]`

---

## 3. Screen Definitions

### 3a. Screen Registry (`app/screens/registry.py`)
| Slug | Label | Category | Primary Metric (Sort) |
|---|---|---|---|
| `52w-high` | Near 52-Week High | Price Action | `pct_from_52w_high` DESC |
| `52w-low` | Near 52-Week Low | Price Action | `pct_from_52w_low` ASC |
| `near-breakout` | Near Breakout | Price Action | `entry_score` DESC |
| `low-debt-midcap` | Low Debt Mid & Small Caps | Value | `entry_score` DESC |
| `undervalued-fundamentals` | Undervalued Strong Fundamentals | Value | `peg_ratio` ASC |
| `momentum-monsters` | Momentum Monsters | Momentum | `rs_score` DESC |
| `value-with-momentum` | Value with Momentum | Momentum | `momentum_1m` DESC |
| `steady-compounders` | Steady Compounders | Quality | `roce` DESC |

---

## 4. API Layer
- `GET /api/screens`: List all registered screens metadata.
- `GET /api/screens/{slug}`: Return results from `screen_results` table.
- `GET /api/screens/{slug}?live=true`: Bypass materialized table, run query function directly.

---

## 5. Implementation Roadmap
1. **Migrations:** Add columns to `TechnicalSignal`, `FundamentalCache`; create `ScreenResult`.
2. **Models:** Update ORM classes.
3. **Extraction:** Implement robust `get_financial_row` in `utils.py`.
4. **Scoring:** Extend `scorer.py` with new computed fields.
5. **Orchestration:** Implement adaptive fetching, RS bulk update, and materialization step.
6. **Screens:** Build the screen library and registry.
7. **API:** Implement routes and wiring.
