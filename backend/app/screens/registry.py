from app.screens.price_action import screen_52w_high, screen_52w_low, screen_near_breakout
from app.screens.value import screen_low_debt_midcap, screen_undervalued_fundamentals, screen_steady_compounders, screen_qarp, screen_dividend_growth
from app.screens.momentum import (
    screen_momentum_monsters,
    screen_value_with_momentum,
    screen_ema_crossover_signals,
    screen_volume_surge,
    screen_rsi_recovery,
    screen_actionable_entries,
)
from app.screens.confluence import (
    screen_mtf_confluence,
    screen_sector_leaders,
    screen_fresh_52w_breakout,
)
from app.screens.sector_rotation import screen_hot_sectors

SCREEN_REGISTRY = {
    # ── Actionable Entries ───────────────────────────────────────────────────
    "actionable-entries": {
        "fn": screen_actionable_entries,
        "label": "Actionable Entries",
        "description": (
            "EMA crossover signals passing the full backtest filter: above 200 EMA, "
            "RSI 40–65, positive 12m momentum, prior consolidation, "
            "and volume breakout or ADX ≥ 25. Act on these the next trading day."
        ),
        "category": "Signals",
    },
    # ── Price Action ─────────────────────────────────────────────────────────
    "52w-high": {
        "fn": screen_52w_high,
        "label": "52-Week Highs",
        "description": "Bullish stocks within 5% of their 52-week high. Trend continuation candidates.",
        "category": "Price Action"
    },
    "52w-low": {
        "fn": screen_52w_low,
        "label": "Recovering from Lows",
        "description": "Stocks near 52-week lows with early RSI recovery. Watchlist only — not direct entry signals.",
        "category": "Price Action"
    },
    "near-breakout": {
        "fn": screen_near_breakout,
        "label": "Near Breakout",
        "description": "Bullish stocks within 3% of key resistance with volume or rising EMA.",
        "category": "Price Action"
    },

    # ── Entry Signals ─────────────────────────────────────────────────────────
    "ema-crossover": {
        "fn": screen_ema_crossover_signals,
        "label": "EMA Crossover Signals",
        "description": "Fresh EMA 5/13 bullish crosses today. These are the signals the backtest engine trades.",
        "category": "Signals"
    },
    "volume-surge": {
        "fn": screen_volume_surge,
        "label": "Volume Surge",
        "description": "Volume >2x 20-day average on a green day with bullish EMA alignment.",
        "category": "Signals"
    },
    "rsi-recovery": {
        "fn": screen_rsi_recovery,
        "label": "RSI Recovery",
        "description": "Stocks recovering from oversold RSI with EMA20 support intact.",
        "category": "Signals"
    },
    "mtf-confluence": {
        "fn": screen_mtf_confluence,
        "label": "Multi-Timeframe Confluence",
        "description": "Daily, Weekly, and Monthly all simultaneously bullish. Highest-conviction setups.",
        "category": "Signals"
    },
    "fresh-breakout": {
        "fn": screen_fresh_52w_breakout,
        "label": "Fresh 52W Breakout",
        "description": "Price just crossed 52-week high with volume. No overhead resistance.",
        "category": "Signals"
    },

    # ── Momentum ──────────────────────────────────────────────────────────────
    "momentum-monsters": {
        "fn": screen_momentum_monsters,
        "label": "Momentum Monsters",
        "description": "Top RS percentile stocks with strong ADX and 3-month momentum.",
        "category": "Momentum"
    },
    "value-with-momentum": {
        "fn": screen_value_with_momentum,
        "label": "Value with Momentum",
        "description": "Reasonable PEG with recent price strength and rising EMA slope.",
        "category": "Momentum"
    },
    "sector-leaders": {
        "fn": screen_sector_leaders,
        "label": "Sector Leaders",
        "description": "Top 3 RS-ranked stocks in each sector. Use for sector rotation.",
        "category": "Momentum"
    },
    "hot-sectors": {
        "fn": screen_hot_sectors,
        "label": "Hot Sector Stocks",
        "description": "Best stocks from the top 3 sectors by average RS. Combines macro and micro.",
        "category": "Momentum"
    },

    # ── Value / Quality ───────────────────────────────────────────────────────
    "low-debt-midcap": {
        "fn": screen_low_debt_midcap,
        "label": "Quality Midcaps",
        "description": "Midcap stocks (5k–20k Cr) with low debt, positive FCF, and sustained profits.",
        "category": "Value"
    },
    "undervalued-fundamentals": {
        "fn": screen_undervalued_fundamentals,
        "label": "Undervalued Growth",
        "description": "Low PEG (<1.5), high ROE (>15%), dividend yield, EV/EBITDA < 20.",
        "category": "Value"
    },
    "steady-compounders": {
        "fn": screen_steady_compounders,
        "label": "Steady Compounders",
        "description": "High ROCE (>15%) with consistent dividend history above 200 EMA.",
        "category": "Value"
    },
    "qarp": {
        "fn": screen_qarp,
        "label": "Quality at Reasonable Price",
        "description": "High ROCE + ROE + FCF positive + low debt + PEG < 2.5.",
        "category": "Value"
    },
    "dividend-growth": {
        "fn": screen_dividend_growth,
        "label": "Dividend Growth",
        "description": "Consistent dividend payers with positive FCF and price above 200 EMA.",
        "category": "Value"
    },
}
