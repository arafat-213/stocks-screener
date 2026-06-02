import datetime
import logging
import os
import sys
import time

# Add current directory to path so app can be imported
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.backtest.engine import (
    _compute_all_indicators,
    _get_cached_ohlcv,
    build_mtf_state_map,
    score_series,
    simulate_trades,
)
from app.core.strategy import TechnicalStrategy
from app.core.trading_config import UnifiedTradingConfig as BacktestConfig

# Configure logging to be quiet
logging.basicConfig(level=logging.WARNING)

# Symbols to benchmark
SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "AXISBANK.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "KOTAKBANK.NS",
    "LT.NS",
]


def run_benchmark():
    config = BacktestConfig(
        date_from=datetime.date(2019, 1, 1),
        date_to=datetime.date(2024, 1, 1),
        require_weekly_confirmation=True,
        require_monthly_confirmation=True,
    )
    strategy = TechnicalStrategy(config)

    print(
        f"Starting benchmark for {len(SYMBOLS)} symbols from {config.date_from} to {config.date_to}..."
    )

    # Warm up: The engine uses some in-memory caches. We want to measure the
    # actual computation but also see the benefit of caching if we run twice.

    start_total = time.time()

    all_trades = []

    for symbol in SYMBOLS:
        print(f"  Processing {symbol}...", end="", flush=True)
        start_sym = time.time()

        try:
            # 1. Fetch data
            df = _get_cached_ohlcv(symbol, period="10y")
            if df is None or df.empty:
                print(" Skipping (no data).")
                continue

            # 2. Precompute indicators (This is the bulk of the work)
            df_enriched = _compute_all_indicators(df, strategy, symbol=symbol)

            # 3. MTF maps
            weekly_map = build_mtf_state_map(df_enriched, "W", strategy)
            monthly_map = build_mtf_state_map(df_enriched, "M", strategy)

            # 4. Score series
            scored_dates = score_series(
                df_enriched, strategy, symbol=symbol, config=config
            )

            # 5. Simulate trades
            trades = simulate_trades(
                symbol,
                "Benchmark",
                df_enriched,
                scored_dates,
                config,
                strategy,
                weekly_state_map=weekly_map,
                monthly_state_map=monthly_map,
            )

            all_trades.extend(trades)
            end_sym = time.time()
            print(f" {end_sym - start_sym:.4f}s ({len(trades)} trades)")
        except Exception as e:
            print(f" Error: {e}")

    end_total = time.time()
    total_time = end_total - start_total

    print("\n" + "=" * 40)
    print("BENCHMARK RESULTS (FIRST RUN - Cold Cache)")
    print(f"Total symbols: {len(SYMBOLS)}")
    print(f"Total time: {total_time:.4f}s")
    print(f"Average time per symbol: {total_time / len(SYMBOLS):.4f}s")
    print(f"Total trades found: {len(all_trades)}")
    print("=" * 40)

    # Second run to test in-memory cache
    print("\nRunning again to test in-memory cache...")
    start_total_2 = time.time()
    all_trades_2 = []
    for symbol in SYMBOLS:
        df = _get_cached_ohlcv(symbol, period="10y")
        df_enriched = _compute_all_indicators(df, strategy, symbol=symbol)
        weekly_map = build_mtf_state_map(df_enriched, "W", strategy)
        monthly_map = build_mtf_state_map(df_enriched, "M", strategy)
        scored_dates = score_series(df_enriched, strategy, symbol=symbol, config=config)
        trades = simulate_trades(
            symbol,
            "Benchmark",
            df_enriched,
            scored_dates,
            config,
            strategy,
            weekly_state_map=weekly_map,
            monthly_state_map=monthly_map,
        )
        all_trades_2.extend(trades)

    end_total_2 = time.time()
    total_time_2 = end_total_2 - start_total_2
    print("BENCHMARK RESULTS (SECOND RUN - Warm Cache)")
    print(f"Total time: {total_time_2:.4f}s")
    print(f"Average time per symbol: {total_time_2 / len(SYMBOLS):.4f}s")
    print("=" * 40)


if __name__ == "__main__":
    run_benchmark()
