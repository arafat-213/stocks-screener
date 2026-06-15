# Spec 03 — Cost Model & Benchmark Wiring

> Depends on: `00`, `01`, `02`. Build step 3.
> A wrong cost model or a wrong benchmark makes every later decision wrong.

---

## Verified findings (T0)

> Resolved at: 2026-06-15. Session: T0 verification spike (no production code).
> Sources verified live against Zerodha and niftyindices.com.

### A. Confirmed cost rates — Zerodha delivery equity (current as of June 2026)

Zerodha delivery brokerage is ₹0 (free). All costs below are statutory/regulatory.
NSE exchange transaction charge was revised downward on **October 1, 2024** (from 0.00322% to 0.00297%).

| Component | Buy | Sell | Notes |
|---|---|---|---|
| Brokerage | ₹0 | ₹0 | Zerodha delivery is free — source: [zerodha.com/charges](https://zerodha.com/charges/) |
| STT | **0.1%** | **0.1%** | On turnover; dominant statutory cost (~0.2% RT) |
| NSE exchange txn | **0.00297%** | **0.00297%** | Revised Oct 1, 2024 — source: [Zerodha Z-Connect](https://zerodha.com/z-connect/business-updates/revision-in-exchange-transaction-charges-and-securities-transaction-tax-from-october-1-2024) |
| SEBI charges | **0.0001%** | **0.0001%** | ₹10 per crore — source: [zerodha.com/charges](https://zerodha.com/charges/) |
| Stamp duty | **0.015%** | **0%** | Buy side only (₹1,500/crore) |
| GST | **0.000553%** | **0.000553%** | 18% × (exchange txn 0.00297% + SEBI 0.0001%); brokerage = 0 so tiny |
| DP charges | ₹0 | **₹15.34 flat/scrip** | ₹3.50 CDSL + ₹9.50 Zerodha + ₹2.34 GST; per-scrip on sell regardless of qty |

**Per-fill statutory totals (approximate, excluding DP):**
- Buy: 0.1% + 0.00297% + 0.0001% + 0.015% + 0.000553% ≈ **0.1186%**
- Sell (excl. DP): 0.1% + 0.00297% + 0.0001% + 0.000553% ≈ **0.1036%**
- Round-trip (excl. DP): ≈ **0.222%**; add DP ₹15.34/scrip → effective RT rises with position size (larger positions = smaller DP %-impact)

These numbers go directly into `CostConfig` in T1.

---

### B. Slippage defaults + calibration rationale

Model (per spec §1.2):
```
participation  = order_value / adv_20
slippage_pct   = base_slippage_pct + impact_coeff × participation
                 (clamped at participation_cap)
```

**Chosen defaults (conservative; tuned in spec 04, never optimized down here):**

| Parameter | Value | Rationale |
|---|---|---|
| `base_slippage_pct` | **0.0015** (0.15%/side) | Spread + queue cost for NSE mid/smallcap delivery; zero-participation floor |
| `impact_coeff` | **0.15** | Calibrated so 1%-of-ADV order adds 0.15 × 0.01 = 0.15% → total 0.30%/side; within the 0.1–0.2% additional range the spec targets |
| `participation_cap` | **0.10** (10% of ADV) | Position is capped if order_value > 10% of adv_20; protects against illiquid fills |

**Calibration check (spec §1.2 requirement: 1%-of-ADV order adds ~0.1–0.2% additional):**
- At participation = 0.01: additional = 0.15 × 0.01 = **0.0015 = 0.15%** ✓ (within 0.10–0.20% range)
- At participation = 0.05: additional = 0.15 × 0.05 = 0.75% → total = 0.90%/side (expected penalty for illiquid fills)
- At participation = 0.10 (cap): additional = 0.15 × 0.10 = 1.50% → effectively a hard wall

**Literature basis:** Linear temporary-impact model consistent with Almgren-Chriss (2000) at small participation rates; for Indian mid/smallcap equity, empirical estimates suggest 0.10–0.25% spread cost at open + participation-scaled impact. Conservative calibration is intentional per spec rule — tuning sweeps belong in spec 04.

---

### C. niftyindices.com TRI download method (confirmed working)

**Method:** HTTP POST to `https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString`

**Required steps:**
1. GET `https://www.niftyindices.com` first (warm-up — establishes session cookie)
2. POST with headers: `Content-Type: application/json; charset=utf-8`, `X-Requested-With: XMLHttpRequest`, `Referer: https://www.niftyindices.com/reports/historical-data`
3. Payload: `{"cinfo": "<JSON-encoded string: {name, startDate, endDate, indexName}>"}` where dates are `"DD-Mon-YYYY"` format (e.g. `"01-Jan-2024"`)
4. Response: JSON `{"d": "<JSON-string array of row objects>"}` — parse `d` as JSON

**Confirmed index name strings (exact, case-sensitive as the API accepts them):**

| Series | API name string |
|---|---|
| Nifty200 Momentum 30 TRI (primary benchmark) | `"NIFTY200 Momentum 30"` |
| Nifty Midcap150 Momentum 50 TRI (secondary) | `"NIFTY MIDCAP150 Momentum 50"` |
| Nifty 50 TRI (sanity floor) | `"Nifty 50"` |

**Column names (all three series):** `['RequestNumber', 'Index Name', 'Date', 'TotalReturnsIndex', 'NTR_Value']`

**Key column for benchmark:** `TotalReturnsIndex` (string; parse as float)

**Verbatim first rows (fetched 2026-06-15, date range 01-Jan-2024 to 31-Jan-2024):**

```
Nifty200 Momentum 30:
{'RequestNumber': 'TRI63917115692712165300', 'Index Name': 'Nifty200 Momentum 30',
 'Date': '31 Jan 2024', 'TotalReturnsIndex': '35727.81', 'NTR_Value': '-'}

Nifty Midcap150 Momentum 50:
{'RequestNumber': 'TRI63917115692774507600', 'Index Name': 'Nifty Midcap150 Momentum 50',
 'Date': '31 Jan 2024', 'TotalReturnsIndex': '64036.58', 'NTR_Value': '-'}

Nifty 50:
{'RequestNumber': 'TRI63917115692837063900', 'Index Name': 'Nifty 50',
 'Date': '31 Jan 2024', 'TotalReturnsIndex': '31939.59', 'NTR_Value': '28933.54'}
```

---

### D. Regime price index — source + method

**Chosen index:** **Nifty 50** (price, not TRI) — standard broad-market regime indicator for Indian equity strategies; widely used for 200-DMA market-health signals.

**Endpoint:** `https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString`
**Same warm-up + headers as the TRI endpoint.** Payload `cinfo` uses the same format.

**API name string:** `"Nifty 50"`

**Column names:** `['RequestNumber', 'Index Name', 'INDEX_NAME', 'HistoricalDate', 'OPEN', 'HIGH', 'LOW', 'CLOSE']`

**Key column for regime 200-DMA:** `CLOSE` (the `engine.run(index_prices=...)` series)

**Verbatim first row (fetched 2026-06-15, same date range):**
```
{'RequestNumber': 'His63917115706613247900', 'Index Name': '', 'INDEX_NAME': 'Nifty 50',
 'HistoricalDate': '31 Jan 2024', 'OPEN': '21487.25', 'HIGH': '21741.35',
 'LOW': '21448.85', 'CLOSE': '21725.70'}
```

**Distinct from TRI:** the price index endpoint (`getHistoricaldatatabletoString`) returns OHLC; the TRI endpoint (`getTotalReturnIndexString`) returns `TotalReturnsIndex`. Do not feed the TRI into regime.

---

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
