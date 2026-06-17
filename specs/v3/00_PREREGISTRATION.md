# v3 / 00 — Pre-Registration: Multi-Factor, Turnover-Aware Momentum

> **Status: LOCKED 2026-06-16 (§11 resolved) — Track A authorized. Build via
> `01_TRACK_A_TASKS.md`.** Pre-registration written BEFORE any v3 data or code.
> Per spec 04 §5, the design must be committed *before* measuring, so no later session
> moves the measuring stick (the v1 failure mode). Nothing here has been run. The v2
> `FINAL_OOS` block (2023-07-01 → 2026-06-12) has **never been observed** (T5 was blocked)
> and is inherited by v3 as a still-unspent one-shot OOS.
>
> **This file is a commitment, not a task list.** It fixes the hypotheses, the factor set,
> the composition rule, the bounded search grid, and the discipline. A separate
> `_TASKS.md` will decompose the build *after* Arafat locks the choices in §11.

---

## 0. Why v3 exists (what v2 measured)

v2 closed as a **research note**, not a deployable strategy (`04_VALIDATION_FLOOR_TASKS.md`).
Three findings, all measured on real, survivorship-free, real-cost data, drive v3:

| v2 finding | Evidence | v3 response |
|---|---|---|
| Edge is **name-concentrated** — dropping 10 of 3,470 names cut Calmar 0.265→0.108 | T4 §6.2 | Multi-factor → broader, smoother selection (§3.2) |
| Edge is **single-regime** — post-COVID bull Calmar +7.68 vs pre-COVID chop −0.49 | T4 §6.4 | Factor diversification reduces regime dependence (§3.2) |
| **~934% turnover is ~90% membership churn**, NOT the regime overlay (regime-off *raised* turnover) and only ~15% weight-reset | `diag_turnover_decomp.py` | Membership-aware turnover control (§3.1) |

Cost fragility (T4 §6.1) is downstream of the churn: cut realized turnover and the
pessimistic-cost margin returns. The regime overlay is **retained** — it is not the
turnover problem and it earns its keep on drawdown (regime-off maxDD 38%→48.6%).

---

## 1. Scope discipline (the v1 sins, explicitly forbidden)

v3 is **not** a license to throw factors at the wall. v1 failed on *methodology*
(thousands of configs on a biased, single reused OOS), not factor count. Adding factors
**enlarges the search space**, which makes overfitting *easier* — so the discipline is
*tighter*, not looser. Forbidden, no exceptions:

- ❌ Adding a factor without a **pre-registered economic rationale** (no "try it and see").
- ❌ Searching factor weightings on a fine grid / optimizing the blend to the backtest.
- ❌ Touching `FINAL_OOS` more than once, or moving any frozen boundary.
- ❌ Re-using v1's yfinance fundamentals (survivorship-biased, not point-in-time).
- ❌ Slicing `DISCOVERY` to exclude an inconvenient regime (the 2018–20 chop stays).

Every config evaluated is logged to the v2 `ConfigLedger`; K feeds the deflated Sharpe.

---

## 2. Hypotheses (each must justify itself before testing — 04 §4)

- **H1 (turnover).** Most of the 934% turnover is monthly membership churn around the
  rank boundary. Slowing reconstitution and/or widening the buffer cuts realized turnover
  materially **without** proportionally hurting Calmar → restores the §6.1 cost margin.
- **H2 (concentration).** A blended multi-factor score selects a broader, more stable set
  than single-factor momentum → the §6.2 top-10-drop retention rises above 70%.
- **H3 (regime).** Factors with **low cross-correlation to momentum** (value, quality)
  smooth performance across regimes → the §6.4 subperiod spread narrows (no single period
  carrying the result). *Caveat: requires fundamentals data we do not yet have (§4 Track B).*

A hypothesis that fails its pre-registered test is reported as a failure (Rule 12).

---

## 3. Design principles

### 3.1 Membership-aware turnover control (targets the 90% bucket)

The lever is **membership stability**, not weight-reset cadence (which is only ~15%).
Pre-registered levers, tested one layer at a time:

