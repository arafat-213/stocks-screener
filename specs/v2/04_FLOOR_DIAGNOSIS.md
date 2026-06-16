# Spec 04 — Floor Diagnosis Note (T1 → Phase 4 re-run → GO marginal)

> Written 2026-06-16, immediately after the T1 floor run returned **NO-GO**.
> The `04` §2 gate mandates this note on a NO-GO: *stop, diagnose data/costs/universe,
> do **not** start T2–T5, do **not** tune.* This document diagnoses; it changes no
> parameter. Re-running the floor is allowed **only** if diagnosis uncovers a genuine
> data/cost **bug** (still the same pre-committed config); changing a knob to make the
> number pass is tuning and is forbidden here.
>
> **Phase 4 re-run complete (2026-06-16).** After the §3.3 data bug was fixed (Spec 05,
> Phases 1–3), the floor was re-run on the same pre-committed config on rebuilt
> `prices_adjusted`. All `02 §10` invariants passed. New verdict: **GO (marginal)**.
> C_strat rose from 0.283 to **0.305**, crossing the C_nifty50 floor (0.302). Spec 04
> is now at a terminal GO state. Proceed to T2 under the marginal-GO branch.

---

## 1. The verdict, stated plainly (Rule 12)

Floor config: every `MomentumConfig` field at its spec-02 default (N=20, M=35, 5cr
liquidity, EMA_200, monthly, regime ON, cat-stop 25%), window **2018-02-06 → 2026-06-12**,
regime driven by the **real Nifty 50 price 200-DMA**. `02 §10` invariants all pass.

### T1 original run (corrupted data — 2026-06-16)

```
C_strat   = 0.283   (strategy Calmar, base costs)
C_nifty50 = 0.302   (Nifty 50 TRI Calmar)
C_primary = 0.448   (Nifty200 Momentum 30 TRI Calmar)   →  0.80 × = 0.359
NO-GO predicate:  C_strat (0.283) < C_nifty50 (0.302)   →  TRIPS  →  NO-GO
```

Diagnosed as corrupted input (§3.3). Verdict superseded by Phase 4 re-run below.

### Phase 4 re-run (rebuilt data — 2026-06-16)

```
C_strat   = 0.305   (strategy Calmar, base costs)
C_nifty50 = 0.302   (Nifty 50 TRI Calmar)
C_primary = 0.448   (Nifty200 Momentum 30 TRI Calmar)   →  0.80 × = 0.359
GO predicate:     C_strat (0.305) >= C_nifty50 (0.302)  →  CLEARS  →  GO (marginal)
GO predicate:     C_strat (0.305) < GO threshold (0.359) →  trails primary → MARGINAL
```

The floor clears the Nifty 50 TRI on Calmar after base costs — by a narrow margin (+1%).
It trails the primary benchmark significantly (gap 0.054, Calmar ratio 0.68). This is a
**marginal GO**: proceed to T2 with heightened scrutiny; the primary-tracking gap is the
main structural question.

**Honest framing:** the +22 bps lift in C_strat (0.283 → 0.305) came entirely from
removing the phantom split-cliff losses that had been biasing measured returns down.
Time-in-cash also fell from 51.2% → 46.1% (the phantom crashes had caused false exits
under the catastrophic-stop), which improved CAGR (+10.74% → +11.75%). The strategy
still earns less than the primary momentum index (CAGR gap ~3.5%) and the regime
overlay at 46% time-in-cash with ~970% annualised turnover remains the prime structural
suspect for the primary-tracking gap (§3.2).

---

## 2. Headline numbers

### Phase 4 re-run (rebuilt data — authoritative)

| | Strat (base) | Nifty50 TRI | Mom30 TRI (primary) | Mid50 TRI |
|---|---|---|---|---|
| CAGR | +11.75% | ~+11.55% | ~+15.2% | ~+19.3% |
| MaxDD | 38.51% | 38.27% | 33.96% | 36.39% |
| Calmar | 0.305 | 0.302 | 0.448 | 0.53 |
| Calmar ratio (strat/bench) | — | **1.01** | 0.68 | 0.57 |

