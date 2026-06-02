#4. 1. The "Logic Fragmentation" Disaster [STATUS: RESOLVED]
  Your system has a split personality. You have signal logic in scorer.py, screening logic in
  momentum.py, and backtest/digest logic in engine.py and signal_digest.py.
   * Status: Logic has been centralized in `backend/app/core/strategy.py`. Both the pipeline and backtest engine now use the same `TechnicalStrategy` class.

#5. 2. The Stop-Loss "Straitjacket" [STATUS: RESOLVED]
  In backend/app/backtest/engine.py, you force all stop losses into a hard 5% to 8% range:

   1 stop_price = max(min(base_stop, entry_price * (1 - MIN_STOP)), entry_price * (1 -
     MAX_STOP))
   * The Flaw: This is arguably your biggest mistake. You're calculating ATR and structural
     stops, then throwing them away if they don't fit your arbitrary 5-8% box.
   * Effectiveness: In the Indian market, midcaps and smallcaps (which your Tier 1.5 allows)
     can breathe 10% in a week without breaking trend. By forcing an 8% max stop, you are
     guaranteeing you get stopped out by market noise on your best candidates. You’re trading
     a "feel-good" stop loss, not the reality of stock volatility.
   * Verification: Checked backend/app/backtest/engine.py:507 - uses base_stop directly now.

#6. 3. "Magic Number" Scoring [STATUS: RESOLVED]
  Your scoring system in scorer.py uses incredibly specific weights like 28.5 for EMA crosses
  and 21.5 for MACD.
   * Status: Indicator weights are now exposed in `UnifiedTradingConfig`, allowing for transparency and future multi-parameter optimization.

#7. 4. Fear of the "Power Zone" (RSI > 80) [STATUS: UNRESOLVED]
  You kill any signal if RSI > 80:

   1 if ta_data.get("rsi", 0) > 80: combined_score = 0.0
   * The Flaw: You're punishing the exact stocks that are showing the most relative strength.
     The strongest stocks in a bull market often stay above 70-80 RSI for the entire duration
     of their "meat-of-the-move" run.
   * Effectiveness: By capping RSI at 80, you are systematically excluding the high-alpha
     "outliers" that usually account for 80% of a portfolio's returns. You're left with the
     "mediocre" setups that are just starting to move.

#13. 5. Architectural Dead Weight [STATUS: RESOLVED]
  Your orchestrator.py explicitly states that Tier 2 (Fundamental caching) was removed, yet
  screener.py is full of deep fundamental fetching logic, and scorer.py still calculates a
  fundamental score that is eventually set to 0.0.
   * Honest Truth: This is messy. Either you believe in fundamentals or you don't. Leaving
     half-finished, bypassed fundamental logic in the pipeline suggests you're afraid to
     commit to a pure technical strategy, or you're too lazy to clean up the refactor.
   * Status: Legacy files `screener.py` and `scorer.py` have been removed. The dashboard no longer joins `FundamentalCache`. The pipeline is now purely technical with minimal metadata (Market Cap) fetched via `fast_info`.

#8. 6. The 200 EMA "Tunnel Vision" [STATUS: UNRESOLVED]
  You treat above_200ema as a binary killer.
   * The Flaw: While safe, it’s lazy. You’ll miss the entire stage-1 accumulation phase and
     the first 20% of a stage-2 breakout.
   * Advice: Use the 200 EMA as a factor, not a death penalty. A stock crossing above the 200
     EMA with volume is often a better entry than one that has been sitting at 120% of its 200
     EMA for months.


#10. 3. Tuning the "Magic Numbers" (Validation Framework) [STATUS: UNRESOLVED]
  The reason those numbers (21.5, 28.5) feel wrong is that they are static. In a trending
  market, EMA crosses are king; in a sideways market, RSI mean-reversion is king.

  How to validate and tune:
   1. Expose Weights as Parameters: Modify your UnifiedTradingConfig to include weights for
      each indicator.

   1     @dataclass
   2     class UnifiedTradingConfig:
   3         # ... existing ...
   4         ema_weight: float = 28.5
   5         macd_weight: float = 21.5
   6         rsi_weight: float = 21.5
   7         volume_weight: float = 21.5
   2. Update parameter_sweep.py: Your current sweep only checks high-level triggers (holding
      days, threshold). You need to add these weights to the GRID.
   3. Use a Fitness Function: Don't just look at "Total Return." Optimize for Sharpe Ratio or
      Expectancy. If a weight change increases return but doubles your Drawdown, it's a "bad"
      tuning that is just lucky on a few outliers.
   4. Walk-Forward Analysis: Run your tuning on 2022-2023 data, then test the winning numbers
      on 2024 data (Out-of-Sample). If they fail in 2024, your "magic numbers" were just
      over-fitted to the past.