- **Reconstitution cadence** — decide *membership* quarterly or semi-annually, even if
  weights are checked monthly. (Distinct from v2's monthly membership churn.)
- **Sell buffer width M** — a held name must fall well past the buy rank before exit.
- **Rank smoothing** — rank on a smoothed score (e.g. N-month average rank) so names don't
  oscillate across the boundary on one noisy month.

### 3.2 Multi-factor composite (smoother, less concentrated signal)

Replace the single `momentum_12_1 / vol` ranker with a **rank-blended composite**: each
factor scored cross-sectionally → percentile rank → equal-weighted (or pre-committed
fixed-weight) average → one composite rank. Rank-blend (not z-score-blend) is robust to
fat tails and avoids one factor's outliers dominating.

### 3.3 Regime overlay — retained as-is

Keep the v2 regime overlay for drawdown control. It is not re-opened for turnover reasons.
Its calibration (debounce / risk-off floor) may be a *late* layer only if drawdown control
needs it, never to chase turnover.

---

## 4. Factor set — honest about what is computable today

### Track A — price/volume factors (computable NOW from the v2 data layer)

The bhavcopy data layer provides OHLCV + `adv_20` only. Computable, pre-registered:

| Factor | Definition (rationale) |
|---|---|
| Momentum (12-1) | `ret(252d skip 21d)` — trend persistence (the v2 base) |
| Momentum (6-1) | shorter-horizon trend — diversifies the lookback |
| Low volatility | inverse annualized vol — the low-vol anomaly; cushions drawdown |
| Trend quality | fraction of up-days / path smoothness — penalizes jumpy momentum |
| Short-term reversal | −1M return — fades 1-month overextension, reduces chasing |

**Honest limit:** Track A factors are mostly *momentum/trend-family* — they are
**correlated** with each other. They will smooth the signal and cut churn/concentration
*somewhat* (H1, H2), but they do **not** deliver the regime-orthogonal diversification
(H3) that value/quality provide. Track A alone is a partial fix.

### Track B — fundamental factors (GATED on new data — value & quality)

Value (earnings yield, book-to-price) and quality (ROE, low accruals, low leverage) are
the factors genuinely *uncorrelated* with momentum and the real fix for §6.4 regime
dependence. **They require a survivorship-free, point-in-time fundamentals source that
does not exist in this project.** The v1 yfinance fundamentals are biased and forbidden
(§1). Track B is therefore a **prerequisite data-layer build** (ingest + point-in-time
align + survivorship handling, to the same standard as spec 01), scoped and approved
**before** any Track B factor is pre-registered. Track B does not start until that data
passes its own acceptance checks.

**Sequencing:** build and validate **Track A first** (it tests H1/H2 with zero new data).
Only commit to Track B (and its data build) if Track A is promising but H3 remains unmet.

---

## 5. Composition rule (pre-committed)

```
composite_rank(name, day) = mean_over_active_factors( percentile_rank(factor_value) )
```

- Factors are added **one at a time** (04 §4), each on a plateau, never as a bulk blend.
- Default weighting is **equal**. Any non-equal weight must be pre-registered with a
  rationale and tested on a **coarse** grid only (§6) — no fine weight optimization.
- Entry gate unchanged from v2: `close > 200-MA AND liquidity floor` (and a momentum-positive
  gate retained while momentum is in the blend).

---

## 6. Bounded coarse grid (one layer at a time — PROPOSED, lock in §11)

Each layer holds all other knobs at the v2 floor / prior-accepted value, runs on
`DISCOVERY` only, logs to the ledger, and is accepted only on a **plateau** (04 §4).

| # | Layer | Coarse grid (proposed) | Tests |
|---|---|---|---|
| 1 | Reconstitution cadence | {monthly, quarterly, semi-annual} | H1 |
| 2 | Sell buffer M | {35, 50, 70} (N=20 fixed) | H1 |
| 3 | Rank smoothing | {none, 2-mo avg, 3-mo avg} | H1 |
| 4 | Add factor: low-vol | blend {mom} vs {mom, low-vol} | H2 |
| 5 | Add factor: trend-quality | + {trend-quality} | H2 |
| 6 | Add factor: 6-1 momentum | + {6-1 mom} | H2 |
| 7 | Add factor: short-term reversal | + {reversal} | H2 |
| (B) | Value / quality | gated on Track-B data | H3 |

No layer exceeds a handful of points. If a layer needs a large grid to find a winner, the
layer is noise and is dropped (04 §4).

---

## 7. Reuse of the v2 harness (no new infra unless a layer needs it)

v3 is a **signal + construction** change driven through the existing, test-gated machinery:

- `engine.run(...)` — unchanged daily loop, costs, regime hook, invariant checks (02 §10).
- `costs.py` — three cost levels, unchanged.
- `benchmark.py` — three TRIs + real price index, unchanged.
- `validation.py` — frozen `DISCOVERY` / `FINAL_OOS`, walk-forward, `ConfigLedger`,
  `deflated_sharpe`, `pbo_cscv`, unchanged.
- `iterate.py` — coarse-grid runner + plateau detector, reused per layer.
- `robustness.py` — the five §6 checks, reused as the candidate gate before OOS.

New v3 code is confined to: the factor library (`factors.py`), the composite ranker, and
the membership-cadence / buffer / smoothing knobs (new fields on a v3 config). The v2
`MomentumConfig` field-lock (config.py) means a v3 config is a **separate** dataclass — v2
stays runnable and frozen.

---

## 8. Frozen splits & OOS discipline

- **Reuse** v2's frozen `DISCOVERY` (2018-02-06 → 2023-06-30) and `FINAL_OOS`
  (2023-07-01 → 2026-06-12). FINAL_OOS is **pristine** (never observed) → a valid one-shot.
- All §6 iteration and robustness happen on `DISCOVERY` only.
- The chosen v3 candidate is run on `FINAL_OOS` **exactly once**. If it fails, it fails —
  no iteration against it.
- **Deflation:** v3's K counts v3's own trials (a fresh strategy family). Report raw Sharpe,
  K, and deflated Sharpe together. PBO via CSCV on the walk-forward folds.

---

## 9. Decision predicates & Definition of Done (same bar as v2 §7)

v3 is "validated, deployable" only if a **single, pre-committed** config:

- Beats Nifty200 Momentum 30 TRI on **Calmar** after **base** costs, with **max DD ≤ 70%**
  of benchmark, on `DISCOVERY`; AND
- Passes all five robustness checks (04 §6) — incl. **§6.1 pessimistic-cost** and **§6.2
  top-10-drop ≥ 70% retention**, the two v2 failed; AND
- Passes the **one-shot `FINAL_OOS`** without re-tuning; AND
- Is tradeable on turnover/capacity (realized turnover, not just planned).

Anything less is a research note (Rule 12). No softening.

---

## 10. Realistic expectation (Rule 12, no overselling)

- **Track A alone** is unlikely to fully fix §6.4 regime concentration — its factors are
  momentum-correlated. It can plausibly fix H1 (turnover) and partially H2 (concentration).
- **The real regime fix (H3) needs Track B fundamentals**, which is a genuine data build.
- It is a legitimate outcome that v3 **also** ends as a research note. The point is honest
  measurement, not a guaranteed deployable strategy.

---

## 11. Locked commitments (Arafat, 2026-06-16)

1. **Track A first.** Build and validate the price/volume multi-factor (§4 Track A) with
   zero new data. Commit to Track B (fundamentals data build) **only** if Track A is
   promising but H3 (regime diversification) remains unmet. Track B is not started now.
2. **§6 layer order and coarse grids accepted** as proposed.
3. **Composite weighting: equal-weight rank-blend** (§5). Any non-equal weight needs a
   separate pre-registration; not in Track A scope.
4. **Reuse v2 frozen splits as-is** — `DISCOVERY` / `FINAL_OOS` unchanged; FINAL_OOS pristine.
5. **Same §9 Definition-of-Done bar** — not lowered.

Build proceeds via `01_TRACK_A_TASKS.md` (T0…T7). No data is touched and no code beyond
the locked scaffolding is written until each task's own gate is met.

---

## Locked decisions (T0) — 2026-06-17

**Code:** `backend/app/backtest_v2/v3_config.py`

| Decision | Value | Source |
|---|---|---|
| Config type | `V3Config` dataclass, separate from `MomentumConfig` | §7, §11 |
| v3 floor | `active_factors=["mom_12_1"]`, `rebalance_cadence="monthly"`, `sell_rank_buffer=35` | §11 item 1 |
| Composite weighting | Equal-weight rank-blend (`factor_weights=None`) | §5, §11 item 3 |
| Layer 1 cadence grid | `["monthly", "quarterly", "semi-annual"]` | §6 |
| Layer 2 buffer-M grid | `[35, 50, 70]` (N=20 fixed) | §6 |
| Layer 3 smoothing grid | `[0, 2, 3]` months | §6 |
| Factor layers (4–7) | `["low_vol", "trend_quality", "mom_6_1", "reversal"]` | §6 |
| DISCOVERY split | Imported from `validation.py` — `(2018-02-06, 2023-06-30)` | §8, §11 item 4 |
| FINAL_OOS split | Imported from `validation.py` — `(2023-07-01, 2026-06-12)` | §8, §11 item 4 |
| §6.4 concentration predicate | Hard FAIL if any positive subperiod > 5× mean of other positives | §6, T6 note |
| DoD predicates | Frozen as functions in `v3_config.py` | §9 |

Nothing above may be changed without a new pre-registration entry and explicit session approval.

---

## Erratum (T1 → T2) — parity baseline correction — 2026-06-17

**Approved by Arafat, 2026-06-17.** A new pre-registration entry per the T0 lock rule above.
This is an **erratum, not a re-tuning**: it repairs an internal contradiction surfaced during
T1, *before any measurement*, and **loosens no §9 Definition-of-Done bar**.

### The contradiction

- §4 + the T0 lock define the v3 floor as `active_factors=["mom_12_1"]`, and §4 defines
  `mom_12_1` as the **raw** 12-1 return `ret(252d skip 21d)`.
- But T2's done-criterion and T4's parity check (in `01_TRACK_A_TASKS.md`) ask that same floor
  to "reproduce v2's ranking order / base numbers (Calmar ~0.265, turnover ~934%)" — numbers
  produced by v2's **volatility-adjusted** ranker `momentum_12_1 / annualized_vol`
  (`signals.py:137`).

These cannot both hold. A raw-momentum floor will **not** reproduce a vol-adjusted candidate's
exact ordering or Calmar. The parity criterion was written on the unstated assumption that
*floor == v2 candidate*; §4 makes that false. The defect is the over-specified parity
criterion, not the factor library.

### Why the floor stays raw (this divergence is by design)

§3.2 commits v3 to **"replace the single `momentum_12_1 / vol` ranker with a rank-blended
composite"** — i.e. v3 *deliberately decomposes* the ratio into separable rank-blended
factors (`mom` and `low_vol` as distinct §4 factors). So the raw-momentum floor differing
from v2's vol-adjusted candidate is the **v3 thesis**, not a bug. Layer 4 (`+low_vol`, §6) is
precisely where vol information re-enters — the v3 way. Two rejected "fixes" and why:

- ❌ **Add `low_vol` to the floor.** Violates the T0/§11 lock; pre-spends Layer 4 (destroys
  the clean one-layer-at-a-time test §6 exists to protect); and an equal-weight rank-blend of
  `{mom, low_vol}` is a *different transform* from the ratio `mom/vol` — it would break the
  lock and still miss parity.
- ❌ **Redefine `mom_12_1` as `mom/vol`.** Moves the §4 measuring stick after T1 was built and
  tested against the raw definition — the v1 sin (§1) — and contradicts §3.2.

### The correction (binding on T2 and T4)

The parity check is a **wiring-correctness** check, not a historical-number-matching check.
Because the v2 ranker is explicitly pluggable (`signals.py:126` — "swapping the ranker is a
one-line change… pass a different callable with the same `(day, isin) → float` signature"):

1. **Exact parity target = a raw-momentum v2 reference.** Drive the *unchanged* v2 engine with
   a ranker returning raw `momentum_12_1` (not `mom/vol`). Assert the v3 momentum-only floor
   matches **that** reference to numerical tolerance. This isolates plumbing correctness
   instead of confounding it with a deliberate signal-definition difference. Log the reference
   run to the `ConfigLedger`.
2. **The historical `Calmar ~0.265 / turnover ~934%` are demoted to a sanity band only** — same
   order of magnitude, turnover still ~900% — explicitly **not** an equality target, because
   they belong to the vol-adjusted signal, not the raw-momentum floor.
3. **Recorded expectation (Rule 12).** v3 `{mom, low_vol}` at Layer 4 should recover v2's
   character, since that is where vol-adjustment legitimately re-enters. If it does not, that
   is itself a finding to report, not to engineer around.

No §9 DoD predicate, no frozen split, and no factor definition is changed by this erratum.

---

## Pre-registration entry — Track-B `DISCOVERY_START` rescope — 2026-06-17

**Approved by Arafat, 2026-06-17.** A new pre-registration entry per the T0 lock rule above.
It amends **§11 item 4** ("Reuse v2 frozen splits as-is — DISCOVERY unchanged") **for Track B
only.** Track A is closed and was evaluated on the full `2018-02-06 → 2023-06-30` DISCOVERY;
this entry does **not** retroactively alter Track A's record or `validation.py`'s canonical v2
split. **`FINAL_OOS` (2023-07-01 → 2026-06-12) is unchanged and stays pristine.**

### Why (a data-feasibility constraint, not a performance tune)

The TB0.5 probe chain (`02_TRACK_B_TASKS.md`) established that the early-DISCOVERY self-ingest
XBRL window cannot clear the **§6.1 75%-by-name floor**: 2018 is a structural XBRL desert
(~5% — FY2017 results XBRL was never published), and 2019 sits at 55–65%. The Step-1 hole-fill
re-probe showed NSE-only standard-tag coverage **crosses 75% between Nov-2019 and Jun-2020**
(2020-06=100%, 2020-12=80%, 2021-03=90% on seeded 20-name samples). So the **frozen 2018-start
DISCOVERY makes the §6 gate unreachable** — TB7 requires ≥75% at *every* monthly rebalance.
This is a property of the data, not of any threshold.

### The change

1. **Track-B DISCOVERY is rescoped to start ≈ 2020.** The exact start = the earliest monthly
   rebalance with **durable ≥75% by-name coverage over the full liquidity-eligible panel**,
   pinned at **TB7** (over the whole panel, *not* 20-name probe samples, and *never* by moving
   §6). Until TB7 pins it, "≈2020" is the committed scope; no precise constant is frozen early
   (avoids false precision — the v1 sin).
2. **Source = NSE-only self-ingest. BSE fallback is NOT built.** It is off the critical path: it
   could only attempt to rescue 2019 (one extra 2018-19 NBFC-crisis year) and cannot touch 2018.
   §8.1 keeps BSE as a *sanctioned remedy* only if a specific BSE-only gap later breaks the floor
   — more input against an unchanged threshold, never HARKing.

### What is explicitly NOT changed (the guards)

- **§6 thresholds unchanged** — 90%-by-weight AND 75%-by-name dual gate intact. This moves the
  *window*, not the *measuring stick*. Manufacturing the early window by loosening §6 is forbidden.
- **`FINAL_OOS` unchanged and pristine** (post-2023 coverage ~95%, feasible regardless).
- **No §9 DoD predicate lowered.** Walk-forward machinery (`walk_forward_windows`,
  `min_is_months=24`+`oos_months=6`) unchanged — the ≈2020 start still yields **2–3 expanding
  folds** (the dominated ~2021 alternative would have given 0–1).

### Cost acknowledged (Rule 12, no overselling)

DISCOVERY shortens from ~5.4 yr to ~3.5 yr, losing the 2018 mid-cap crash and the 2018-19 NBFC
crisis from the in-sample window. It **retains the Mar-2020 COVID crash** — the largest regime
contrast in the panel and exactly the diversification H3 is built to test. A shorter window that
still spans a genuine crash is the honest maximum the data supports; the alternative (a clean
but regime-thin ~2021 start, or a speculative BSE build for one extra year) was rejected.