Calmar-ratio matrix (strat / bench) across cost levels — Phase 4:

| Cost | Mom30 | Mid50 | Nifty50 |
|---|---|---|---|
| OPTIMISTIC | 0.77 | 0.65 | **1.14** |
| BASE | 0.68 | 0.57 | **1.01** |
| PESSIMISTIC | 0.59 | 0.50 | **0.88** |

Other floor diagnostics (base, Phase 4): Sharpe 0.76 · ann. vol 16.96% · **ann. turnover 972.6%**
· **time-in-cash 46.1%** · avg exposure 79.5% · median exposure 100.0% · 2,082 fills ·
hit rate 45.7% · 392 names traded · statutory cost ₹80,521 (slippage in P&L).

### T1 original run (corrupted data — superseded)

| | Strat (base) | Nifty50 TRI | Mom30 TRI (primary) | Mid50 TRI |
|---|---|---|---|---|
| CAGR | +10.74% | ~+11.55% | ~+15.2% | ~+19.3% |
| MaxDD | 37.99% | 38.27% | 33.96% | 36.39% |
| Calmar | 0.283 | 0.302 | 0.448 | 0.53 |
| Calmar ratio (strat/bench) | — | 0.94 | 0.63 | 0.53 |

Original Calmar-ratio matrix (strat / bench) — corrupted data, for reference only:

| Cost | Mom30 | Mid50 | Nifty50 |
|---|---|---|---|
| OPTIMISTIC | 0.72 | 0.60 | **1.07** |
| BASE | 0.63 | 0.53 | **0.94** |
| PESSIMISTIC | 0.54 | 0.46 | 0.81 |

---

## 3. Candidate root causes — to investigate, not to tune

Ordered by "could this overturn the verdict": the cost-model artifact check goes first
because it is the only one that could make NO-GO a *measurement* error rather than a real
structural finding.

### 3.1 Cost-model sanity (rule out artifact) — **RESOLVED 2026-06-16: NOT an artifact**

Investigated read-only via `backend/app/backtest_v2/diag_cost_sanity.py` (same
pre-committed floor config, real regime index, 3 cost levels; no parameter changed).
Cost-flow facts confirmed by code read (`costs.py`, `engine._stamp_fills`,
`portfolio.apply_fills`): `fill_cost()` returns **statutory + DP only**; **slippage** is
applied separately as an effective-price adjustment (buys fill higher, sells lower), so it
lives in cost basis / the equity curve, **not** in the `_total_cost_paid` counter.

Per-level decomposition over the floor window:

| level | final equity | notional traded | statutory (= reported "total cost") | slippage | **true cost** | **avg stat bps** |
|---|---|---|---|---|---|---|
| optimistic | ₹2,518,880 | ₹64.0M | ₹83,012 | ₹0 | **₹83,012** | **12.96** |
| base | ₹2,343,587 | ₹60.9M | ₹79,562 | ₹95,161 | **₹174,723** | **13.06** |
| pessimistic | ₹2,164,101 | ₹57.6M | ₹75,897 | ₹179,490 | **₹255,386** | **13.18** |

Findings:
- **The rupee "inversion" (₹83.0k > ₹79.6k > ₹75.9k) is a book-size effect, not a preset
  bug.** Avg statutory bps are level-invariant (12.96 / 13.06 / 13.18, <2% drift), so the
  statutory-only "total cost" line just tracks traded notional — and the optimistic path
  compounds to a larger book (₹2.52M vs ₹2.16M final; ₹64.0M vs ₹57.6M notional) → more
  statutory rupees despite *lower* true cost. Smoking gun confirmed.