#9. 4. Exit Signal Trigger vs. Binary Killers [STATUS: UNRESOLVED]
  You should stop "killing" the score and start "managing the state."

  Proposed Transition:
   * The Problem: score = 0 if RSI > 80 is a "dumb" rule. A stock at 81 RSI might be in a
     vertical "blow-off top" that could gain another 20% in two days. You want to capture
     that, but with a tighter leash.
   * The Solution: Implement a State Engine in your centralized strategy.
       * State: NORMAL: High score, standard stop loss.
       * State: OVEREXTENDED (RSI > 75): Maintain position, but lock in profits.
       * Logic: Instead of zeroing the score, the OVEREXTENDED state should trigger an
         exit_reason = "profit_protection".
       * The Rule: If RSI > 78 AND Price breaks the previous day's Low -> Exit immediately.

  Why this is better:
  It allows the stock to be as "insane" as it wants to be (RSI 85, 90), but the moment the
  parabolic move stalls (breaks previous low), you are out with a massive gain. Your current
  system just refuses to enter or stay in the best trades of the year.

  ---

  Immediate Action Plan (Centralization Strategy)

#4.1   1. Create backend/app/core/strategy.py: [STATUS: UNRESOLVED]
       * Move calculate_technical_score here.
       * Pass the UnifiedTradingConfig directly into it so it uses the config's weights.
#4.2   2. Unify the Signal Object: [STATUS: UNRESOLVED]
       * Make sure orchestrator.py (live) and engine.py (backtest) both call
         Strategy.evaluate(df, config).
#5.1   3. Kill the Hardcoded Stop Floor/Ceiling: [STATUS: RESOLVED]
       * In engine.py, change the stop-loss logic to be purely ATR-based or structure-based.
         If the backtest shows a 15% drawdown, accept it as a truth about that setup, then use
         Position Sizing to reduce the cash risk, rather than choking the trade with a 7%
         stop.


Here is the brutally honest audit of your current state:

#1.   1. Law of the Land Violation: The NSE Suffix (Critical) [STATUS: RESOLVED]
  Your GEMINI.md explicitly states: "All Indian stock symbols MUST have the .NS suffix. Never
  use raw symbols in database queries or API logic."

  You are currently violating this everywhere.
   * get_nse_symbols() returns raw symbols (e.g., ['20MICRONS', '21STCENMGM']).
   * Your TechnicalSignal, Stock, and FundamentalData tables are being populated with these
     raw symbols.
   * Your queries (e.g., db.query(TechnicalSignal).filter_by(symbol=symbol)) use raw symbols.
   * The Impact: You have fragmented your data. If any external service or future refactor
     follows the "Law," your existing database becomes a graveyard of orphaned records. You
     are building a system that is incompatible with its own documentation.

#3.   2. Testing Hallucination: Outdated & Irrelevant (Critical) [STATUS: RESOLVED]
  Your MomentumScorer code implements a 100-point system, but your test suite
  (test_scorer_fixes.py) was still testing for an old 70-point ceiling.
   * Status: Updated `test_scorer_fixes.py` to validate the 100-point scale and new technical tiers (EMA Crosses, MACD Decoupling).

#11.   3. "Binary Killer" is a Mocked Joke (Major) [STATUS: RESOLVED]
  You mentioned a "heavy fundamentals related refactoring." In reality, you've gutted the
  fundamentals and replaced the "Binary Killer" (Pledging Filter) with random noise.
   * The Evidence: update_pledging.py uses random.random() < 0.05 and random.uniform(31.0,
     95.0) to assign pledging values.
   * Status: The file update_pledging.py is no longer in the codebase, and random pledging filters appear to have been removed from the main pipeline.

#2.   4. Known Crash Vector: Timezone Fragility (Major) [STATUS: RESOLVED]
  Your MEMORY.md warns that yfinance timezone-aware data causes TypeError in comparisons and
  mandates using .tz_localize(None).
   * The Violation: Your orchestrator (orchestrator.py:161) calls signal_date =
     working_df.index[-1].date() without ensuring the index is naive. While .date() might
     survive, any comparison of working_df.index[-1] with a naive pd.Timestamp (common in your
     backtest engine) will crash the process mid-run.

#12.   5. Idempotency Risk [STATUS: RESOLVED]
  While you have checkpoints, your tier1_survivors and final_survivors are maintained as
  in-memory lists during the run. If the pipeline crashes after Tier 1.5 but before Scoring,
  your checkpoint knows which individual symbols were processed, but it has no way to
  reconstruct the list of survivors without re-running the logic.
  * Status: Checkpoints now save set(tier1_survivors) and set(final_survivors) to the database.

  ---

  Action Plan to Reach "Ready" State:
#1.1   1. Enforce the Suffix: [STATUS: RESOLVED] Update get_nse_symbols to return .NS symbols or ensure every DB
      entry is transformed immediately. Scrub your DB and start fresh with .NS keys.
#3.1   2. Sync Tests to Reality: [STATUS: RESOLVED] Rewrite test_scorer_fixes.py to assert the 100-point scale. Add
      edge-case tests for your new tiers (EMA cross, MACD decoupling, RSI recovery).
#11.1   3. Kill the Randomness: [STATUS: RESOLVED] Either implement a real fetcher for pledging data or disable the
      filter. Mock data in a "production-ready" pipeline is a liability.
#2.1   4. Localize Timezones: [STATUS: RESOLVED] Add df.index = df.index.tz_localize(None) to your fetcher or
      orchestrator immediately after data retrieval.

  Don't run the pipeline yet. You're just generating high-quality garbage.
