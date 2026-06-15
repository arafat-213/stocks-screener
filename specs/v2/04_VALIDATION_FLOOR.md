## Locked decisions (T0)

> Locked 2026-06-15. Do not move any boundary here to make a config pass (Rule 12).

### Usable data window

Probed via `store.read_prices_adjusted()` on 2026-06-15:

| Metric | Value |
|---|---|
| Raw data start | 2017-01-02 |
| Raw data end | 2026-06-12 |
| Distinct ISINs | 3,470 |
| Trading days on disk | 2,331 |
| Warmup required | 273 trading days (`momentum_lookback_days=252` + `momentum_skip_days=21`) |
| **First usable decision date** | **2018-02-06** |
| **Usable backtest window** | **2018-02-06 → 2026-06-12** (~8.3 years) |

The warmup of 273 trading days maps to ~13 months from the data start (2017-01-02),
landing the first valid `momentum_12_1` signal on 2018-02-06.

---

### Floor → `MomentumConfig` field map

All `04` §2 prose fields match `MomentumConfig` defaults exactly. **No drift.**

| Spec §2 description | `MomentumConfig` field | Default value | Drift? |
|---|---|---|---|
| Hold top 20 | `target_positions` | `20` | None |
| Buffer sell at 35 | `sell_rank_buffer` | `35` | None |
| Liquidity floor (₹ crore ADV-20) | `liquidity_floor_cr` | `5.0` | None (spec says "liquidity-floored"; 5cr is the spec 01/02 established value) |
| Rank: `momentum_12_1` lookback | `momentum_lookback_days` | `252` | None |
| The "1" skip in `12-1` | `momentum_skip_days` | `21` | None |
| Vol denominator lookback | `vol_lookback_days` | `126` | None |
| `close > 200-MA` gate | `trend_ma` | `"EMA_200"` | None |
| Equal-weight | (no field; engine default) | — | None |
| Monthly rebalance | `rebalance` | `"monthly"` | None |
| Regime overlay ON | `use_regime_overlay` | `True` | None |
| Catastrophic stop 25% | `catastrophic_stop_pct` | `25.0` | None |
| Costs at base level | `cost_level` (engine param, not config) | `"base"` | None |

The floor config is simply `MomentumConfig(date_from=date(2018, 2, 6), date_to=date(2026, 6, 12))` with all other fields at defaults.

---

### FROZEN date splits

```python
# Immutable — do not adjust to make a config pass (Rule 12)
USABLE_START  = date(2018, 2, 6)   # first post-warmup decision date
USABLE_END    = date(2026, 6, 12)  # last date on disk (2026-06-15 probe)

# T1 floor runs on the FULL usable window (single pre-committed config, no OOS budget spent)
FLOOR_START   = USABLE_START
FLOOR_END     = USABLE_END

# Discovery: all §4 iteration runs here only
DISCOVERY     = (date(2018, 2, 6), date(2023, 6, 30))   # ~5.4 years in-sample

# Final OOS: looked at EXACTLY ONCE in T5, for the chosen config
FINAL_OOS     = (date(2023, 7, 1), date(2026, 6, 12))   # ~3 years held-out
```

Non-overlap: confirmed — `DISCOVERY[1]` (2023-06-30) < `FINAL_OOS[0]` (2023-07-01). No shared dates.

Rationale for the 2023-07 split: provides ~3 years of clean OOS covering two distinct market regimes (post-Covid normalization + 2024–25 mid/smallcap correction), while leaving ~5.4 years of discovery for robust walk-forward folding.

---

### Decision-rule predicates (GO / NO-GO)

Let:
- `C_strat` = strategy Calmar at **base** cost level over the floor window
- `C_primary` = Nifty200 Momentum 30 TRI Calmar over the same window
- `C_nifty50` = Nifty 50 TRI Calmar over the same window

**GO predicate** (proceed to T2):
```
C_strat >= 0.80 × C_primary
```
Interpretation: strategy Calmar at base costs is at least 80% of the primary benchmark's
Calmar. "Roughly tracks" = within 20% of the benchmark — tight enough to confirm a real
foundation, loose enough not to demand the floor beats a purpose-built momentum index outright.

