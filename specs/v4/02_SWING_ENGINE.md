# v4 / 02 — Daily Swing Engine: build, fidelity, no-lookahead + returns-blind N_max lock

> **Status: LOCKED — 2026-06-24 (Arafat). §11 signed (all 8 commitments).** No engine code existed before
> this lock; the next move is V4.0a (indicators + regime + signals). No engine code exists yet
> (`backend/app/swing_v4/` confirmed absent). This is the **implementation spec** for the daily
> event-driven swing engine whose *strategy* was frozen in `00_SWING_PREREG.md` (LOCKED 2026-06-23).
> It builds the plumbing under the prereg's frozen rules; it does **not** re-decide a single strategy
> parameter. It corresponds to prereg **stage V4.0** and ends with two deliverables: (a) a fidelity-
> and no-lookahead-tested engine, and (b) the **returns-blind `N_max` lock** — with **no DISCOVERY/OOS
> return backtest** in this stage (that is V4.1+).
>
> **Owner:** Arafat. **Created:** 2026-06-23. **Depends on:** `00_SWING_PREREG.md` (LOCKED — strategy,
> regime score, grid, acceptance, OOS protocol all frozen) and `01_REGIME_DATA_LAYER.md` (COMPLETE —
> `market_internals` liquid breadth/AD + India VIX landed).
>
> **What this doc is NOT:** it is not a strategy decision. Every entry/exit rule, indicator parameter,
> regime weight/cut/bucket, benchmark, cost level, and acceptance threshold is **inherited frozen** from
> `00`. If this doc and `00` ever appear to disagree, `00` wins and this doc is the bug (§0). This doc
> also does **not** run any return number — V4.0 is build + unit-test + a returns-blind count.

---

## 0. Inheritance & scope discipline (binding)

This spec is **downstream of a locked prereg**. The following are inherited verbatim and are **not**
re-opened here (citations are to `00_SWING_PREREG.md`):

| Frozen by `00` | Value | `00` ref |
|---|---|---|
| Universe | v2 liquid bhavcopy, `instrument_id`-stitched, `adv_20 ≥ ₹5cr` | §3.1 |
| Indicators | MACD(12,26,9) daily + weekly, SMA20/50/200, EMA50, ATR20(Wilder), all on **adjusted** series | §3.2 |
| Entry | 4 conditions, all true on D close → BUY D+1 open | §3.3 |
| Exit (candidate) | Type 3 ATR `3×` trailing on **close** anchor; Type 1/2 are comparators only | §3.4 |
| Catastrophic floor | `−25%`-from-cost-basis close-breach circuit breaker beneath Type 3 | §3.4 |
| Sizing | equal-weight, whole-share, gross ≤ `f×capital`, buys clamped to cash | §3.5 |
| `N_max` | **procedure-locked returns-blind at ≈p99 of concurrent holdings** (this doc executes it) | §3.5 |
| Oversubscription tiebreak | rank by `adv_20` (most liquid first) — neutral, non-return | §3.5 |
| Regime downgrade | **no forced liquidation** — throttle blocks/limits new deployment only | §3.5 |
| Regime score | 5-condition 0–5; buckets `0–1/2–3/4–5 → 0%/50%/100%`; **liquid** breadth/AD; missing-VIX→cond5=0 | §4 |
| Benchmark | primary = **Nifty 50 TRI** (Calmar-beat + maxDD ≤ 100%); Nifty200 Mom30 reported as reference | §2 |
| Cost levels | base + pessimistic via the v2 `costs.py` model | §5/§6.1 |
| Fill discipline | signal on close D → fill D+1 open; no intrabar ordering | §9 |

- **No parameter chosen by backtest.** This engine emits *no return number*. Anything that would tune a
  parameter against a return belongs to V4.1+ and is bounded by the `00` §5 grid — never invented here.
