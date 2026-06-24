# V4.1 Trade-Level Forensic — Findings Memo

**Status:** DIAGNOSTIC (findings only — NOT a candidate, NOT a grid change)
**Date:** 2026-06-24
**Window:** DISCOVERY 2018-02-06 → 2023-06-30
**Discipline:** Adds **0 to K** · v4-FINAL_OOS **untouched** · no threshold changed · no grid level added · re-runs the locked T1/T2/T3 only (`00` §1/§6).
**Runner:** `backend/app/swing_v4/v41_forensic.py` · raw output `backend/reports/v41_forensic.txt` (gitignored).

---

## 0. Why this memo exists

The V4.1 cost screen (`438d9a1c`) closed NULL: 0/3 configs cleared §6.1, and every
base-cost Calmar (≤0.145) already trailed Nifty 50 TRI (0.346) **before** costs. The
screen reported portfolio-level aggregates only. This forensic re-runs the same three
configs and dumps the **per-round-trip** and **per-exit-type** statistics the screen
aggregated away, to answer one question descriptively: *what is the mechanism of the
failure — a broken edge, a cost problem, or a deployment problem?*

This is the `00` §6 species of work (read-only diagnostic). It does **not** select a
candidate, relax a rule, or extend the grid. Any structural hypothesis it surfaces
requires a **separate** pre-registration frozen before a new return number — never a
swap into the closed V4.1 (`00` §1).

---

## 1. Headline reconstruction

| Cfg | Exit rule | Calmar | CAGR | maxDD | Turnover | Fills | Round-trips |
|----|-----------|-------:|-----:|------:|---------:|------:|------------:|
| **T3** (candidate) | ATR 3× trail | **0.083** | 2.85% | 34.4% | 828% | 783 | 384 closed +15 open |
| **T1** | MACD cross-down | **−0.070** | −2.12% | 30.1% | 2660% | 2576 | 1281 closed +14 open |
| **T2** | close < EMA50 | **0.145** | 3.97% | 27.4% | 1061% | 1038 | 512 closed +14 open |

Benchmark: Nifty 50 TRI Calmar **0.346** over the same window (from the screen).

**The binding constraint is CAGR, not drawdown.** maxDD (27–34%) is unremarkable for a
trend system; CAGR (−2% to +4%) is what sinks Calmar. So the forensic question becomes:
*why is CAGR so low when the trade geometry (below) is healthy?*

---

## 2. The edge is real but THIN (not broken)

Per-round-trip, net of cost:

| Cfg | Win rate | Avg win | Avg loss | Payoff | Expectancy/trade (net) |
|----|---------:|--------:|---------:|-------:|-----------------------:|
| T3 | 34.1% | +16.64% | −7.53% | 2.21 | **+0.72%** |
| T1 | 32.1% | +7.33% | −3.54% | 2.07 | **−0.06%** |
| T2 | 27.9% | +16.53% | −5.65% | 2.93 | **+0.55%** |

This is the **textbook trend-following signature**: low win rate, payoff ratio > 2 (cut
losers fast, let winners run). T3 and T2 have **genuinely positive** per-trade
expectancy. The signal is *not* a coin flip and *not* negative — it has a real,
positive, but **small** edge per trade. That is an important, somewhat encouraging
negative result: the failure is one of *magnitude and friction*, not of a broken thesis.

---

## 3. The three leaks that crush CAGR

### Leak A — the per-trade edge is barely above the cost-per-turn

Σ over closed round-trips (of ₹3.5L starting capital, **total over the 5.4-yr window**,
not annualized):

| Cfg | Gross P&L | Costs | Net P&L | Costs as % of gross |
|----|----------:|------:|--------:|--------------------:|
| T3 | +₹40,136 (+11.5%) | ₹24,440 (7.0%) | **+₹16,083 (+4.6%)** | **61%** |
| T1 | +₹24,901 (+7.1%) | ₹69,045 (19.7%) | **−₹43,813 (−12.5%)** | **277%** |
| T2 | +₹45,539 (+13.0%) | ₹30,546 (8.7%) | **+₹15,395 (+4.4%)** | **67%** |

Even the candidate's *gross* (frictionless-ish) trading P&L is only **+11.5% over 5.4
years** (~2%/yr). Costs then eat 61% of it, leaving ~0.8%/yr net trading P&L. This is
why §6.1 fails even at base cost: the edge is too thin for the friction it pays. **Cost
is a real amplifier but a secondary one — for T3/T2 the edge is thin *before* cost; only
T1 is a pure cost casualty.**

### Leak B — turnover is set by the EXIT RULE, and it is the cost multiplier

| Cfg | Median hold | p25 / p75 | % of trades held ≤10 days | Turnover |
|----|------------:|-----------|--------------------------:|---------:|
| T3 (ATR trail) | 42 d | 25 / 72 | **3.9%** | 828% |
| T1 (MACD cross) | 11 d | 5 / 19 | **48.6%** | 2660% |
| T2 (EMA50) | 28 d | 12 / 58 | 23.4% | 1061% |

