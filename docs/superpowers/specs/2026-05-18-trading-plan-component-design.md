# Trading Plan Component Design Spec

**Date:** 2026-05-18
**Status:** Approved

## Goal
Create a reusable `TradingPlan` component to display actionable trade setup details (Entry, Stop Loss, Targets) derived from technical analysis.

## Architecture
- **Component:** `TradingPlan.jsx`
- **Styles:** `TradingPlan.css`
- **Icons:** `lucide-react` (Target, ShieldAlert, Zap)

## Data Structure
The component expects a `setup` object prop:
```json
{
  "setup_type": "BREAKOUT",
  "entry_zone": { "low": 2450.0, "high": 2465.0 },
  "stop_loss": 2410.5,
  "stop_basis": "Below EMA 20",
  "targets": [
    { "rr": "2", "level": 2540.0 },
    { "rr": "3", "level": 2585.0 }
  ],
  "risk_per_share": 45.5,
  "atr": 32.4
}
```

## Design Details
- **Theme Support:** Uses CSS variables for light/dark mode compatibility.
- **Visual Hierarchy:**
  - Header with icon and setup type.
  - Grid layout for Entry and Stop Loss.
  - Pill-style targets for 2R/3R levels.
  - Footer with secondary metrics (Risk, ATR).
- **Colors:**
  - Bullish/Targets: `--color-bullish` (#22C55E)
  - Bearish/Stop Loss: `--color-bearish` (#EF4444)
  - Primary: `--color-primary` (#3B82F6)

## Implementation Steps
1. Create `frontend/src/components/TradingPlan.jsx`.
2. Create `frontend/src/components/TradingPlan.css`.
3. Verify component renders correctly with sample data.
4. Commit changes.