- **Additive only.** New package `backend/app/swing_v4/`. It **reads** the bhavcopy adjusted store,
  `market_internals`, India VIX, and the Nifty 50 index series; it **writes nothing** into the data layer
  and imports the v2 `costs.py` / accounting primitives **without modifying them** (§8). It cannot move an
  S3/`11` or `FINAL_OOS` number.

---

## 1. Architecture — mirror the v2 context/state/step_day split (fidelity by construction)

The v2 engine (`backend/app/backtest_v2/engine.py`) already proved the pattern that lets a **single
per-day core** drive both the historical backtest and a future live paper shell byte-for-byte (the `11`
probation). v4 reuses that shape so its eventual forward probation (a future `11`-style spec) is faithful
by construction, not by re-implementation:

```
backend/app/swing_v4/
  __init__.py
  config.py        # SwingConfig (frozen 00 params as defaults; exit_type/atr_mult/n_max/regime_tier knobs)
  indicators.py    # MACD, weekly-MACD, SMA, EMA, ATR(Wilder) — pure, vectorized, adjusted-series only
  signals.py       # SwingSignalStore: precompute per-ISIN entry/exit primitives once (like v2 SignalStore)
  regime.py        # RegimeScore: 0–5 daily score from market_internals + Nifty50 price → f ∈ {0,0.5,1.0}
  engine.py        # build_context() / SwingLoopState / step_day() / run()  — the event-driven core
  footprint.py     # V4.0 returns-blind N_max measurement (NO sizing, NO throttle, NO PnL)
```

- **`build_context()` → `SwingEngineContext`** (immutable per-run lookups + collaborators): the adjusted
  price pivots (`close`, `open`, `adv_20`), the precomputed `SwingSignalStore`, the `RegimeScore`
  collaborator, the resolved `CostConfig`, `whole_shares` flag, and the trading calendar. Built once.
- **`SwingLoopState`** (mutable, carried across days — and **persistable** the way v2's `LoopState` is, so
  a future live shell can hydrate it): `portfolio`, `pending_fills`, and the **per-name open-position
  state** (`dict[instrument_id → SwingPosition]` holding entry date, cost basis, and the **trail anchor =
  max adjusted close since entry**).
- **`step_day(ctx, state, day)`** is the one shared per-day core. `run()` = `build_context()` + a loop of
  `step_day` over the calendar. The future live shell will call the **same** `step_day`.
- **Reuse, do not fork, the v2 fill plumbing & accounting.** Import and reuse the v2 `costs.py` model
  (`CostConfig.{base,pessimistic}`, `fill_cost`, `effective_price`) and the v2 `Portfolio`/`Fill`
  primitives **iff** they are strategy-agnostic (they account cash/positions/MTM/cost generically; V4.0
  verifies and reuses them rather than copying). The slippage-on-effective-price and clamp-to-cash
  mechanics (`_stamp_fills` / `_clamp_buys_to_cash` equivalents) are **shared, not re-derived** — divergence
  here is exactly the v1-class fidelity bug we refuse to reintroduce. *(§11-decision RESOLVED — Arafat:
  **reuse, never edit** the v2 classes. If a v2 primitive carries a rebalance-specific assumption that does
  not fit an event-driven book, **compose/wrap around it or surface the incompatibility** — never edit the
  v2 class and never silently fork.)*

> **Plain-language note (Rule 13):** the v2 engine is a *monthly* `for name in top-N` snapshot; v4 is a
> *daily* `while (trend intact)` loop **per name**. So v4 can't be a config of the v2 loop — it needs its
> own `step_day`. But the parts that decide *how a queued order becomes cash and shares* (next-open fill,
> slippage, whole-share rounding, never-spend-cash-you-don't-have) are strategy-agnostic plumbing, and we
> reuse the v2 versions so the two engines fill orders identically.

### 1.1 `step_day` ordering (the hard invariant — mirrors v2 §3 / `11` §3e)

For trading day `D`, in this exact order:

1. **Apply prior-session queued fills at today's open.** Sells/trims before buys (exits replenish cash
   before new buys). Stamp next-open price → apply slippage via `effective_price` → `_clamp_buys_to_cash`
   (whole-share aware) → `portfolio.apply_fills`. A name bought at today's open gets its cost basis set
   **now**, so it is exit-eligible on **today's** close (no skipped first-day stop).
