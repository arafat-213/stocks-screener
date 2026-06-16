# Spec 04 — Floor Diagnosis Note (T1 = NO-GO)

> Written 2026-06-16, immediately after the T1 floor run returned **NO-GO**.
> The `04` §2 gate mandates this note on a NO-GO: *stop, diagnose data/costs/universe,
> do **not** start T2–T5, do **not** tune.* This document diagnoses; it changes no
> parameter. Re-running the floor is allowed **only** if diagnosis uncovers a genuine
> data/cost **bug** (still the same pre-committed config); changing a knob to make the
> number pass is tuning and is forbidden here.

---

## 1. The verdict, stated plainly (Rule 12)

Floor config: every `MomentumConfig` field at its spec-02 default (N=20, M=35, 5cr
liquidity, EMA_200, monthly, regime ON, cat-stop 25%), window **2018-02-06 → 2026-06-12**,
regime driven by the **real Nifty 50 price 200-DMA**. `02 §10` invariants all pass.

Decision predicate (T0), base cost level:

```
C_strat   = 0.283   (strategy Calmar, base costs)
C_nifty50 = 0.302   (Nifty 50 TRI Calmar)
C_primary = 0.448   (Nifty200 Momentum 30 TRI Calmar)   →  0.80 × = 0.359
NO-GO predicate:  C_strat (0.283) < C_nifty50 (0.302)   →  TRIPS  →  NO-GO
```

The floor does not clear even the plain Nifty 50 TRI on Calmar after base costs, and
trails the purpose-built primary momentum index badly (Calmar ratio 0.63).

**Honest framing (do not soften — and do not catastrophize):** the miss vs the Nifty 50
floor is *narrow* (~6%) and is a **return** gap, not a drawdown gap — strategy MaxDD
(37.99%) is actually marginally *better* than Nifty 50 TRI (38.27%). The strategy simply
earns slightly less return (CAGR 10.74% vs ~11.55%) for comparable risk. It clears the
Nifty 50 floor at *optimistic* costs (Calmar ratio 1.07) but not at base (0.94) or
pessimistic (0.81). So the result is **cost-sensitive and marginal**, not a blowout — but
the pre-committed predicate is base costs, and at base costs it fails. NO-GO stands.

---

## 2. Headline numbers

| | Strat (base) | Nifty50 TRI | Mom30 TRI (primary) | Mid50 TRI |
|---|---|---|---|---|
| CAGR | +10.74% | ~+11.55% | ~+15.2% | ~+19.3% |
| MaxDD | 37.99% | 38.27% | 33.96% | 36.39% |
| Calmar | 0.283 | 0.302 | 0.448 | 0.53 |
| Calmar ratio (strat/bench) | — | 0.94 | 0.63 | 0.53 |

Calmar-ratio matrix (strat / bench) across cost levels:

| Cost | Mom30 | Mid50 | Nifty50 |
|---|---|---|---|
| OPTIMISTIC | 0.72 | 0.60 | **1.07** |
| BASE | 0.63 | 0.53 | **0.94** |
| PESSIMISTIC | 0.54 | 0.46 | 0.81 |

Other floor diagnostics (base): Sharpe 0.71 · ann. vol 16.66% · **ann. turnover 963.6%**
· **time-in-cash 51.2%** · avg exposure 79.4% · median exposure 100.0% · 2,081 fills ·
hit rate 45.2% · 392 names traded · total cost ₹79,562.

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

**STOP at the gate.** T2–T5 are not started. No parameter was changed. The floor as
specified does not establish a foundation that clears the Nifty 50 TRI on Calmar after base
costs — exactly the outcome `04` §2's gate exists to catch.

**Diagnosis progress:**
- **§3.1 cost-model sanity — DONE (2026-06-16): NOT an artifact.** Base preset is calibrated
  (~0.57% RT, honest 2× of v1), per-trade cost is correctly ordered opt<base<pess (true cost
  ₹83k<₹175k<₹255k), and the rupee inversion is a pure book-size effect (statutory bps
  level-invariant). Not a measurement error. Reporting line relabeled (was "Total Cost Paid",
  now "Statutory Cost … (fees+DP only; slippage is in P&L)") in `metrics.summary` /
  `run_real` — verdict unaffected.
- **§3.3 universe / data integrity — DONE (2026-06-16): CONFIRMED SYSTEMIC DATA BUG.** The
  adjustment layer silently drops split/bonus back-adjustment on 556 in-window events / 406
  ISINs (CUPID 5:1 on 2026-03-09 is the worked example, held by the floor). The bug
  corrupts both the signal and P&L price series and biases held-name returns **downward** —
  the direction that could be masking a GO. **This is the §2 fix-and-re-run trigger.**
- **§3.2 regime whipsaw — NOT investigated and now moot until data is fixed:** any regime
  analysis on corrupted prices is unreliable, and a regime-parameter change is T3 tuning
  regardless.

**Revised status (supersedes the earlier "valid terminal state").** Spec 04 is **no longer
at a clean terminal STOP**. The §3.3 data bug means the NO-GO was computed on corrupted
input; per §2 the legitimate next step is **fix `prices_adjusted` (split/bonus adjustment)
and re-run the floor once on the same pre-committed config**. This is *not* tuning. It is,
however, a foundational data-pipeline remediation affecting all prior backtests, so it must
be **scoped and approved by Arafat before any code is written** (CLAUDE.md: migrations /
data pipeline are holy). T2–T5 remain unauthorized. No parameter and no data were changed by
this diagnosis.
