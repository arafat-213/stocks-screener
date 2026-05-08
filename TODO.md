# Stock AI Refined Screener Implementation

## Phase 1: Foundation
- [x] Task 1: Update Database Models & Migrations

## Phase 2: Screener Logic
- [x] Task 2: Implement Tier 1 Fast Filters
- [x] Task 3: Implement Sector-Relative D/E and 3-Year Profitability

## Phase 3: Performance & Caching
- [x] Task 4: Implement Tiered Caching & Batching

## Phase 4: Scoring & Finalization
- [x] Task 5: Refine Stage 2 Scoring
- [x] Task 6: Final Verification & Pipeline Run

🟡 Phase 2 — High-Value Features
Alerting / Notifications — The screener runs but nobody knows when a stock hits 3/3 confluence. Add a Telegram bot (via python-telegram-bot) or email alert (SMTP) triggered at the end of run_pipeline() when confluence_count == 3. This is the #1 reason a screener becomes a daily-use tool.
Watchlist — A simple Watchlist DB table (user_id, symbol, added_at). Lets users pin stocks to track across pipeline runs even if they fall out of the top 20. Add a heart icon to StockCard.jsx.
Historical Signal Tracking — Your TechnicalSignal table stores signals but the dashboard only shows the latest. Build a chart showing a stock's score over time — this reveals whether a stock is trending up or deteriorating in its signal strength.

🟢 Phase 3 — Intelligence & Depth
Backtesting Engine — Given you already store historical OHLCV (3 years via period="3y"), you can replay your calculate_combined_score() logic over past dates and measure: "If I bought everything with score > 80 and sold after 20 days, what was the return?" This validates your scoring model with real data.
News Sentiment Layer — Add a NewsSignal model. At pipeline end, fetch headlines for top-scored stocks via a free API (e.g. NewsAPI or Yahoo Finance RSS) and run a quick sentiment pass. A stock with strong technicals + positive news sentiment is a much higher conviction signal.
Position Sizing / Risk Module — Add a simple Kelly Criterion or fixed-fractional calculator. Given a portfolio size, score, and ATR (already derivable from your OHLCV data), suggest position size and stop-loss level. This moves the tool from screener to decision support.

🔵 Phase 4 — Platform Maturity
User Authentication — Add FastAPI-Users or a simple JWT layer. This unlocks per-user watchlists, custom alert thresholds, and eventually a SaaS model.
Real-time Price Updates — Your dashboard polls every 15s via REST. Switch to WebSockets (fastapi-websockets) for live intraday price ticks during market hours. The CandlestickChart component is already structured for this.
Deployment & Scheduling — Containerize with Docker Compose (FastAPI + PostgreSQL + a Redis task queue). Replace the BackgroundTasks pipeline trigger with APScheduler or Celery so the pipeline runs automatically at market close (3:30 PM IST) daily without manual triggering.