2. **MTM** the book at today's adjusted close.
3. **Update each open position's trail anchor** = `max(anchor, adjusted_close[D])`.
4. **Exit checks (per open name, on D close → queue SELL D+1 open):** catastrophic floor first
   (`adjusted_close[D] < cost_basis × 0.75`), then the configured exit (Type 3: `adjusted_close[D] <
   anchor − atr_mult × ATR20[D]`; or Type 1/2 if that config). No forced liquidation on regime change.
5. **Compute the regime score for D** → bucket → deployable fraction `f`.
6. **Entry scan (D close → queue BUY D+1 open):** while `open_positions < N_max` **and** projected
   `gross < f × capital`, take names whose 4 entry conditions are all true on D and that are eligible
   (`adv_20 ≥ ₹5cr`, traded D, not already held). When signals exceed free slots, rank by `adv_20` desc
   (frozen tiebreak). Per-name target notional = `f × capital / N_max`, equal-weight.
7. **Snapshot** the day (NAV, cash, positions, per-name anchors) for later metrics.

> **Deployment fidelity — close-based exit is GTT-free deployable (verified 2026-06-23, Arafat's Q).** The
> frozen close→next-open model needs **no intraday GTT and no `00` §13 deviation**: Zerodha accepts **market
> AMOs for equity** (window ~4:00 PM–8:58 AM NSE) that fire into the **9:00 AM pre-open auction and fill at
> the opening price**. So the EOD pipeline (19:30 IST) places a plain **market AMO** on a breach → it fills
> at the next-open auction price == the backtest's "open" ⇒ backtest == deployment. (Zerodha disallows the
> stop-loss *order type* as an AMO, but we don't rest a broker stop — we detect the ATR/floor breach in the
> pipeline and place a market order, so that restriction does not apply.) Intraday-GTT remains the explicit
> *alternative* requiring a signed `00` deviation; it was **not** taken.

---

## 2. Indicator layer (`indicators.py`) — textbook-frozen, parity-tested

Pure vectorized functions on the **split/bonus-adjusted** series only (never `close_raw`). Parameters are
the `00` §3.2 constants, passed in (not hardcoded) so tests can exercise tiny fixtures, but **defaulted to
the frozen values** in `SwingConfig`.

| Function | Definition | Lookahead guard |
|---|---|---|
| `macd(close, 12,26,9)` | EMA12−EMA26; signal = EMA9 of MACD line | trailing EMA only |
| `weekly_macd(close)` | resample **W-FRI**, **completed weeks only**, then MACD(12,26,9) | in-progress week excluded until it closes |
| `sma(close, n)` | rolling mean, `min_periods = n` | no partial-window value |
| `ema(close, n)` | `ewm(span=n, adjust=False)` | trailing only |
| `atr20(high, low, close)` | **Wilder** ATR over 20, on adjusted O/H/L/C | trailing only |

- **Weekly→daily alignment:** each daily row D carries the **last completed** weekly MACD as of D. A week
  becomes visible only on/after its Friday close (or the last trading day of that week). This is the §9
  "completed weeks only" guard and gets its own no-lookahead test (§5).
- **ATR is computed on adjusted O/H/L/C** so a corporate action cannot inflate the trail (`01`/`05`
  adjustment discipline). The trail anchor is the adjusted **close**, never the intraday high (§9 — the v1
  trailing-stop-uses-same-bar-high bug is explicitly excluded).

---

## 3. Regime score (`regime.py`) — consumes `01`, causal, frozen at `00` §4

`RegimeScore` is a collaborator built once over the run window. For each day D it returns an integer score
`0–5` and the deployable fraction `f`:

| # | Condition (+1 each) | Source |
|---|---|---|
| 1 | Nifty 50 close > its 200-DMA | Nifty 50 **price** series (`benchmark` Nifty-50-price loader) |
| 2 | Nifty 50 50-DMA > 200-DMA | same |
| 3 | `liq_breadth_pct` > 60 | `store.read_market_internals` |
| 4 | `liq_ad_ratio` > 1 | same |
| 5 | `india_vix` < 20 | `store.read_india_vix` / merged `market_internals.india_vix` |

- **Buckets (frozen):** `0–1 → f=0.0` (Bear); `2–3 → f=0.5` (Neutral); `4–5 → f=1.0` (Bull).
- **Liquid series locked (`00` §4):** conditions 3 & 4 read `liq_breadth_pct` / `liq_ad_ratio` — the
  ~562-name liquid subset matching v4's hunting ground, **not** the all-EQ series.
- **Missing-VIX day (the 18 surfaced-not-filled days, `01`):** condition 5 scores **0** (score capped at 4,
  biases toward *less* deployment). No forward-fill, no rescale, no degrade-to-3-factor.
- **Causality (§9):** DMAs use trailing windows with `min_periods = window`; day D uses only completed-day
  D values; trades fire D+1 open. No intraday/in-progress value ever enters.
- **3-factor ablation:** `RegimeScore` exposes a 3-factor variant (conditions 1–3, rescaled
  `0=Bear / 1–2=Neutral / 3=Bull`) used **only as a reported ablation** in V4.2 — it is not a separate
  selection trial (running it as a candidate would be K+1; `00` §4).
- **Nifty 50 price source:** the `benchmark` module already exposes a Nifty-50-price loader (cache-then-
  fetch). **Open operational note:** if the Nifty 50 price/TRI cache misses, V4.0 does a **one-off live
  fetch** (already-sanctioned, same exemption `01` Part B used; **no live API in pytest** — tests inject a
  fixture series). This is the only external dependency V4.0 may touch.

---

## 4. The returns-blind `N_max` lock (`footprint.py`) — V4.0's one novel mechanism

`00` §3.5 deliberately makes `N_max` a **returns-blind** procedure, not a picked number, to resolve the
"the cap must lock before the run, but we mustn't tune it" tension. This is the only place V4.0 produces a
number, and it is **a count, never a return**.

**Procedure (executed in V4.0, before any PnL exists):**
1. Run the **frozen entry rule + Type-3 exit** as a pure state machine over **DISCOVERY**
   (`2018-02-06 → 2023-06-30`).
2. Run it **unconstrained**: **no `N_max` cap, no regime throttle, no sizing, no costs, no PnL.** Every
   name whose 4 entry conditions fire is treated as "held" until its own Type-3 exit fires. *(§11-decision:
   throttle-excluded is the literal `00` §3.5 reading — "entry rule + Type-3 exit". Excluding the throttle
   yields a **conservative upper-bound** crowding distribution, so the resulting cap is a genuine
   *tail-risk control that rarely binds*, not a performance lever. Recommended; recorded explicitly.)*
3. Record **only** the time series of **concurrent open holdings** (and fresh entry signals/day) — never
   any P&L. Report the full distribution: **max / p95 / p99**.
4. **Lock `N_max` at ≈ the 99th percentile** of concurrent holdings, rounded to an integer. Record the
   number **and** the full distribution **before** V4.1 begins.
5. The `00` §5 grid later tests `N_max ± 2` (a §6.3 plateau axis) to confirm the cap is non-binding — that
   confirmation happens in V4.2, not here.

This is **signal-footprint characterization** — the same category as measuring universe size or turnover
structure — and is pre-registration-safe precisely because it touches no return (`00` §3.5).

> **K impact: zero (Arafat-confirmed).** K counts *return-evaluated* selection trials (the false-discovery
> risk is "tried N configs, kept the best return"). The footprint evaluates **no return**, so it does **not**
> increment the v4 ledger. The `00` §5 `N_max ± 2` neighbors *are* return-evaluated in V4.2 (the §6.3
> plateau check) and **do** count toward K there — the lock is free, the stress-test is not.