- **True economic cost is correctly ordered opt < base < pess** (₹83k < ₹175k < ₹255k, a
  clean ~3× spread). The slippage the headline omits (₹0 / ₹95k / ₹179k) *is* in the equity
  curve — hence the 16% final-book spread across levels. Cost is wired into P&L (spec 03 §4
  acceptance #1/#2 hold).
- **Base is calibrated, not punitive:** ~13 bps/fill statutory (≈0.26% RT) + 0.15%/side
  slippage floor ≈ **~0.57% RT** — the honest ~2× correction of v1's optimistic flat 0.25%,
  matching the T0-verified live Zerodha rates. Not inflated.

**Verdict impact: none — NO-GO is NOT a cost artifact; if anything this strengthens it.**
Base costs are honest and conservative-but-fair and the strategy still can't clear Nifty 50
on Calmar (the verdict's Calmar/CAGR come from the equity curve, which already includes
slippage). The only legitimate floor-re-run trigger for §3.1 (a base-preset bug) is ruled
out. No re-run.

**One real finding (reporting, not measurement):** the floor report's `total cost ₹79,562`
line silently excludes slippage — it both understates true cost (₹174.7k at base) and
produces the confusing inversion. The verdict is unaffected, so this does **not** justify a
re-run, but the line should be relabeled (or made statutory+slippage) when work resumes.
Recommended, not urgent; flagged for Arafat.

### 3.2 Regime overlay whipsaw (structure / signal quality) — **dominant suspect**

> **CORRECTION (2026-06-16, post-T4 turnover decomposition — `diag_turnover_decomp.py`).**
> The turnover hypothesis below was **disproved by measurement.** On DISCOVERY (base cost)
> the ~934% turnover is **~90% membership churn** (top-20 names rotating across the
> rank-20/35 boundary monthly), only **~15% weight-reset**, and the **regime overlay is
> turnover-neutral-to-helpful** — turning it OFF *raised* turnover (934%→981%). The regime
> earns its keep on drawdown (regime-off maxDD 38%→48.6%). The regime overlay is **not**
> the turnover driver. It *may* still contribute to the *return* gap via cash drag (regime
> ON CAGR 10.05% < regime OFF 11.63% on DISCOVERY) — that part of the suspicion stands; the
> turnover part does not. See [[turnover-decomp-churn-dominant]] memory and §4 below.

**51.2% time-in-cash** with **median exposure 100%** means the book is binary: fully in or
fully out. Combined with **963.6% annualized turnover** (~80% of the book per monthly
rebalance), the real Nifty 50 200-DMA regime signal is very likely toggling risk-on/off
repeatedly — each toggle is a full liquidate-and-rebuy, which (a) burns cost and (b) sits
in cash through recoveries, explaining the return gap with no drawdown benefit. Investigate
(measurement only): count regime transitions over the window; measure return earned while
risk-off vs the market's return over those same spans (whipsaw test); attribute turnover
into regime-driven full exits vs buffer-driven rank churn. *Note:* the regime debounce /
risk-off floor is exactly T3's layer-1 calibration target — which means touching it now is
**tuning and is forbidden** under the gate. The diagnosis stops at "the regime overlay is
the prime structural suspect."

### 3.3 Universe quality / data integrity — **CONFIRMED SYSTEMIC DATA BUG (2026-06-16)**

Investigated read-only via `backend/app/backtest_v2/diag_universe_quality.py` (same floor
config, base cost; no parameter changed) plus a universe-wide scan. **A genuine,
systemic split/bonus adjustment failure was found in `prices_adjusted`** — this is the one
finding the `04` §2 gate treats as a legitimate fix-and-re-run trigger.

**The bug.** A clean split/bonus must step the back-adjustment factor so the adjusted
series stays continuous. Across **556 events within the floor window (2018-02-06 →
2026-06-12) on 406 distinct ISINs**, the raw price drops by a *clean split ratio* while
**both `adj_factor` and `tr_factor` stay flat** — so the adjustment is never applied. Ratio
clustering is unmistakable: 241× ~2:1, 12× ~5:1, 23× ~10:1, **zero** non-clean ratios (a
real crash would scatter; these don't). Because `close = close_raw × adj_factor` (and
`close_tr` likewise), the cliff propagates into **both** the adjusted **signal price**
(`open`/`close`, drives momentum ranking & fills) **and** the **P&L price** (`close_tr`,
drives MTM → equity → Calmar). It is not a cosmetic `close_raw` artifact.

**Worked example — CUPID (`INE509F01029`), ex-date 2026-03-09, held by the floor:**
prior close ₹402.20 → **gap-open ₹82.00, intraday high ₹93.20** (the stock never traded
between 402 and 93), close ₹91.60, volume 6.4M → **81.9M (13×)**, `adj_factor` =
`tr_factor` = **1.0 across the event**. Open ₹82.00 ≈ 402.20 / 5 = **₹80.44** → an
unadjusted **~5:1 split**, not a crash (a crash trades *down through* intermediate prices;
this is a clean gap to a new scale). The floor held CUPID across the ex-date and booked a
**phantom −77% MTM cliff and ₹−68,756 "realized" loss** that is not economically real
(post-split you hold 5× the shares at ⅕ the price).

**Verdict impact — the NO-GO is computed on corrupted input and cannot stand as-is.**
The bias is in the **verdict-dangerous direction**: a missed split injects a phantom
−50%…−90% drop on a *held* name, biasing measured strategy returns **downward** — i.e. it
could be **masking a GO**. (It also corrupts selection, since the phantom crash tanks that
name's momentum score, so the net portfolio sign is genuinely unknown.) This is exactly the
"genuine data bug → fix `prices_adjusted` + single re-run on the same pre-committed config"
path in §2. The floor must be **re-run on corrected data** before NO-GO (or GO) can be
trusted.

**Scope caution (Arafat's call, not yet authorized).** The fix is *not* a one-off CUPID
patch — it is a corporate-action adjustment rebuild touching the **holy data pipeline**
(`bhavcopy` adjustment layer), and it affects **every** backtest ever run in this project
(v1 and v2), not just the floor. This is a foundational data-integrity remediation that
must be scoped and approved before any code is written. Diagnosis stops here; it changes no
data and no parameter.

Secondary (structural, *not* a bug, does not by itself reopen the floor): of 392 traded
names, 30 had median hold-window ADV below the 5cr floor and 42 were ever stale-carried
(net ₹−270,777, −5.1% of gross |P&L|) — broad survivorship-free universe noise, expected.

---

## 4. Decision

**TERMINAL STATE: GO (marginal) — proceed to T2.** Spec 04 is complete. The floor on
rebuilt data (Phase 4 re-run, 2026-06-16) clears the Nifty 50 TRI on Calmar at base
costs. T2 is authorized under the marginal-GO branch.

**Diagnosis progress:**
- **§3.1 cost-model sanity — DONE (2026-06-16): NOT an artifact.** Base preset is calibrated
  (~0.57% RT, honest 2× of v1), per-trade cost is correctly ordered opt<base<pess (true cost
  ₹83k<₹175k<₹255k), and the rupee inversion is a pure book-size effect (statutory bps
  level-invariant). Not a measurement error. Reporting line relabeled (was "Total Cost Paid",
  now "Statutory Cost … (fees+DP only; slippage is in P&L)") in `metrics.summary` /
  `run_real` — verdict unaffected.
- **§3.3 universe / data integrity — DONE (2026-06-16): CONFIRMED SYSTEMIC DATA BUG → FIXED
  → RE-RUN → GO (marginal).** The adjustment layer silently dropped split/bonus back-adjustment
  on 556 in-window events / 406 ISINs. Fixed via ISIN succession bridge in `adjust.py`
  (Spec 05 Phases 1–3); rebuilt `prices_adjusted` (4,008,497 rows, 3,470 ISINs). Phase 4
  re-run on rebuilt data returned **GO (marginal)**: C_strat 0.305 > C_nifty50 0.302. The
  fix also reduced time-in-cash from 51.2% → 46.1% (phantom crashes had caused false
  catastrophic-stop exits).
- **§3.2 regime whipsaw — carryover diagnostic (not yet investigated, not blocking T2).**
  The regime overlay remains the prime structural suspect for the primary-tracking gap (Calmar
  ratio 0.68 vs 1.0 target): 46.1% time-in-cash with 972% annualised turnover. Calibrating
  the regime debounce / risk-off floor is T3's layer-1 work. The diagnosis stops here; T3
  is now authorized by the GO verdict.
