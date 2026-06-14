# Spec 03 — Cost Model & Benchmark Wiring

> Depends on: `00`, `01`, `02`. Build step 3.
> A wrong cost model or a wrong benchmark makes every later decision wrong.

---

## 1. Cost model (costs.py)

v1 used a flat 0.25% round-trip. That is optimistic — it ignores STT, flat DP charges, and
slippage. Model cost **per fill** (not per round-trip), as a function of trade value and
liquidity. Delivery equity (we hold weeks → delivery, not intraday).

### 1.1 Components (verify exact rates at build time — they change)

For **delivery** equity on a discount broker (Zerodha assumed):

| Component | Buy | Sell | Notes |
|---|---|---|---|
| Brokerage | ₹0 | ₹0 | Zerodha delivery is free |
| STT | 0.1% | 0.1% | on turnover; the dominant statutory cost (~0.2% RT) |
| Exchange txn | ~0.00297% | ~0.00297% | NSE |
| SEBI charges | ~0.0001% | ~0.0001% | negligible |
| Stamp duty | 0.015% | 0 | buy side only |
| GST | 18% on (brokerage+txn) | same | brokerage 0 → tiny |
| DP charges | 0 | ~₹13–16 flat | **per scrip on sell**, flat → hurts small positions |

Statutory + DP, perfect fill ≈ **~0.30% round-trip** on a moderate position. **Slippage is
extra and dominates on mid/smallcaps.**

### 1.2 Slippage (the part that actually matters)

Model slippage as a function of order value vs liquidity (`adv_20` from spec 01):

```
participation = order_value / adv_20
slippage_pct  = base_slippage_pct + impact_coeff * participation
# clamp to a sane ceiling; widen for low-ADV names
```

Defaults to start (conservative, tune later, never optimize down to flatter unphysically):
- `base_slippage_pct = 0.15%` per side (spread/queue),
- `impact_coeff` chosen so a 1%-of-ADV order adds ~0.1–0.2% — calibrate against literature,
- Enforce a **liquidity floor** (spec 01/02) so participation stays small; if an order
  would exceed e.g. 5–10% of ADV, **cap the position size** rather than pay fantasy fills.

### 1.3 Interface

```python
def fill_cost(side: str, qty: int, price: float, adv_20: float, cfg: CostConfig) -> float:
    """Return total ₹ cost (statutory + flat + slippage) for one fill.
       Slippage is realized by adjusting the effective fill price, not as a
       fee-only term, so it also moves cost basis / realized P&L."""
```

Apply slippage to the **effective fill price** (buys fill higher, sells fill lower) AND add
the statutory+flat charges as cash deductions. Do not double-count.

### 1.4 Sensitivity is mandatory

Any headline result must be reported at **three cost levels**: optimistic (~0.3% RT, no
slippage), **base** (the model above), pessimistic (2× slippage). If the edge only exists
at the optimistic level, there is no edge. Make cost level a first-class run parameter.

---

## 2. Benchmark wiring (benchmark.py)

### 2.1 Which benchmark (LOCKED)

- **Primary:** Nifty200 Momentum 30 **TRI**.
- **Secondary:** Nifty Midcap150 Momentum 50 **TRI** (use if the traded universe skews mid).
- Also load **Nifty 50 TRI** as a sanity floor (are we even beating large-cap beta?).

TRI (total return) — not price index — so dividends are comparable to our `close_tr` P&L.
Source: niftyindices.com historical index data (free; verify download method at build time).

### 2.2 Alignment rules

- Align benchmark to the **same trading calendar** and the **same date window** as the run
  (slice off the indicator warmup period — do not let warmup dilute benchmark return, the
  bug noted in v1 `compute_metrics`).
- Rebase both strategy equity and benchmark to the same starting capital at `date_from`.
- Compute benchmark daily returns from TRI closes for an apples-to-apples Sharpe.

### 2.3 The regime overlay uses a *price* index

The market-regime overlay (`02 §8`) reads the **price** index 200-DMA (Nifty 50 or Nifty 200
price index), not the momentum TRI. Keep the two roles distinct: price index → regime
signal; momentum TRI → performance benchmark.

---

## 3. Metrics (metrics.py) — honest, daily-MTM, benchmark-relative

All computed from the v2 **daily** equity curve (not step-on-exit like v1).

**Absolute:**
- CAGR (from first to last daily equity, calendar-time annualized).
- Daily-MTM Sharpe (mean/stdev of daily returns × √252).
- Sortino (downside dev).
- Max drawdown (from daily equity), max DD duration.
- **Calmar = CAGR / max DD** ← the primary objective metric.
- Avg / median **exposure**, time-in-cash %.
- Annualized **turnover**.
- Volatility (annualized).

**Benchmark-relative (vs Nifty200 Momentum 30 TRI):**
- Excess CAGR.
- **Calmar ratio of strategy ÷ Calmar of benchmark** (the headline — must be > 1).
- Max-DD ratio (strategy ÷ benchmark) — **target ≤ 0.70** per the locked goal.
- Information ratio (excess return / tracking error).
- Up/down capture vs benchmark.
- Correlation / beta to benchmark.

**Per-name diagnostics:** contribution to return, hold-period distribution, hit rate of
held names, biggest winners/losers (sanity-check for data glitches, not for tuning).

---

## 4. Acceptance criteria

1. Reducing slippage to 0 and statutory to v1's flat 0.25% reproduces v1-style cost drag —
   confirms the model is wired into P&L, not bolted on cosmetically.
2. Slippage moves cost basis (a buy's realized return starts slightly negative pre-move).
3. Benchmark TRI loaded, calendar-aligned, warmup-sliced; benchmark Sharpe/Calmar computed.
4. The three-cost-level report renders for any run.
5. Max-DD ratio and Calmar ratio vs benchmark are computed and printed prominently — they
   are the pass/fail numbers for the whole project.