---

## 5. Fidelity & no-lookahead test battery (the V4.0 "done" bar — Rule 9: encode WHY)

No live API in any test (CLAUDE.md §5); every external series is a fixture. Each test states the failure it
guards:

1. **Indicator parity:** MACD / weekly-MACD / SMA / EMA / ATR(Wilder) on a tiny hand-computed fixture match
   hand-figures to tolerance. *Guards: a silent indicator-definition drift.*
2. **Entry-rule fixture:** a fixture where all 4 conditions become simultaneously true on a known day D
   produces exactly one entry queued for D+1 open, and a fixture missing any one condition produces none.
   *Guards: an AND collapsing to OR, or an off-by-one on the MACD-crossover `D−1 ≤ signal` test.*
3. **Type-3 exit fixture:** a fixture that ratchets the anchor up then breaches `anchor − 3×ATR` on close D
   queues a SELL for D+1 open; the anchor never moves down. *Guards: the trail anchoring on the intraday
   high (the v1 sin) or moving down.*
4. **Catastrophic-floor fixture:** a `−25%` close breach exits even when the Type-3 trail has not yet
   tightened. *Guards: a gap-down slipping past the floor.*
5. **No-lookahead (future-bar corruption) — the headline guard:** compute all signals/exits for day D, then
   **corrupt every bar after D** (NaN/garbage), recompute, and assert **every day-≤D signal, exit, anchor,
   and regime score is byte-identical.** *Guards: any forward leak in indicators, weekly resample, ATR, or
   the regime DMAs — the v1-class data-layer lookahead.*
6. **Completed-weeks-only:** the in-progress (un-closed) week's bars must not change the weekly-MACD value
   carried on any day inside that week. *Guards: a partial-week MACD leaking the future.*
7. **Regime causality + missing-VIX:** a missing-VIX day scores condition 5 = 0 (not forward-filled);
   regime DMAs respect `min_periods`. *Guards: silent VIX fill (`00` §4) and partial-window DMA leaks.*
8. **Whole-share + clamp-to-cash:** buys floor to integer shares and never drive cash negative; the
   `equity == cash + Σ shares·price` identity holds every day. *Guards: fractional-share fidelity drift and
   the implicit-leverage bug fixed in S3 `11` §13.*
9. **Fill-discipline parity:** a name bought at D+1 open has its cost basis set at apply-time and is
   exit-eligible on D+1 close (the v2/`11` §3e hard ordering invariant). *Guards: a skipped first-day stop.*
10. **Identity continuity:** an `instrument_id` succession across an open position does not look like an
    exit + re-entry, nor strand a position in a ghost ISIN (`06`/`07`). *Guards: the `11` ghost-holding
    defect class.*

---

## 6. Definition of Done (V4.0 only — no return number)

- [ ] `backend/app/swing_v4/` package built: `config`, `indicators`, `signals`, `regime`, `engine`
      (`build_context`/`SwingLoopState`/`step_day`/`run`), `footprint`.
- [ ] v2 `costs.py` reused verbatim; v2 `Portfolio`/`Fill` reused or a documented thin equivalent (§1).
- [ ] Full test battery §5 (1–10) green; **no live API in pytest**; the existing backtest_v2 / paper_v2 /
      data-layer suites stay green (additive-only proof, §8).
- [ ] **`N_max` locked from the returns-blind count distribution** (§4): integer + max/p95/p99 recorded in
      this doc's Session log **before** V4.1.
- [ ] **No DISCOVERY/OOS *return* backtest in V4.0** (build + unit-test + count-only footprint). FINAL_OOS
      untouched (it cannot be touched until a §6-locked candidate exists, `00` §8).

Anything skipped is surfaced, not hidden (Rule 12). A green V4.0 authorizes V4.1 (the DISCOVERY cost screen
in `00` §13) — it does **not** authorize touching FINAL_OOS.

---

## 7. What this spec does NOT do (guards)