**NO-GO predicate** (stop; diagnose data/costs; do not build T2–T5; do not tune):
```
C_strat < C_nifty50
```
Interpretation: if the strategy can't beat even the plain Nifty 50 on a risk-adjusted basis
after real costs, the problem is structural (universe quality, cost model, data), not
parameter choice. Tuning cannot fix a broken foundation.

**Middle zone** (`C_nifty50 ≤ C_strat < 0.80 × C_primary`): beats the floor benchmark but
falls short of tracking the primary. Treat as a marginal GO — proceed with heightened
scrutiny; document the gap explicitly in the T1 session log.

---

### Anti-overfit method (T2 implementation target)

**Deflated Sharpe Ratio (DSR):**
Bailey & López de Prado (2016), *"The Deflated Sharpe Ratio: Correcting for Selection Bias,
Backtest Overfitting, and Non-Normality"*, Journal of Portfolio Management.

Formula: adjusts the annualized Sharpe for (a) the expected maximum Sharpe under the null
when `K` configs are tried, (b) non-normality via skewness and excess-kurtosis of the returns
distribution, and (c) the number of independent trials. Implementation target: apply to each
walk-forward window's OOS Sharpe, reporting both raw and deflated values.

**PBO (Probability of Backtest Overfitting):**
Bailey & López de Prado (2014), *"The Probability of Backtest Overfitting"*, Journal of
Computational Finance. Method: Combinatorially Symmetric Cross-Validation (CSCV). Partition
the `T` walk-forward OOS sub-periods into all `C(T, T/2)` combinations; for each combination,
identify the config that ranked best in-sample, observe its OOS rank; PBO = fraction of
combinations where that config ranked below the median OOS performer. PBO ∈ [0, 1]; values
> 0.5 indicate near-certain overfitting. T2 must implement this against the walk-forward fold
set, not a static split.

---

*T0 done-criteria checklist:*
- [x] Real usable backtest window (post-warmup) recorded from on-disk data.
- [x] Floor config mapped field-by-field; no prose↔default drift found.
- [x] `DISCOVERY` and `FINAL_OOS` ranges frozen as explicit values (non-overlapping).
- [x] Decision-rule GO and NO-GO predicates stated numerically.
- [x] Deflated-Sharpe + PBO method named with citations.

---

# Spec 04 — Validation Floor & Anti-Overfit Methodology

> Depends on: `00`–`03`. Build step 4 — and the gate for everything after.
> The point of v2 was honest measurement. This spec defines what "honest" means
> and forbids the overfitting that made v1's sweep meaningless.

---

## 1. The order of operations (do not violate)

1. Build data layer (`01`) and **pass its acceptance checks**.
2. Build engine + costs + benchmark (`02`, `03`).
3. **Establish the floor** (this spec, §2) — the simplest possible momentum portfolio,
   measured honestly. **No tuning yet.**
4. Only if the floor is sound, iterate **one layer at a time** (§4) with plateau-based,
   not point-based, selection.

You may **not** run a parameter sweep before the floor is established. v1's mistake was
optimizing on a biased, optimistically-measured harness. Fix the measuring stick first.

---

## 2. The floor: simplest momentum portfolio

Run exactly one config, no search:

- Universe: point-in-time, survivorship-free, liquidity-floored (`01`).
- Gate: `close > 200-MA` AND `momentum_12_1 > 0` AND liquidity floor.
- Rank: `momentum_12_1 / annualized_vol`.
- Hold top 20 (buffer sell at 35), equal-weight, monthly rebalance.
- Regime overlay ON (deployable fraction from index 200-DMA).
- Catastrophic stop 25%. Costs at **base** level (`03`).

**Decision rule:**
- If this floor roughly **tracks or beats Nifty200 Momentum 30 TRI on Calmar after base
  costs** → you have a real foundation; proceed to §4.
- If it badly underperforms even the **Nifty 50 TRI** after costs → stop. The problem is
  the universe, the costs, or the data — not the parameters. Diagnose, do not tune.

Report the floor at all three cost levels (`03 §1.4`) and vs all three benchmarks.