The exit rule *is* the turnover knob. **MACD cross-down whipsaws** — nearly half its
trades are closed within 10 calendar days, tripling fills (2576) and cost (19.7%) and
turning a +7.1% gross into a −12.5% net. The ATR trail is the lowest-churn exit and the
reason T3 is the least cost-bled of the three. (This is consistent with the §6.1 ranking
but now mechanistically explained: T1's failure is turnover-driven; T3/T2's is
edge-magnitude-driven.)

### Leak C — the regime overlay halves deployment, and capital sits idle

Deployable fraction `f` over DISCOVERY (signal-independent, identical across configs):

```
f = 0.0 : 11.1% of days     f = 0.5 : 53.8% of days     f = 1.0 : 35.1% of days
mean f = 0.62
```

Realized average exposure: T3 **70.1%**, T2 68.2%, T1 49.3% — and **time-in-cash =
100%** (the book is *never* fully invested on any single day, owing to the
`target_positions=15` cap + whole-share rounding + the `f` throttle stacking). The
regime overlay alone holds mean deployment near 62%; combined with the cap it means a
large, persistent cash drag. A thin gross edge applied to ~62% of capital produces the
~3% CAGR we see. **The overlay is doing its risk job (maxDD is contained), but it is also
the single largest CAGR suppressor** — a classic risk/return tension, not a bug.

---

## 4. Honest disclosure (Rule 12)

- The exit-reason table reports `still_open` round-trips at **avg net ret −100.12%**.
  This is a **reconstruction artifact, not a real loss**: open positions have no sell
  fill, so the round-trip reconstructor sees `sell_notional = 0`. Their *unrealized*
  value **is** correctly carried in the equity curve (and therefore in the headline
  Calmar/CAGR via MTM); the −100% appears only in the standalone round-trip table and is
  excluded from the §3 Leak-A gross/net sums (those are over closed trades only). ~14–15
  names per config are simply open at the window edge.
- All numbers are base cost (the most favorable tier) — the friction story is
  *conservative*; pessimistic cost (the §6.1 gate) is strictly worse.
- The INE093A01033 / INE736A01011 "no close_tr — carrying last" MTM warnings in the raw
  log are a known stale-price data gap for two names, carried forward at last price; they
  do not affect the entry/exit logic and are filtered from the saved report.

---

## 5. What this licenses — and what would be HARKing

**Mechanism, stated plainly:** the V4.1 swing edge is *real, positive, and too small to
survive the friction + de-deployment it operates under.* Ranked by leverage:

1. **Selection (highest leverage).** The thin edge is per-*name*. The locked engine
   selects entrants by `adv_20` (liquidity), and the V4.1 §6 diagnostic already found
   that selector **edge-discarding** (random-15 and uncapped both beat it). Picking names
   by something return-informed attacks the edge *at its source* (Leak A) rather than
   nibbling at friction.
2. **Exit/turnover.** The ATR trail already minimizes churn; tightening it further is a
   second-order cost saving and cannot close a ~4× Calmar gap on its own (T3 is thin
   *pre*-cost).
3. **Regime deployment.** Loosening the overlay would lift CAGR but also lift maxDD — a
   returns-for-risk trade, ambiguous, and it touches a deliberate risk control.

**The non-HARKing path:** a structural hypothesis motivated by mechanism (1) — a
**return-informed selector** — is exactly what `00` §6 pre-authorized as "a SEPARATE
future amendment with its own K." That is legitimate science: it is not the knob-value
that would have made T3 pass on this data; it is a different mechanism with an
independent reason to exist, and it must be frozen (grid + acceptance rules) **before**
any new return number is read.

**What would be HARKing (and is therefore forbidden here):**
- Re-running T1/T2/T3 with a lowered §6.1 bar, a different benchmark, or a sub-window
  chosen because it looks better, then calling it a pass.
- Tuning `target_positions`, `atr_mult`, or the regime thresholds to the values this
  forensic suggests would have cleared the gate, and presenting that as a fresh result.
- Touching v4-FINAL_OOS on the basis of this DISCOVERY analysis.

Any of the three levers becomes legitimate **only** inside a new, signed pre-registration
with its own K budget and (given three prior programs hit the "buy-the-index" wall) an
explicit, honest prior that the most-likely outcome is still NULL.

---

## 6. Bottom line

V4.1 did not fail because the swing thesis is wrong. It failed because the per-trade edge
(+0.72% net for the candidate) is **too thin** to overcome (A) transaction cost that eats
~60% of gross, (B) turnover set by the exit rule, and (C) a regime overlay that keeps the
book ~62% deployed. The trade geometry (payoff > 2, disciplined losers) is sound. The one
mechanism with the leverage to matter is **name selection**, which independently
corroborates the already-pre-authorized §6 edge-discarding finding. **No candidate is
advanced, no grid changed, K unchanged, FINAL_OOS pristine.**
