from app.screens.price_action import screen_52w_high, screen_52w_low, screen_near_breakout
from app.screens.value import screen_low_debt_midcap, screen_undervalued_fundamentals, screen_steady_compounders
from app.screens.momentum import screen_momentum_monsters, screen_value_with_momentum

SCREEN_REGISTRY = {
    "52w-high": {
        "fn": screen_52w_high,
        "label": "52-Week Highs",
        "description": "Stocks trading within 5% of their 52-week high.",
        "category": "Price Action"
    },
    "52w-low": {
        "fn": screen_52w_low,
        "label": "52-Week Lows",
        "description": "Stocks trading within 10% of their 52-week low.",
        "category": "Price Action"
    },
    "near-breakout": {
        "fn": screen_near_breakout,
        "label": "Near Breakout",
        "description": "Stocks near multi-month resistance with volume or momentum.",
        "category": "Price Action"
    },
    "low-debt-midcap": {
        "fn": screen_low_debt_midcap,
        "label": "Low Debt Midcaps",
        "description": "Quality midcaps with low debt and positive free cash flow.",
        "category": "Value"
    },
    "undervalued-fundamentals": {
        "fn": screen_undervalued_fundamentals,
        "label": "Undervalued Growth",
        "description": "Low PEG, high ROE, and efficient operations.",
        "category": "Value"
    },
    "momentum-monsters": {
        "fn": screen_momentum_monsters,
        "label": "Momentum Monsters",
        "description": "High relative strength and strong trend parameters.",
        "category": "Momentum"
    },
    "value-with-momentum": {
        "fn": screen_value_with_momentum,
        "label": "Value with Momentum",
        "description": "Reasonable valuation combined with recent price strength.",
        "category": "Momentum"
    },
    "steady-compounders": {
        "fn": screen_steady_compounders,
        "label": "Steady Compounders",
        "description": "High ROCE and consistent dividend payers.",
        "category": "Value"
    }
}