---

## 3. Why honest measurement changes the bar

Re-establish expectations from a clean baseline. Likely findings to be ready for:
- After survivorship correction + real costs, returns will be **lower** than v1 reported.
  That is the point — v1's numbers were partly artifacts.
- Beating the momentum index on **raw CAGR** after costs is hard (the index is already good
  momentum). The realistic, defensible edge is **risk-adjusted** (Calmar / lower max DD via
  the regime overlay). The locked target reflects this: **max DD ≤ 70% of benchmark** while
  matching CAGR. Hold the line on this target; do not move it to make a config "pass."

---

## 4. Controlled iteration (only after a sound floor)

Add **one** layer at a time. Each must justify itself economically *before* testing, and
survive on a **plateau**, not a point.

Candidate layers, in rough priority:
1. Regime overlay calibration (debounce days, risk-off floor) — drawdown control.
2. Ranker variant (12-1 vol-adjusted vs index-style 6M/12M composite).
3. Rebalance cadence (monthly vs the structural alternative) — turnover vs decay trade-off.
4. Position count N / buffer M (concentration vs diversification).
5. Liquidity floor level (alpha vs tradeability).

Rules:
- **Plateau, not peak.** A parameter is acceptable only if a *contiguous neighborhood* of
  values all perform similarly well. A lone spiky optimum surrounded by poor values is
  overfit — reject it. (This is the cheapest, most reliable overfit defense.)
- Coarse grids only. No 1700-combo sweeps. If a layer needs a huge grid to find a winner,
  the layer is noise.
- Change one thing; keep everything else at the floor values.

---

## 5. Walk-forward & out-of-sample discipline

- **Multiple comparisons is the enemy.** Every config you test on a fixed OOS window burns
  it. v1 hit a handful of reused OOS folds with thousands of configs — guaranteed false
  positive eventually.
- Split history into **discovery** and **validation** with a clean date boundary (no
  overlap). Do all §4 iteration on discovery only.
- **Reserve one final, contiguous, recent OOS block that you look at exactly once**, at the
  very end, for the chosen config. If it fails there, it fails — do not iterate against it.
- Prefer **walk-forward** (rolling discovery→OOS windows) over a single split, so the result
  isn't a function of one lucky period.
- Be aware of **deflated Sharpe / PBO** (probability of backtest overfitting): with K configs
  tried, the expected best in-sample Sharpe under the null is positive. Track how many
  configs you tried and discount accordingly. If you can, compute a deflated Sharpe.

---

## 6. Robustness checks before believing any winner

A config is only a candidate after it survives:
1. **Cost stress:** still beats the benchmark Calmar at the **pessimistic** cost level.
2. **Universe perturbation:** drop the top-10 contributing names — does the edge persist, or
   was it a handful of (possibly glitchy) outliers? Cross-check those names' adjusted data.
3. **Parameter neighborhood:** plateau check (§4).
4. **Subperiod stability:** positive-ish across bull / bear / chop subperiods, not one regime
   carrying everything (v1's edge was almost entirely the 2021 bull — explicitly avoid this).
5. **Turnover/capacity:** annualized turnover and average participation vs ADV are within
   tradeable limits at the intended capital. A strategy you can't fill isn't a strategy.

---

## 7. Definition of done for v2

v2 is "validated" only when a **single, pre-committed config**:
- Beats Nifty200 Momentum 30 TRI on **Calmar** after **base** costs, with **max DD ≤ 70%**
  of the benchmark, on **discovery**, AND
- Holds up at **pessimistic** costs and across **subperiods** (§6), AND
- Passes the **one-shot final OOS** block (§5) without re-tuning, AND
- Is tradeable on turnover/capacity (§6.5).

Anything less is a research note, not a deployable strategy. Report it honestly (CLAUDE.md
Rule 12 — fail loud); do not soften a miss into a "promising" result.

---

## 8. What success unlocks (out of scope here)

Only after §7: wire the validated config into the live signal path (shared
`TechnicalStrategy` indicators keep parity), switch live OHLCV to Kite with the parity
check (`01 §8`), and paper-trade before real capital. Do not skip paper trading.