- It does **not** tune any indicator/regime/exit/sizing parameter or add a grid axis (that's `00` §1/§5).
- It does **not** compute a return, Calmar, Sharpe, or turnover number — V4.0 is build + count only.
- It does **not** touch DISCOVERY/OOS returns, and **never** FINAL_OOS.
- It does **not** modify the data layer, the v2 `costs.py`, the v2 engine, or any S3/`11`/`FINAL_OOS`
  number — it is an additive consumer (§8).
- It does **not** re-decide anything frozen in `00`; on any apparent conflict, `00` wins (§0).

---

## 8. Blast radius (stated up front)

- **Additive only.** A new `backend/app/swing_v4/` package that **reads** `prices_adjusted`,
  `market_internals`, `india_vix`, and the Nifty 50 series, and **imports** v2 `costs.py` / accounting
  primitives **without editing them**. No change to `prices_adjusted`, membership, the v2 engine, or the
  paper_v2 live shell ⇒ **S3 `11` probation and `FINAL_OOS` are untouched and byte-identical.**
- The only external touch is the **one-off Nifty 50 price/TRI fetch on a cache miss** (§3), outside pytest.
- If v2 `Portfolio`/`Fill` turn out to carry rebalance-specific assumptions, V4.0 **composes/wraps** around
  them under the same fill discipline and **surfaces the incompatibility** (§1, Arafat-confirmed) — it does
  **not** edit the v2 classes and does **not** silently fork.

---

## 9. File map

| Concern | File |
|---|---|
| Swing config (frozen `00` defaults + grid knobs) | `backend/app/swing_v4/config.py` (new) |
| Indicators (MACD/weekly/SMA/EMA/ATR) | `backend/app/swing_v4/indicators.py` (new) |
| Precomputed entry/exit primitives | `backend/app/swing_v4/signals.py` (new) |
| Regime score (0–5 → f) | `backend/app/swing_v4/regime.py` (new) |
| Event-driven engine (context/state/step_day/run) | `backend/app/swing_v4/engine.py` (new) |
| Returns-blind N_max footprint | `backend/app/swing_v4/footprint.py` (new) |
| Cost model (reused, unmodified) | `backend/app/backtest_v2/costs.py` |
| Accounting primitives (reused if agnostic) | `backend/app/backtest_v2/engine.py` (`Portfolio`/`Fill`) |
| Adjusted prices / internals / VIX reads | `backend/app/data/bhavcopy/store.py` (`read_prices_adjusted`, `read_market_internals`, `read_india_vix`) |
| Nifty 50 price + Nifty 50 TRI loaders | `backend/app/backtest_v2/benchmark.py` |
| Tests | `backend/tests/swing_v4/` (new — battery §5) |
| Downstream | `00_SWING_PREREG.md` V4.1+ (cost screen / battery / OOS — not this doc) |

---

## 10. Execution (cold-session runnable — NOT STARTED until §11 is signed)

> No code before §11 LOCK. V4.0 produces an engine + a returns-blind count only; **no return backtest**.
> Honor the token budget (Rule 6); update Status + a Session log per sub-step; do not mark Done if anything
> was skipped (Rule 12).

### V4.0a — Indicators + regime + signal precompute
- **Status:** ⬜ NOT STARTED (gated on §11).
- **Do:** `indicators.py`, `regime.py`, `signals.py` + their parity / causality / completed-weeks /
  missing-VIX tests (§5 items 1, 6, 7). Wire the Nifty 50 price loader (fixture in tests; one-off fetch on
  cache miss outside tests).
- **Done:** indicator parity green; regime score reproduces a hand-built 0–5 fixture; no-lookahead on the
  indicator/regime layer proven.

### V4.0b — Event-driven engine + fill discipline
- **Status:** ⬜ NOT STARTED.
- **Do:** `config.py`, `engine.py` (`build_context`/`SwingLoopState`/`step_day`/`run`); reuse v2
  `costs.py` + `Portfolio`/`Fill` (or documented thin equivalent, §1). Tests §5 items 2–5, 8–10.
- **Done:** entry/exit/floor fixtures green; whole-share + clamp-to-cash + fill-ordering + identity-
  continuity proven; the full future-bar-corruption no-lookahead test (§5 item 5) green over the engine.

### V4.0c — Returns-blind `N_max` lock
- **Status:** ⬜ NOT STARTED.
- **Do:** `footprint.py` — frozen entry + Type-3 exit state machine over DISCOVERY, **unconstrained, count
  only** (§4). Report max/p95/p99 of concurrent holdings; **lock `N_max` ≈ p99**.
- **Done:** `N_max` integer + full distribution recorded in the Session log **before** V4.1; **no return
  computed**; FINAL_OOS untouched.

---

## 11. Locked commitments (Arafat — sign to flip DRAFT → LOCKED)

This doc decides only **engine-construction** questions (everything strategy is frozen in `00`). Confirm or
redline. Items marked **(decision)** are where I picked a recommended default.

1. **Inheritance:** every strategy/regime/grid/acceptance value is inherited frozen from `00`; on any
   conflict `00` wins; this doc re-decides nothing (§0).
2. **Architecture:** new `backend/app/swing_v4/` package; mirror the v2 `build_context`/`step_day` split so
   a future live shell shares the per-day core; event-driven per-name `step_day` (§1).
3. **Reuse vs fork — ✅ RESOLVED (Arafat):** **reuse** v2 `costs.py` and `Portfolio`/`Fill` and **never
   edit** them; compose/wrap if an assumption doesn't fit and **surface** it — no silent fork (§1, §8).
4. **`step_day` ordering:** apply-prior-fills → MTM → update anchor → exits (floor then configured) →
   regime score → entry scan (capacity + `adv_20` tiebreak) → snapshot (§1.1).
5. **Returns-blind `N_max` — ✅ RESOLVED (Arafat):** measured **unconstrained — no cap, no throttle, no
   sizing, no PnL** (literal `00` §3.5 reading; conservative tail cap); lock ≈ p99; record number +
   distribution before V4.1. **Adds 0 to K** (no return evaluated); the `00` §5 `N_max ± 2` neighbors *do*
   count toward K when return-evaluated in V4.2 (§4).
6. **Nifty 50 source — ✅ RESOLVED (Arafat): use the existing repo `benchmark` loaders** (Nifty-50 price for
   regime 1–2, `load_tri(TRI_NIFTY_50)` for §2). Local cache `data/niftyindices/` is currently empty ⇒ one
   **one-off live fetch** populates it (outside pytest; tests use the existing `price_nifty50_fixture` /
   `tri_nifty50_fixture`) (§3).
7. **Test battery:** §5 items 1–10 are the V4.0 done-bar; future-bar-corruption (§5.5) is the headline
   no-lookahead guard; no live API in pytest.
8. **Scope:** V4.0 is build + unit-test + returns-blind count **only**; no return backtest; FINAL_OOS
   untouched; a green V4.0 authorizes V4.1, not OOS (§6).

> **Signed:** Arafat — 2026-06-24 (all 8 commitments approved as recorded above, incl. the close-based +
> market-AMO deployment finding that keeps `00` frozen with no §13 deviation; DRAFT → LOCKED). **V4.0a
> authorized** — indicators + regime + signals build under §5 fidelity/no-lookahead tests; no return
> backtest until V4.0c's returns-blind `N_max` lock is recorded.

---

## Exit criteria
- [x] §11 locked by Arafat (DRAFT → LOCKED) — 2026-06-24.
- [ ] V4.0a — indicators + regime + signals built and tested (parity / causality / completed-weeks / VIX).
- [ ] V4.0b — engine + fill discipline built; entry/exit/floor/whole-share/fill-ordering/identity +
      future-bar no-lookahead all green; existing suites still green (additive proof).
- [ ] V4.0c — `N_max` locked from the returns-blind distribution; number + distribution recorded; no return
      computed; FINAL_OOS untouched.
