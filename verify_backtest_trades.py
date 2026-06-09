
import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import argparse
from datetime import datetime

# Connection setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/stock_ai")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

REGIME_LABELS = {
    0: "Bear",
    1: "Neutral",
    2: "Bull"
}

def get_run_data(run_id):
    query = f"SELECT starting_capital, config FROM backtest_runs WHERE run_id = '{run_id}'"
    return pd.read_sql(query, engine)

def analyze_trades(run_id):
    # Load trades into a DataFrame
    query = f"SELECT * FROM backtest_trades WHERE run_id = '{run_id}'"
    df = pd.read_sql(query, engine)

    if df.empty:
        print(f"No trades found for run_id: {run_id}")
        return

    # Data Cleaning: Handle empty or null sectors
    df['sector'] = df['sector'].fillna('Unknown')
    df['sector'] = df['sector'].replace('', 'Unknown')

    # Mapping Regime Labels
    df['regime_label'] = df['regime_at_entry'].map(REGIME_LABELS).fillna('Unknown')

    # Fetch run context
    run_meta = get_run_data(run_id)
    starting_capital = 1000000.0 # Default fallback
    if not run_meta.empty:
        starting_capital = run_meta['starting_capital'].iloc[0] or 1000000.0

    df['entry_date'] = pd.to_datetime(df['entry_date'])
    df['exit_date'] = pd.to_datetime(df['exit_date'])
    df['holding_days'] = (df['exit_date'] - df['entry_date']).dt.days

    # --- 1. Trade Density & Capital Utilization ---
    start_date = df['entry_date'].min()
    end_date = df['exit_date'].max()
    all_dates = pd.date_range(start_date, end_date)

    exposure_over_time = []
    capital_exposure_over_time = []

    for d in all_dates:
        active_trades = df[(df['entry_date'] <= d) & (df['exit_date'] >= d)]
        exposure_over_time.append(len(active_trades))

        if 'position_size' in df.columns and not df['position_size'].isnull().all():
            capital_exposure_over_time.append(active_trades['position_size'].sum())
        else:
            capital_exposure_over_time.append(len(active_trades) * (starting_capital * 0.1))

    counts_df = pd.DataFrame({
        'date': all_dates,
        'active_trades': exposure_over_time,
        'capital_util': capital_exposure_over_time
    })

    avg_active = counts_df['active_trades'].mean()
    max_active = counts_df['active_trades'].max()
    avg_util = counts_df['capital_util'].mean()
    max_util = counts_df['capital_util'].max()

    print(f"\n--- Trade Density Audit ---")
    print(f"Average Active Trades: {avg_active:.2f}")
    print(f"Peak Active Trades: {max_active}")
    print(f"Average Capital Utilization: ₹{avg_util:,.2f} ({avg_util / starting_capital * 100:.2f}%)")
    print(f"Max Capital Utilization: ₹{max_util:,.2f} ({max_util / starting_capital * 100:.2f}%)")

    # --- 2. Performance Metrics ---
    total_trades = len(df)
    winners = df[df['return_pct'] > 0]
    losers = df[df['return_pct'] <= 0]

    win_rate = len(winners) / total_trades
    avg_win = winners['return_pct'].mean() if not winners.empty else 0
    avg_loss = losers['return_pct'].mean() if not losers.empty else 0
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    if 'position_size' in df.columns:
        df['pnl'] = df['position_size'] * (df['return_pct'] / 100)
        total_profit = df[df['pnl'] > 0]['pnl'].sum()
        total_loss = abs(df[df['pnl'] < 0]['pnl'].sum())
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    else:
        profit_factor = (winners['return_pct'].sum()) / abs(losers['return_pct'].sum()) if not losers.empty else float('inf')

    print(f"\n--- Trade Summary for {run_id} ---")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate: {win_rate * 100:.2f}%")
    print(f"Avg Return: {df['return_pct'].mean():.2f}%")
    print(f"Avg Win: {avg_win:.2f}% | Avg Loss: {avg_loss:.2f}%")
    print(f"Risk/Reward Ratio: 1:{abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "R/R: N/A")
    print(f"Expectancy: {expectancy:.2f}% per trade")
    print(f"Profit Factor: {profit_factor:.2f}")

    # --- 3. Segmented Analysis ---
    print("\n--- Exit Reason Breakdown ---")
    exit_stats = df.groupby('exit_reason').agg({
        'return_pct': ['count', 'mean', 'median'],
        'holding_days': ['mean', 'median']
    })
    print(exit_stats)

    print("\n--- Performance by Regime (Entry) ---")
    regime_stats = df.groupby('regime_label')['return_pct'].agg(['count', 'mean', 'median', 'std'])
    print(regime_stats)

    print("\n--- Top 10 Sectors by Avg Return ---")
    print(df.groupby('sector')['return_pct'].mean().sort_values(ascending=False).head(10))

    # --- 4. Text-Based Heatmaps ---
    print("\n--- Monthly Returns Heatmap (%) ---")
    df['exit_month'] = df['exit_date'].dt.month
    df['exit_year'] = df['exit_date'].dt.year

    if 'pnl' in df.columns:
        monthly_pnl = df.groupby(['exit_year', 'exit_month'])['pnl'].sum().reset_index()
        monthly_pnl['return_pct'] = (monthly_pnl['pnl'] / starting_capital) * 100
    else:
        monthly_pnl = df.groupby(['exit_year', 'exit_month'])['return_pct'].sum().reset_index()

    pivot_monthly = monthly_pnl.pivot(index="exit_year", columns="exit_month", values="return_pct").fillna(0)
    # Use pandas options to format the output nicely
    pd.options.display.float_format = '{:,.2f}%'.format
    print(pivot_monthly)

    print("\n--- Regime vs Exit Reason Heatmap (Trade Counts) ---")
    regime_exit = df.groupby(['regime_label', 'exit_reason']).size().unstack(fill_value=0)
    pd.options.display.float_format = '{:,.0f}'.format
    print(regime_exit)

    # Reset float format
    pd.options.display.float_format = None

    # --- 5. Best/Worst Trades ---
    print("\n--- Best 10 Trades ---")
    print(df.sort_values(by='return_pct', ascending=False)[['symbol', 'return_pct', 'exit_reason', 'holding_days']].head(10).to_string(index=False))

    print("\n--- Worst 10 Trades ---")
    print(df.sort_values(by='return_pct', ascending=True)[['symbol', 'return_pct', 'exit_reason', 'holding_days']].head(10).to_string(index=False))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze backtest trades for a specific run.")
    parser.add_argument("run_id", type=str, help="The UUID of the backtest run to analyze.")

    args = parser.parse_args()
    analyze_trades(args.run_id)
    engine.dispose()
