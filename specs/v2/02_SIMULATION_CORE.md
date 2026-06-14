# Spec 02 — v2 Simulation Core (time-driven daily loop)

> Depends on: `00_OVERVIEW.md`, `01_DATA_LAYER.md`. Build step 2.
> This replaces v1's symbol-first engine with a portfolio-first daily loop.

---

## 1. Core inversion

v1 simulates each symbol's trades in isolation, then reconciles the portfolio post-hoc.
v2 **iterates the trading calendar day by day**, holding the whole portfolio at once. This
is what makes daily mark-to-market, exposure tracking, and slot-level ranking natural.

The core object is no longer a `Trade`. It is the **portfolio state over time**: cash +
held positions, marked to market every day.

---

## 2. Module layout

```
backend/app/backtest_v2/
  __init__.py
  config.py        # MomentumConfig dataclass (stripped down — see §7)
  signals.py       # ranker + binary entry gate (uses indicators from v1 strategy.py)
  regime.py        # market-level risk-on/off overlay (simple)
  portfolio.py     # Portfolio state: cash, positions, MTM, apply fills
  engine.py        # the daily loop (orchestrator)
  metrics.py       # daily-MTM metrics incl. exposure, turnover, Calmar
  costs.py         # imported from spec 03
  types.py         # dataclasses: Position, Fill, RebalancePlan, DailySnapshot
```

Keep entirely separate from `backend/app/backtest/` (v1). Reuse only
`TechnicalStrategy.calculate_indicators` and `OHLCVCache`-style reads of the v2 parquet.

---

## 3. The daily loop (engine.py)

Pseudocode — the authoritative control flow:

```
load adjusted prices for all in-universe ISINs over [start - warmup, end]
precompute per-ISIN indicators once (EMAs, ATR, 12-1 momentum, vol) — vectorized
build trading calendar from the benchmark/index dates
rebalance_dates = last trading day of each month within [start, end]

portfolio = Portfolio(cash=starting_capital)
for day in calendar:
    # 1. MARK TO MARKET (every day, using adjusted close_tr for P&L)
    portfolio.mark_to_market(day, prices)
    record DailySnapshot(day, equity, invested_value, cash, n_positions, exposure)

    # 2. CATASTROPHIC STOP CHECK (intra-period, close-based, conservative)
    for pos in portfolio.positions:
        if close[pos.isin, day] <= pos.cost_basis * (1 - catastrophic_stop_pct):
            queue SELL pos at NEXT day's open   # executed in step 5 on next loop

    # 3. REGIME read (market overlay) — determines deployable fraction today
    deployable_fraction = regime.deployable_fraction(day)   # 1.0 risk-on, →0 risk-off

    # 4. REBALANCE (only on rebalance_dates) — decision at close, fills NEXT open
    if day in rebalance_dates:
        eligible = universe_membership(day) filtered by entry_gate(day) & liquidity floor
        ranked = sort eligible by ranker_score(day) desc
        plan = build_rebalance_plan(portfolio, ranked, deployable_fraction, config)
        queue plan.sells and plan.buys at NEXT day's open

    # 5. EXECUTE queued fills at THIS day's open (queued on the prior day)
    portfolio.apply_fills(this_day_open_fills, costs)
```

Key invariants:
- **All decisions use data ≤ decision date; all fills happen at the next session's open.**
  No same-bar decide-and-fill. No intrabar high/low peeking.
- Catastrophic stop triggers on **close** breach, fills next open (worst-case-friendly).
- MTM/P&L uses `close_tr` (total return). Signals/ranking use split+bonus-adjusted `close`.

---

## 4. Signals (signals.py)

Two **separate** concerns — do not merge them into a score.

**Binary entry gate** — a name is *eligible* to be held iff ALL:
- `close > EMA_200` (long-term uptrend; SMA_200 acceptable, pick one and document).
- `momentum_12_1 > 0` (absolute momentum filter).
- `adv_20 >= liquidity_floor` on the decision date.
- (optional, config) regime is risk-on — but prefer to express regime via
  `deployable_fraction` in §5, not as a hard per-name gate.

**Ranker** — among eligible names, rank by **volatility-adjusted momentum**:
- Default: `momentum_12_1 / annualized_volatility` where vol = stdev of daily (or weekly)
  returns over a lookback (e.g. 126 trading days), annualized.
- Alternative to A/B later (do not build both now): index-style composite — z-score of
  risk-adjusted 6M and 12M returns, averaged. Keep the interface pluggable
  (`ranker(day, isin) -> float`) so swapping is a one-line change.

`momentum_12_1(day)` = `close[day-21] / close[day-273] - 1` (≈12 months ending 1 month ago).
Use calendar-aware index positions, not naive shifts across gaps.

---

## 5. Rebalance plan + membership buffer (portfolio.py)

`build_rebalance_plan(portfolio, ranked, deployable_fraction, config)`:

1. **Sell discipline (hysteresis):** for each current holding, find its rank in `ranked`.
   - Sell if its rank > `sell_rank_M` (fell out of the buffer) OR it no longer passes the
     entry gate (e.g. dropped below EMA200) OR it's flagged by catastrophic stop.
   - Otherwise **hold** (let winners run).
2. **Target membership:** desired holdings = current holds that survived + top names from
   `ranked` (rank ≤ `buy_rank_N`) until we have `target_positions` names.
3. **Weighting:** equal weight. `target_weight = deployable_fraction / target_positions`,
   capped at `max_position_pct`. Capital not allocated (too few eligible names, or
   `deployable_fraction < 1`) **stays in cash** — never force deployment.
4. **Reset to target each rebalance** (equal-weight reset): compute target ₹ per name from
   current equity; produce buy/trim/sell deltas. (The "let winners run without re-weighting"
   variant is a later test, not v1.)
5. Emit `RebalancePlan(sells=[...], buys=[...], trims=[...])` as next-open fills.

Constraints applied here (config-driven, default off/loose to keep the floor simple):
- `max_sector_positions` (needs a sector map; if unavailable from bhavcopy, defer).
- `max_position_pct` single-name cap.

> Turnover is the cost driver. The buffer (N<M) and "hold survivors" rule exist to keep
> turnover sane. Track it (see §6) and treat runaway turnover as a red flag, not a detail.

---

## 6. Portfolio state & mark-to-market (portfolio.py)

`Position`: `isin, symbol, shares, cost_basis, entry_date, last_price`.
`Portfolio`: `cash, positions: dict[isin, Position]`.

- `mark_to_market(day, prices)`: `equity = cash + Σ shares_i * close_tr[i, day]`.
  Handle a held name with no print that day (suspension): carry last known price, flag it.
- `apply_fills(fills, costs)`: for each fill at `open` price, compute cost via `costs.py`
  (spec 03), update cash, shares, cost_basis. A buy of a new name creates a Position; a
  full sell removes it; trims/adds adjust shares.
- Every day append a `DailySnapshot`: `date, equity, cash, invested_value,
  exposure = invested_value/equity, n_positions`. This is the equity curve and the
  exposure series — both first-class outputs.

---

## 7. Config (config.py) — deliberately small

```python
@dataclass
class MomentumConfig:
    # universe / selection
    target_positions: int = 20          # N: buy when rank <= N
    sell_rank_buffer: int = 35          # M: sell when rank > M (M > N)
    liquidity_floor_cr: float = 5.0     # adv_20 >= this (₹ crore), decision-date
    # ranking
    momentum_lookback_days: int = 252
    momentum_skip_days: int = 21        # the "1" in 12-1
    vol_lookback_days: int = 126
    # trend gate
    trend_ma: str = "EMA_200"           # or "SMA_200"
    # weighting / sizing
    max_position_pct: float = 10.0
    starting_capital: float = 1_000_000.0
    # risk overlay
    use_regime_overlay: bool = True
    catastrophic_stop_pct: float = 25.0
    # rebalance
    rebalance: str = "monthly"          # the one structural knob we may sweep later
    # dates
    date_from: date = None
    date_to: date = None
```

No scoring weights. No holding_days/target/RR/partial/pullback/tier/MTF fields. If you feel
the urge to add one, re-read `00_OVERVIEW §2.6` — adding layers made v1 worse.

---

## 8. Regime overlay (regime.py) — keep it dumb

A single market-level signal driving `deployable_fraction(day) ∈ [0, 1]`:
- Risk-on (1.0) when the benchmark index `close > its 200-DMA`; risk-off (→ a floor like
  0.0–0.3) when below, with a small confirmation/debounce (e.g. N consecutive days) to
  avoid whipsaw at the line.
- That's it. No multi-state hysteresis maze, no breadth+RSI+ADX override lattice. This is
  the *one* layer whose job is drawdown control; prove it earns its keep in `04` before
  elaborating it.

---

## 9. Outputs

- `DailySnapshot` series → equity curve, exposure curve.
- Realized fills/positions log (for audit).
- Per-rebalance turnover.
- Hand off to `metrics.py` (daily-MTM Sharpe, CAGR, max DD, Calmar, avg/median exposure,
  annualized turnover, hit rate of held names, contribution by name). See `03` for the
  benchmark-relative metrics.

---

## 10. Acceptance criteria

1. **No-lookahead test:** shifting all decision logic to use only ≤ D data and fills at
   D+1 open is enforced; add a unit test that corrupts future data and asserts results are
   unchanged for decisions up to D.
2. **Cash conservation:** `equity == cash + Σ shares*price` every day to within rounding;
   total cost paid == Σ per-fill costs.
3. **Determinism:** same config + data → identical equity curve.
4. **Exposure sanity:** in a sustained downtrend with `use_regime_overlay=True`, average
   exposure drops materially vs overlay off.
5. **Turnover sanity:** monthly rebalance with buffer yields plausible annualized turnover
   (flag if absurd, e.g. >1000%).
6. Reproduces a v1-style run *direction* on the same (biased) data as a smoke check before
   switching to honest data — not for correctness, just to catch gross wiring bugs.
