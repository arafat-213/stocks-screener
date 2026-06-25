# v4 / 00 — Daily Swing Strategy: Master Pre-Registration

> **🛑 PROGRAM CLOSED — 2026-06-24: RESEARCH NOTE (pre-accepted §6 null).** V4.1 cost screen returned
> **0/3 §6.1 survivors** (best costed Calmar ratio 0.31 < 1.0 vs Nifty 50 TRI; the candidate 0.11) — daily
> single-name swing does not clear a costed bar on this market; high turnover (828–2660%) erases the edge,
> and the book trails the index even pre-cost. V4.2/V4.3 N/A; **v4-FINAL_OOS NEVER touched (pristine)**;
> v4 ledger K=6. One forward lead: the §6 selection-quality diagnostic read **edge-discarding** (liquidity
> creaming hurts) → authorizes a *separate future* prereg for a return-informed selector (its own K). See
> §13 (V4.1) + Exit criteria for the full table.
>
> **Status: LOCKED — 2026-06-23 (Arafat). §12 signed (all 10 commitments). ✅ AMENDMENT 1 SIGNED
> 2026-06-24 (§14):** the V4.0c returns-blind footprint proved the signal is
> intrinsically broad (mean 118 / p99 371 concurrent), which invalidates the §3.5 `N_max`-as-sizing-divisor
> premise. Amendment 1 (§14) replaces it with a **binding concentration cap `target_positions` (= slot cap
> AND sizing divisor, ops-set = 15)**, a **top-`target_positions` `adv_20` selector**, and a **`U=200`
> `stable_universe`** universe. All three are **return-blind** (no return seen; K stays 0; FINAL_OOS
> pristine). **On any conflict, §14 supersedes §3.1 / §3.5 / §5 / §12-item-5,7.** Engine rework (V4.0
> re-opened) + V4.1 execution run in a later cold session.
> This is the anti-HARKing
> master commitment for the **v4 swing family**: it freezes — *before any return number is
> measured* — the strategy model, the regime-score definition, the (small) search grid, the
> binding acceptance rule, the deflation/K accounting, the discovery/OOS split, and the
> one-shot OOS protocol. Moving any stick after seeing a result (a new lever level, a loosened
> threshold, a re-touched OOS) is the v1 sin and is forbidden.
>
> **Owner:** Arafat. **Created:** 2026-06-23. **Depends on:** `01_REGIME_DATA_LAYER.md`
> (COMPLETE — breadth/A-D + India VIX landed, 5-factor regime inputs available).
>
> **What this doc is NOT:** it is not a task list and not the engine. The v4 daily event-driven
> engine is a *separate* implementation spec (`02_SWING_ENGINE.md`) that may only begin **after**
> this prereg locks. This doc commits the strategy; that doc builds the plumbing under the same
> fill discipline (§9).

---

## 0. Context — what v4 is, and how it relates to S3

v4 is a **daily, single-name, event-driven swing strategy** for spare capital, designed to run
**in parallel** with S3 (the monthly cross-sectional momentum runner currently in `11` probation —
see [[s3-probationary-paper-deploy-11]]). It is philosophically distinct from S3/v2:

| | **S3 (v2/v3 family)** | **v4 swing family** |
|---|---|---|
| Decision cadence | Monthly rebalance (last trading day → next open) | **Daily** post-close entry/exit checks |
| Selection | Cross-sectional rank of the whole universe | **Per-name event signal** (a name qualifies on its own) |
| Position model | Top-N portfolio, rank drop-out exit | Single-name entries, **per-position trailing exit** |
| Regime overlay | **Binary** risk-on/off (full book to cash) | **Continuous 0–5 score** → 0% / 50% / 100% deployment |
| Family K | carries (~69, deflation headwind) | **resets to 0** (§1) — independent economic prior |

> **Plain-language note (Rule 13):** a "swing" trade is a position held days-to-weeks that rides a
> single stock's up-move and exits when the move stalls — like a `while (trend_intact)` loop per
> name, versus S3's monthly `for each name in top-N` snapshot. The **regime score** is a throttle on
> the gas pedal (how much spare capital the book is allowed to deploy right now), not a per-name
> signal. The **ATR trailing stop** is a stop-loss that ratchets *up* as the stock makes new highs but
> never moves down — it locks in gains while giving the trend room to breathe (ATR = Average True
> Range = the stock's typical daily move, so "3×ATR" = "give it 3 normal days of wiggle before exiting").

**Honest framing (eyes-open, locked in the brainstorm 2026-06-23):**
- v4 is **NOT a portfolio diversifier.** Both S3 and v4 are long-only trend/momentum beta — they will
  be correlated, both thrive in bull markets and struggle in chop/bear. v4 is a *different engine on
  the same risk premium*, run on capital that would otherwise sit idle. Accepted, not oversold.
- **The probation (a future `11`-style spec) validates ops/fidelity ONLY — never edge.** v4 still owes
  this full research arc (discovery → §6 battery → DSR/PBO → one-shot OOS) *before* any probation, and
  a clean probation earns only a small real-capital allocation under a *separate future* prereg.

---

## 1. Scope discipline (the anti-HARKing line — binding)

- ✅ **K resets to 0 for the v4 family.** This is the one legitimate K-reset in the whole program: v4
  is an **independent strategy family with an independent economic prior** (event-driven single-name
  trend-following, not cross-sectional momentum ranking). The v2/v3 momentum trials (~69) did **not**
  select a swing candidate, so they carry no false-discovery weight here. K=0 is a *start*, kept honest
  by (a) freezing all parameters to convention (§3/§4) and (b) accumulating K from a **fresh v4 config
  ledger** as configs are evaluated (§7). The momentum ~69 does **not** carry; v4's own ledger does.
- ✅ **One-shot OOS retained per family** (§8). v4 gets its own single, pristine FINAL_OOS shot; spending
  it is the only way a candidate becomes "validated, deployable."
- ❌ **No parameter mining.** MACD(12,26,9), DMA(20,50,200), EMA(50), ATR(20) are **frozen at textbook
  convention** (§3) — chosen *because* they are conventional, not because they backtested well (we have
  not run a backtest). The regime-score weights, bucket cuts, and sizing map are **frozen at Arafat's
  design** (§4). Tuning any of these after a result is the v1 sin.
- ❌ **No grid expansion after results.** The search grid is the small, fully-enumerated set in §5,
  decided now. No lever level is added, no threshold loosened, no axis introduced after seeing a number.
- ❌ **No FINAL_OOS peek** before a single §6-locked candidate exists (§8).
- ❌ **No data-layer change.** v4 consumes the `01`-landed `market_internals` + the v2 bhavcopy adjusted
  store **as-is**. It writes nothing into the data layer and cannot move an S3/`11` or `FINAL_OOS` number.

---

## 2. The goal (LOCKED-on-sign)

**Risk-adjusted outperformance of the cheap passive alternative for spare capital**, net of realistic
costs — not raw return, not "positive vs cash."

- **Primary deployment benchmark: Nifty 50 TRI** (the literal "spare capital sitting in a broad index
  fund" alternative — locked by Arafat 2026-06-23). **Rationale:** S3 already competes against Nifty200
  Mom30 TRI; v4's entry bar is deliberately strict (four stacked conditions), so the book is **expected
  to sit substantially in cash**, and the honest comparison for an often-partially-deployed spare-capital
  book is the broad market, not the fully-invested momentum index. **Nifty200 Mom30 TRI is still reported
  as a reference** (so we can see the gap to the aggressive index), but the *bar* is Nifty 50 TRI.
- **Falsifiable target (set before any tuning, mirrors `08` §2b — the corrected bar):** beat **Nifty 50
  TRI** on **Calmar after base costs** while holding **max drawdown ≤ 100% of the benchmark's**.
  A strategy that merely *matches* the index is the explicit **"buy the index fund"** outcome — a valid,
  money-saving research-note close, not a deployable strategy.
- **The edge thesis (what would justify v4 existing):** the passive momentum index has *no drawdown
  control and no cash overlay*; v4's intended edge is **per-name ATR trailing exits + a continuous
  regime throttle** that de-risk between the index's annual reviews. We are the same *kind* of bet; we
  try to win on **risk control and cash discipline**, net of the higher turnover that daily swing incurs.

---

## 3. The strategy model (frozen on sign)

Position-centric, single-name, daily event-driven. Signals computed on day `D` **close**; all fills at
day `D+1` **open** (no intrabar ordering, §9). All indicators on the **split/bonus-adjusted** series.

### 3.1 Universe (eligibility)
> ⚠️ **SUPERSEDED by Amendment 1 (§14) — SIGNED 2026-06-24.** The universe is narrowed to a `U=200`
> `stable_universe` (return-blind Nifty200 proxy); the `adv_20 ≥ ₹5cr` floor is retained *beneath* it as a
> per-day tradeability safety. Read §14 as authoritative on any conflict.

The **v2 liquid bhavcopy universe**: survivorship-free, `instrument_id`-stitched (post `05`/`06`/`07`),
gated by `adv_20 ≥ ₹5cr` (`5e7`, matching `signals_v3.py`) as a per-day tradeability floor. Same
eligibility S3 uses — no new universe construction.

### 3.2 Indicators (frozen at textbook convention)
| Indicator | Definition | Use |
|---|---|---|
| MACD(12,26,9) | EMA12−EMA26, signal=EMA9 of MACD; on adjusted close | daily entry/exit + weekly trend |
| Weekly MACD | same params on **weekly** bars (W-FRI resample, **completed weeks only**) | entry condition 1 |
| SMA 20 / 50 / 200 | simple MA of adjusted close | entry conditions 2–3 |
| EMA 50 | exp MA of adjusted close | exit comparator (Type 2) |
| ATR(20) | Wilder ATR on **split-adjusted** O/H/L/C | exit (Type 3) sizing of the trail |

### 3.3 Entry (frozen — all four true on day `D` close → BUY fill `D+1` open)
1. **Weekly MACD line > 0** (last *completed* week — higher-timeframe trend up).
2. **Adjusted close > SMA200** (long-term uptrend).
3. **SMA20 > SMA50** (intermediate uptrend).
4. **Daily MACD bullish crossover on `D`**: `MACD[D] > signal[D]` **and** `MACD[D−1] ≤ signal[D−1]`.

### 3.4 Exit (frozen candidate = **Type 3**; Types 1–2 are the *only* grid comparators, §5)
- **Type 3 — ATR trailing stop (the candidate, Arafat's preferred):**
  `anchor = max(adjusted close since entry)`; `stop = anchor − 3 × ATR20[D]`. **Exit when adjusted
  close[D] < stop** → SELL fill `D+1` open. (Close-based anchor, not intraday high — avoids intrabar
  lookahead, §9; the `3×` multiple is frozen, with `{2.5, 3.0, 3.5}` as the §6.3 plateau neighborhood.)
- **Type 1 — opposite daily MACD crossover** (comparator only): `MACD[D] < signal[D]` and
  `MACD[D−1] ≥ signal[D−1]`.
- **Type 2 — close < EMA50** (comparator only).
- **Catastrophic floor (recommended, §12-decision):** a wide `−25%`-from-cost-basis circuit breaker on a
  *close* breach → next-open fill, retained beneath Type 3 (the trail can sit far below cost early in a
  trade; the floor caps a gap-down before the trail tightens). Mirrors v2's circuit breaker. *(Confirm.)*

### 3.5 Position sizing & the regime throttle (recommended defaults — §12-decision)
> ⚠️ **SUPERSEDED by Amendment 1 (§14) — SIGNED 2026-06-24.** `N_max` is renamed `target_positions` and
> reframed from a "rarely-binding tail cap" to a **binding concentration cap** that is BOTH the hard slot
> cap AND the sizing divisor (`per-position = f × capital / target_positions`), ops-set = 15. The footprint
> (§14) showed the "cap rarely binds / divisor is sensible" premise below is **false** (mean 118 concurrent).
> The `adv_20` tiebreak is promoted to the **primary top-`target_positions` selector**. Read §14 as
> authoritative on any conflict; the no-forced-liquidation and whole-share/clamp-to-cash mechanics below are
> UNCHANGED.

- **Max concurrent positions** `N_max` — **set by a returns-blind procedure, not picked** (resolves the
  "N_max must lock before the run" tension, Arafat 2026-06-23). Before any backtest (V4.0 §13), run the
  **frozen** entry rule + Type-3 exit as a state machine over DISCOVERY and record **only the position
  *count* time series** (fresh entry signals/day + concurrent open holdings) — **never PnL/returns**.
  Lock `N_max` at the **≈99th percentile of concurrent holdings** so the cap is a *tail risk control that
  rarely binds*, not a performance lever (if signals never crowd, `N_max` simply never clips; if they do,
  it caps tail concentration). The locked integer + the full count distribution (max / p95 / p99) are
  recorded **before** V4.1. The §5 grid then tests `N_max ± 2` (§6.3) to confirm it is not a hidden knob.
  *(This measurement is signal-footprint characterization — the same category as measuring universe size
  or turnover structure — and is pre-registration-safe precisely because it is returns-blind.)*
- **Deployable fraction** `f ∈ {0, 0.5, 1.0}` from the regime bucket (§4). Caps **gross exposure** at
  `f × capital`.
- **Per-position target** = `(f × capital) / N_max`, **equal-weight, whole-share integer** (NSE; mirrors
  the S3 `11` §13 whole-share deviation), **buys clamped to cash on hand** (the S3 negative-cash fix).
  *(With `N_max` set non-binding above, per-position size is effectively `f × capital / N_max` and the cap
  only redistributes on the rare crowded day.)*
- **New entries** are taken only while `gross < f × capital` **and** `open positions < N_max`. When more
  entry signals fire than free slots, rank by **`adv_20` (most liquid first)** — a neutral, non-return
  tiebreak (frozen; §12-decision — *not* a return-optimized ranker, to avoid a hidden selection knob).
- **On a regime *downgrade*** (bucket falls): **no forced liquidation** — open positions exit only via
  their own §3.4 rules; the regime throttle only blocks/limits *new* deployment. *(§12-decision: this vs
  force-scale-to-target. Recommended: no forced liquidation — the per-name ATR trail is the de-risk;
  forcing sells on a regime flicker invites whipsaw. v2 scaled the whole book because it was monthly and
  had no per-name stop; v4 does, so the division of labor differs.)*

---

## 4. The regime score (frozen at Arafat's design — the v4 overlay)

A **continuous 0–5 score**, recomputed daily from `market_internals` (`01`) + the bhavcopy index series.
Each condition contributes **+1**:

| # | Condition | Source series | Tier |
|---|---|---|---|
| 1 | Nifty close > Nifty 200 DMA | bhavcopy index series (`01` §8.1) | 3-factor floor |
| 2 | Nifty 50 DMA > Nifty 200 DMA | same | 3-factor floor |
| 3 | Breadth > 60% | `market_internals` (**liquid** breadth — §12-decision) | 3-factor floor |
| 4 | A/D ratio > 1 | `market_internals` (**liquid** A/D) | 5-factor |
| 5 | India VIX < 20 | `market_internals.india_vix` | 5-factor |

**Buckets → deployable fraction (frozen):** `0–1 = Bear → 0%`; `2–3 = Neutral → 50%`; `4–5 = Bull → 100%`.

- **Tier:** the candidate uses the **full 5-factor** score (all inputs landed in `01`). The **3-factor**
  score (conditions 1–3, buckets rescaled to `0=Bear / 1–2=Neutral / 3=Bull`) is a **reported ablation
  diagnostic**, not a separate selection trial (keeps K small — running it as a candidate would be K+1).
- **Breadth/A-D series — LOCKED to the liquid-subset series (Arafat 2026-06-23):** conditions 3 & 4 read
  the `liq_breadth_pct` / `liq_ad_ratio` columns (~562 names/day), matching v4's liquid trading universe
  (§3.1). Rationale: for a deployment throttle on a liquid-only book, the breadth measure must match the
  hunting ground — it won't wave v4 to full deployment during a microcap-froth episode its names aren't in.
  The all-EQ series (~1,635 names/day, also stored in `01`) is the documented alternative; the two are 0.97
  correlated and flip the `>60%` point on 8.7% of days (concentrated at regime turns). Locked, not tuned.
- **Missing-VIX day (18 of 2336, surfaced not filled in `01`) — LOCKED conservative (Arafat 2026-06-23):**
  condition 5 scores **0** that day (the score cannot exceed 4, biasing toward *less* deployment on a day
  we cannot confirm calm). No forward-fill, no rescale, no degrade-to-3-factor.
- **Causality (§9):** the score on day `D` uses only completed-day `D` values and trades `D+1` open. Any
  DMA uses trailing windows with `min_periods = window`. No intraday/in-progress value ever enters.

---

## 5. The search grid (small, fully enumerated — decided now)

The candidate is the §3/§4 design with **Type 3 exit, 5-factor regime, `target_positions=15`** (Amendment 1,
§14; was `N_max=10`). The grid exists only
to (a) confirm the candidate is a *region not a spike* (§6.3) and (b) check the exit choice is principled,
**not** to mine for the best number. Every config is logged to the v4 ledger and counts toward K (§7).

| Axis | Frozen candidate | Enumerated alternatives (the ONLY ones) | Role |
|---|---|---|---|
| Exit rule | **Type 3 (ATR 3×)** | Type 1 (MACD cross), Type 2 (EMA50) | exit-choice robustness |
| ATR multiple | **3.0** | 2.5, 3.5 | §6.3 plateau (continuous knob) |
| `target_positions` (§14) | **15** (ops-set, §14) | {13, 15, 17} | §6.3 plateau (confirms the cap is not return-tuned) |
| Regime tier | **5-factor** | 3-factor (reported ablation, §4) | overlay-value diagnostic |

Total selection trials are **bounded and pre-enumerated** (the candidate + its immediate neighbors);
no axis or level is added after a result. **Two-stage** (mirrors `08`):
- **Stage 1 — cost screen:** the candidate (and the exit-rule alternatives) on full DISCOVERY at **base
  + pessimistic** cost. Record turnover, base Calmar, maxDD, win rate, avg hold, §6.1 ratio. Log to ledger.
  Also run the §6 **selection-quality diagnostic** (`B_liquid` vs `B_random` vs `B_all`) and record its read
  — non-gating, adds 0 to K (it informs a possible *future* amendment, never this run's candidate).
- **Stage 2 — battery (only configs clearing §6.1):** §6.2 / §6.3 (over the ATR-multiple & `target_positions`
  neighbors {13,15,17}) / §6.5, + §6.4 diagnostic. Apply §6 acceptance.

---

## 6. Pre-committed acceptance rule (binding — decided before any run)

A config becomes the **single locked OOS candidate** iff **all** hold on full DISCOVERY:

1. **§6.1 cost survival:** pessimistic-cost Calmar ratio vs **Nifty 50 TRI** ≥ **1.0** (swing turnover
   is high — this is the *primary* gate; costs are the most likely killer).
2. **§6.2 concentration — SKEW-AWARE gate (the `09`/`10` pattern, NOT classic drop-top-10), Arafat
   2026-06-23:** a trend/swing book is *supposed* to ride a few big winners longer, so adversarially
   deleting the top-10 P&L names and demanding 70% survival would penalize the exact behavior we want.
   Instead the gate is the v3 skew-aware battery: over many **random subsets** of the trade population,
   **median Calmar ≥ 0.70** of base **and** **p5 (5th-percentile) Calmar ≥ 0.50** of base, with **≥ 25
   rotating distinct contributors** to P&L (the edge is broad-based across names/time, not a 2-name
   fluke). Random subsets sometimes include and sometimes exclude the winners → this measures
   *broad-based-ness* without punishing legitimate winner-concentration. **The classic drop-top-10
   retention is still computed and reported as a contamination guard**, but it is **diagnostic, not
   gating**; a pass-skew/fail-classic config is labeled **"conditional"** (per `10`), never "validated."
3. **§6.3 plateau:** the candidate and its §5 neighbors (±1 step on ATR multiple **and** on `target_positions`,
   i.e. {13,15,17}) stay ≥ **85%** of the candidate's base Calmar — a region, not a lone peak.
4. **Deployment bar (corrected, = `08` §2b):** beats the primary benchmark (§2) on **base-cost Calmar**
   with **maxDD ≤ 100%** of the benchmark.
5. **§6.4 subperiod** reported, **not** gating (window-fragility demoted per TBE3/`05` §2 / the whole arc).

**Exit-choice rule:** Type 3 is the registered candidate. If Type 3 fails §6 but Type 1 or Type 2 passes,
that is a **reported finding, not a silent swap** — promoting a comparator to candidate is a *new*
registration decision (a fresh K-bearing trial), recorded explicitly, never a quiet substitution.

**Selection-quality diagnostic (pre-registered 2026-06-24; non-gating, adds 0 to K).**
*Why now:* the Amendment-1 footprint showed the stable-`U=200` book naturally wants **~46 concurrent names
(mean)** against a binding `target_positions = 15` — so the top-15-by-`adv_20` selector binds **~3:1** and is
therefore a *first-order return driver*, not a rare-day tiebreak. This diagnostic measures, in the V4.1 cost
screen, **whether liquidity-creaming systematically discards edge** — *without* turning the selector into a
return-mined choice. It changes **nothing** about the candidate, the §5 grid, the §6 gates, or the §8 OOS.

*What is run* (same frozen engine / entry / exit / regime / sizing; **only the cap+selector differ**; full
DISCOVERY, base cost):
- **`B_liquid`** — the candidate: keep the top-`target_positions` by `adv_20` when oversubscribed (the actual engine).
- **`B_random`** — keep a *random* `target_positions` when oversubscribed; reuse the §6.2 skew-aware
  random-subset machinery to report **median** and **p5** Calmar over seeds (a distribution, not one draw).
- **`B_all`** — *no* cap: hold every qualifying name equal-weight (the ~46-name unconstrained book). A
  **capital-blind reference only** (not deployable at ₹3.5L — sub-tradeable sizes); run it return-only
  (`whole_shares` off) purely to bound how much return lives in the names the cap drops.

*Pre-committed read (decided before any number; the ≥85% threshold reuses the §6.3 plateau tolerance — no new magic number):*
- **Neutral** — `B_liquid` ≥ **85%** of `B_random` median Calmar ⇒ liquidity selection costs ~nothing; keep the engine as-is, the cap is just a cap.
- **Favorable** — `B_liquid` ≥ `B_random` median ⇒ liquidity selection mildly *helps* (plausible — liquid names fill cleaner, lower impact); keep, reinforced.
- **Edge-discarding** — `B_liquid` < **85%** of `B_random` median **and** materially below `B_all` ⇒ evidence
  the selector throws away edge. This **does not** swap the selector in this run; it **authorizes a separate
  future amendment** that introduces a return-informed selector as a budgeted, §6.3-plateau-tested grid axis
  carrying **its own K** (identical to the exit-choice "promotion is a fresh K-bearing trial" rule above).

*Guards (anti-HARKing):* **report-only** — the locked OOS candidate stays top-15-by-`adv_20` **regardless** of
this diagnostic (same status as the §6.4 subperiod and the classic drop-top-10 retention). `B_random` / `B_all`
are reference books, **not** configs we may keep-the-best-of; neither can be promoted to the candidate from
this run, so the diagnostic **adds 0 to K**. A bad result triggers *new* pre-registered work, never a quiet swap.

**Null outcome (pre-accepted close):** if **0** configs satisfy 1–4, the v4 swing strategy is a
**research note** — `FINAL_OOS` is **not** touched. A null is the honest finding that daily swing on this
market does not clear a costed, deflated bar; it is **not** a prompt to add a grid level, loosen a
threshold, or re-touch OOS (§1).

---

## 7. Deflation & K accounting (honest search cost — K=0 *start*)

- **K starts at 0** for the v4 family (§1) and **accumulates from a fresh v4 config ledger** as each §5
  config × cost level is evaluated. The momentum ~69 does **not** carry.
- At OOS (§8): report **raw Sharpe, K, deflated Sharpe** (`validation.deflated_sharpe`) + **PBO**
  (`pbo_cscv` over walk-forward windows on DISCOVERY; no fold reaches FINAL_OOS).
- **Honest headwind:** K is small at the start, but a small K does *not* make a marginal edge real —
  daily swing's high turnover means the **costed** Calmar (§6.1), not the gross one, is the number that
  must clear, and the deflated Sharpe must survive whatever K the grid accumulates. A marginal pass is a
  research note, not a deployment.

---

## 8. Splits & the one-shot OOS protocol

- **DISCOVERY** = `validation.DISCOVERY (2018-02-06 → 2023-06-30)` — all of §5/§6/§7 lives here.
- **v4-FINAL_OOS** = `validation.FINAL_OOS (2023-07-01 → 2026-06-12)` — touched **exactly once**, only
  after a single §6-locked candidate exists, **never** on the null outcome. The OOS run is the
  byte-for-byte locked candidate through the v4 engine on FINAL_OOS — once, no re-tuning.
- **Eyes-open contamination caveat (ACCEPTED by Arafat 2026-06-23):** these calendar bytes
  were *seen by the momentum program*, but they did **not** select a swing candidate (different signals,
  K=0), so the window is **unspent for the v4 family**. What is *not* pristine is the **researcher's
  macro-knowledge** of 2023–2026 (a real but bounded contamination — we cannot un-know that period was a
  bull run). Therefore: a FINAL_OOS pass here is **"in-sample-clean for v4, macro-contaminated for the
  researcher"** — strong, but the **truly clean** validation is the **forward paper probation** (a future
  `11`-style spec on genuinely unseen post-2026-06 data). This prereg pre-accepts that limitation rather
  than pretending the window is pristine. *(Alternative: skip historical OOS entirely and validate only
  forward — rejected as too slow to ever falsify; confirm.)*

---

## 9. Lookahead / point-in-time landmines (the v1-sin guardrail — non-negotiable)

v1's actual sin was a **data-layer lookahead bias found late**, and v1's engine also peeked intrabar
(v2 overview §2.3). Every item below is a check, not a nicety:

- **Signal on close `D` → fill `D+1` open.** No same-day fill, no intrabar target/stop ordering.
- **ATR trail anchored on adjusted *close*, exit on close breach** — never the intraday high (no
  intrabar peek; the v1 trailing-stop-uses-same-bar-high bug is explicitly excluded).
- **Weekly MACD uses *completed weeks only*** — the in-progress week is invisible until it closes.
- **Adjusted (not raw) series everywhere** — a corporate action must not manufacture a phantom signal,
  and ATR must be computed on split-adjusted O/H/L (the `01`/`05` adjustment discipline).
- **`instrument_id`-stitched identity** (`06`/`07`) — a succession/merger must not look like an exit +
  a new entry, nor strand a position in a ghost ISIN.
- **Regime score is causal** — completed-day inputs only, trailing-window DMAs (`min_periods = window`),
  missing-VIX surfaced not filled (§4).
- **Survivorship-free universe** — daily eligibility = names that actually traded that day, never
  reindexed against today's membership.

---

## 10. Definition of Done (the deployment bar)

The candidate is **"validated, deployable (pending forward probation)"** only if the single locked config:
- Beats the **primary benchmark** (§2) on **Calmar after base costs** on v4-FINAL_OOS, with
  **maxDD ≤ 100%** of the benchmark; AND
- Holds §6.1 / §6.2 / §6.3 out-of-sample (the hard gates do not collapse); AND
- Is tradeable on realized turnover/capacity (§6.5); AND
- Raw + deflated Sharpe + PBO reported together (§7); AND
- The §8 contamination caveat is restated in the verdict (FINAL_OOS pass ≠ forward-validated).

§6.4 reported OOS as a diagnostic, not a gate. Anything less is a **research note** (Rule 12) — no
softening of the hard gates to manufacture a pass. **Even a full PASS** earns only entry into a forward
paper probation under a *separate future* prereg, then a small real-capital allocation under *another*;
it does **not** authorize real capital directly.

---

## 11. What this prereg does NOT do (guards)

- It does **not** tune MACD/DMA/EMA/ATR params or the regime weights/cuts/sizing map (§1, §3, §4).
- It does **not** add a grid axis/level or soften a §6 threshold after a result (§1, §5, §6).
- It does **not** change the data layer, the universe construction, or any S3/`11`/`FINAL_OOS` number
  (additive consumer only).
- It does **not** build the engine — that is `02_SWING_ENGINE.md`, gated on this lock.
- It does **not** touch v4-FINAL_OOS until a single DISCOVERY-locked candidate exists, and not at all on
  the null outcome (§8).
- It does **not** claim the historical OOS is pristine for the researcher (§8 caveat) — the clean test is
  forward probation.

---

## 12. Locked commitments (Arafat — sign to flip DRAFT → LOCKED)

Confirm or redline each. Items marked **(decision)** are where I picked a recommended default that you
should explicitly accept or change before any code.

1. **Family/K:** v4 is an independent family; **K resets to 0** and accumulates from a fresh v4 ledger;
   one-shot OOS retained per family (§1, §7).
2. **Goal/benchmark — ✅ ACCEPTED (Arafat 2026-06-23):** primary deployment bar = **Nifty 50 TRI**,
   Calmar-beat + maxDD ≤ 100%; Nifty200 Mom30 TRI reported as a reference only (S3 already competes there;
   v4's strict entry ⇒ it will sit substantially in cash, so the broad-market bar is the honest one) (§2).
3. **Strategy model frozen — ✅ (fill-next-open confirmed):** universe = v2 liquid bhavcopy; entry = the 4
   conditions (§3.3); exit candidate = **Type 3 ATR 3×** with Type 1/2 as the only comparators (§3.4);
   indicators at textbook convention (§3.2).
4. **Catastrophic floor — ✅ ACCEPTED (Arafat 2026-06-23):** retain the wide **−25%** close-breach circuit
   breaker beneath Type 3 (§3.4).
5. **Sizing/throttle — ✅ (throttle-only-new-deployment confirmed); ⚠️ AMENDED by §14:** ~~`N_max`
   procedure-locked returns-blind at ≈p99~~ → **`target_positions = 15`**, a *binding* concentration cap =
   slot cap **and** sizing divisor, with `adv_20` promoted to the **primary top-15 selector** (§14 A/B/C).
   Equal-weight whole-share, gross ≤ `f×capital`, **no forced liquidation on regime downgrade** — all
   UNCHANGED. `starting_capital = ₹3.5L` (§14 E).
6. **Regime score frozen — ✅ ACCEPTED (Arafat 2026-06-23):** the 5-condition 0–5 score, buckets
   `0–1/2–3/4–5 → 0%/50%/100%` (§4); 5-factor is the candidate, 3-factor a reported ablation; breadth/A-D
   = **liquid** series (`liq_breadth_pct`/`liq_ad_ratio`); missing-VIX day scores condition-5 = 0 (§4).
7. **Grid:** the small enumerated §5 grid (exit rule × ATR multiple × `target_positions ± 2` = {13,15,17}
   [§14; was `N_max ± 2`] × tier); no level added after results; two-stage screen → battery.
8. **Acceptance rule — ✅ §6.2 set to SKEW-AWARE (Arafat 2026-06-23):** §6 items 1–5 with §6.2 = the
   `09`/`10` random-subset skew-aware gate (median ≥ 0.70 + p5 ≥ 0.50 + ≥ 25 rotating contributors;
   classic drop-top-10 **diagnostic, not gating** — swing rides winners), exit-choice-is-not-a-silent-swap,
   pre-accepted null close.
9. **Splits + contamination caveat — ✅ ACCEPTED (Arafat 2026-06-23):** DISCOVERY/v4-FINAL_OOS reused from
   `validation`; OOS is "clean for the v4 family, macro-contaminated for the researcher" → **forward
   probation is the true clean test** (§8).
10. **Engine:** built separately in `02_SWING_ENGINE.md`, gated on this lock, under §9 fill discipline;
    reuses bhavcopy + `market_internals` + the v2 cost model.

> **Signed:** Arafat — 2026-06-23 (all 10 commitments approved/redlined as recorded above; DRAFT → LOCKED;
> `02_SWING_ENGINE.md` / V4.0 authorized — engine build + returns-blind N_max lock, no return backtest
> until that engine's fidelity + no-lookahead tests are green).

---

## 13. Execution (cold-session runnable — NOT STARTED until §12 is signed)

> No stage may begin before §12 is LOCKED. DISCOVERY only until a candidate is locked; v4-FINAL_OOS is
> spent exactly once, only on a §6-locked candidate, never on the null. Honor the token budget (Rule 6);
> update Status + a Session log per stage; do not mark Done if anything was skipped (Rule 12).

### V4.0 — Engine build + fidelity + returns-blind N_max lock (separate spec `02_SWING_ENGINE.md`)
- **Status:** ⬜ NOT STARTED (gated on §12 lock).
- **Do:** (a) build `backend/app/swing_v4/` — a daily event-driven engine sharing the bhavcopy adjusted
  store, `market_internals`, and the v2 cost model; signal-on-close → fill-next-open (§9). Indicator
  parity tests (MACD/DMA/EMA/ATR vs a hand-computed fixture), no-lookahead tests (future-bar corruption
  leaves past signals identical), whole-share + clamp-to-cash tests. (b) **Returns-blind signal-footprint
  measurement (§3.5):** run the frozen entry + Type-3 exit over DISCOVERY recording **only** the
  position-count time series (fresh signals/day + concurrent holdings) — **no PnL** — report max / p95 /
  p99 of concurrent holdings, and **lock `N_max` at ≈p99**. This is the answer to "what's the max active
  signals," and it happens *before* any return is computed.
- **Done-criteria:** engine reproduces hand-computed entry/exit on a tiny fixture; no-lookahead proven;
  cost model wired; **N_max locked from the returns-blind count distribution** (number + distribution
  recorded); **no DISCOVERY/OOS *return* backtest in this stage** (build + unit-test + count-only footprint).

### V4.1 — Stage 1: cost screen on full DISCOVERY
- **Status:** ✅ DONE 2026-06-24 — **NULL CLOSE (pre-accepted, §6).** `app/swing_v4/v41_cost_screen.py`
  over DISCOVERY (2018-02-06 → 2023-06-30), candidate + both exit comparators × base + pessimistic, ₹3.5L
  whole-share. **0/3 clear §6.1** (pessimistic Calmar ratio vs Nifty 50 TRI ≥ 1.0):

  | Cfg | exit | base Calmar | maxDD | turnover | win | hold | C_strat(pess) | ratio | §6.1 |
  |---|---|---|---|---|---|---|---|---|---|
  | **T3** (candidate) | ATR 3× | 0.083 | 34.4% | 828% | 33% | 569d | 0.039 | **0.11** | FAIL |
  | T1 (comparator) | MACD cross | −0.070 | 30.1% | 2660% | 34% | 793d | −0.167 | **−0.48** | FAIL |
  | T2 (comparator) | EMA50 | 0.145 | 27.4% | 1061% | 30% | 642d | 0.107 | **0.31** | FAIL |

  Benchmark Nifty 50 TRI Calmar = 0.346; the best config (T2) reaches **0.31× of the bar at pessimistic
  cost**, the candidate **0.11×**. **Costs are the killer** (the §6.1 thesis): turnover 828–2660% (T1's
  MACD-cross exit churns 3× the candidate's). The verdict holds even *before* costs — every config's *base*
  Calmar (≤ 0.145) is already below the benchmark's 0.346. **Exit-choice rule (§6):** T2 is the best
  comparator but still fails, so there is nothing to promote (a comparator *beating* the candidate would be a
  reported finding, not a silent swap — moot here).
- **Selection-quality diagnostic (§6, non-gating, adds 0 to K) — read = EDGE-DISCARDING:** `B_liquid`
  (top-15 by `adv_20`, the candidate) base Calmar **0.083** < 85% of `B_random` median **0.138** (ratio 0.60)
  **and** below `B_all` (no cap) **0.090** → the liquidity-creaming selector throws away edge (random 15
  beats it; the uncapped book beats it). Per §6 this **authorizes a separate future amendment** (a
  return-informed selector carrying its own K) — it is **not** a swap this run, and it does **not** rescue the
  null: even `B_random` median (0.138) and `B_all` (0.090) are far below the costed bar.
- **Ledger:** v4 K = **6** (3 configs × {base, pessimistic}); the diagnostic added 0. **`FINAL_OOS` untouched.**
  > **K-accounting correction (2026-06-25, append-only — original figure above stands as signed):** under the
  > corrected counting standard ratified in `05` §7.0, cost levels are an evaluation assumption, **not** a
  > trial (×1, not ×2). This run's effective independent K is **3** (the three exit-tightness configs), not 6.
  > The over-charge was the `× {base, pessimistic}` multiplier. The corrected carried v4 ledger is **4** (this
  > 3 + V4.4's MOM); see `05` §7.1. No result or verdict changes — recorded so future preregs do not re-inflate.
- Local report: `backend/reports/v41_cost_screen.txt` (gitignored). Engine support added additively:
  `SwingEngineResult.per_rebalance_turnover` (+`_daily_turnover`) so `metrics.compute_metrics` annualizes
  swing turnover, and a `SwingConfig.selector`/`selector_seed` knob for `B_random` (default `"adv"` ⇒ engine
  byte-identical). 8 V4.1 tests added; 36 swing_v4 green; **683 across backtest_v2 + paper_v2 + swing_v4**
  (additive-only — only `swing_v4/` files touched).

### V4.2 — Stage 2: battery + §6 acceptance
- **Status:** ⛔ N/A — not run. V4.1 produced **0 §6.1 survivors**, and V4.2 runs only on the §6.1-clearing
  set (§5 two-stage gate). With no survivor the §6 acceptance (items 1–4) is unreachable ⇒ the pre-accepted
  null (§6) closes the program at V4.1. No grid level added, no threshold loosened (§1).

### V4.3 — One-shot v4-FINAL_OOS + §10 verdict (only on a locked candidate)
- **Status:** ⛔ N/A — not run. No §6-locked candidate exists, so `v4-FINAL_OOS` is **never touched** (§6/§8
  forbid spending it on the null). It remains **pristine** for the v4 family.

---

## 14. Amendment 1 — concentration cap + universe (SIGNED 2026-06-24; APPLIED to the engine)

> **This amendment changes only RETURN-BLIND structural choices and is NOT the v1 sin.** The forbidden move
> (§ top, §1) is *moving a stick after seeing a **return***. Here **no return has been computed** — V4.0c's
> footprint recorded *counts only* (concurrent holdings), and the changes below are driven by an
> **operational/deployability constraint** (manageable book size + viable per-position size + AMO fill
> fidelity), not by any Calmar/Sharpe. Therefore: **K stays 0**, the v4 ledger is untouched, and
> **v4-FINAL_OOS remains pristine**. The §6 acceptance rule, the §8 OOS protocol, the entry rule (§3.3), the
> indicators (§3.2), the exit rules (§3.4), and the regime score (§4) are **all UNCHANGED**.

**Trigger (the V4.0c finding, `02` §4 / Session log).** The returns-blind footprint over DISCOVERY
(2018-02-06 → 2023-06-30; 1333 days, 922 instruments) returned concurrent-holdings **max 408 / p95 298 /
p99 371 / MEAN 118**. The §3.5 design used `N_max` for two jobs — a "rarely-binding tail cap" *and* the
sizing divisor (`per-position = f×capital / N_max`). The procedure sized the *cap* correctly, but its premise
("signals are sparse ⇒ the cap rarely binds ⇒ the divisor is sensible") is **false**: at p99 = 371 the book
naturally wants ~118 names, so as a divisor 371 yields microscopic positions (≈ capital/371), an unmanageable
100+-name book, and chronic ~68% cash drag (divisor 371 ≫ typical 118 ⇒ structurally under-invested). The
engine is correct; the footprint did its job — it *proved the strategy is intrinsically broad*.

**The decisions (frozen on sign):**

| # | Change | From (§3) | To (Amendment 1) | Why it is return-blind |
|---|---|---|---|---|
| A | **Rename + reframe** | `N_max` = returns-blind tail cap, locked ≈ p99 | **`target_positions`** = a **binding concentration cap**: simultaneously the hard slot cap **and** the sizing divisor (`per-position = f × capital / target_positions`). | A count-driven structural choice; no return consulted. |
| B | **Value** | 371 (≈ p99) | **`target_positions = 15`** (ops-set inside Arafat's manageable 15–25 band, nudged to the low end for **whole-share granularity at ~₹3-4L spare capital**: at 15, full-deploy per-position ≈ ₹23K vs ≈ ₹17.5K at 20, so integer-share rounding drag drops ~10→~3% on mid-priced names). | Set by an *operational* constraint (manageability + viable per-position size for the real capital), not by optimizing a return. The §6.3 plateau (axis renamed `target_positions ± 2` → **{13, 15, 17}**) confirms it is not a hidden knob. |
| C | **Selector** | `adv_20` was a *tiebreak only on the rare oversubscribed day* | **primary selector**: when > `target_positions` names fire, hold the top-`target_positions` by **`adv_20`** (most liquid first). | `adv_20` is the already-frozen *neutral, non-return* ranker (§3.5 / §12-item-5); promoting it adds no return information. |
| D | **Universe** | full v2 liquid bhavcopy (~562/day), `adv_20 ≥ ₹5cr` floor | **`stable_universe` at `U = 200`** (`app/backtest_v2/stable_universe.py`, from v3 `08`: top-U by 126-td median `adv_20`, semi-annual review + hysteresis, **no-lookahead tested**) — AND-ed into the entry scan; the `adv_20 ≥ ₹5cr` floor is **retained beneath it** as a per-day tradeability safety. | A structural/liquidity universe definition; chosen for tradeability/fill-fidelity, no return consulted. |
| E | **Backtest capital** | `starting_capital = ₹10L` (the `SwingConfig` default) | **`starting_capital = ₹3.5L`** for the V4.1+ screen, matching Arafat's real spare capital. | A *deployment fact*, not a tuned knob: it makes the screen's cost + whole-share rounding drag honest. It is the **conservative** end — granularity only improves as profits reinvest + a monthly SIP-style top-up grows the book (sizing is equity-based, so it compounds). |

**The `N_max` premise is formally retired.** With `target_positions = 15` as the *actual* cap, the cap binds
on most bull days (the footprint guarantees it) — that is intended. The cash-drag pathology is fixed: filling
20 slots at `f × capital / 20` = fully deployed at the regime-allowed gross. The 371 footprint number is
**retained as a diagnostic** (it is *why* a concentration cap is needed), no longer a lock.

**Honest caveats (Rule 12):**
- `stable_universe` ranks by **liquidity (ADV)**, not free-float market cap, so it is a *proxy* for Nifty200,
  not the index — it tilts large-cap and will not match the constituent list. The repo has **no point-in-time
  Nifty200 constituents** (`universe_membership` is only "ISIN traded that day"); sourcing real survivorship-
  free historical constituents is a **separate future data task**, not a blocker here.
- The selector concentrates the book toward the **most liquid** names that fired (not the "best setups") — a
  deliberately return-blind choice; whether that leaves edge on the table is a question for the V4.1 screen,
  **not** something to pre-optimize now.
- The **entry rule is deliberately left untouched.** Tightening it to be "more selective" is a *returns* bet
  (it claims to pick better names) → it would burn K and risks v3-style overfitting. It is **deferred** until
  after the V4.1 cost screen shows the actual concentrated book, and only then as a budgeted, plateau-tested
  grid axis (a *new* amendment, if at all).

**Downstream edits this implies (applied on signature):** §3.1 (universe), §3.5 (`N_max` → `target_positions`,
divisor, selector), §5 grid row (`N_max ± 2` → `target_positions ± 2` = **{13,15,17}**; candidate
`target_positions = 15`), §12 items 5 & 7 wording. `SwingConfig` defaults: `n_max` → `target_positions = 15`,
`starting_capital = 350_000`, new `universe_size_U = 200` (+ the `stable_universe` review/buffer knobs reused
from `08`). `02_SWING_ENGINE.md` is then updated to match and the engine reworked (`stable_universe` mask
AND-ed into the entry scan; `n_max` → `target_positions`; top-N selector; re-run the footprint as a
*diagnostic*). **V4.0 is re-opened** (it was prematurely called complete); V4.1 begins only after this rework's
tests are green.

> **Signed:** Arafat — 2026-06-24 (Amendment 1 decisions A–E approved as recorded above; DRAFT → APPLIED).
> Return-blind ⇒ K unchanged (still 0), v4 ledger untouched, v4-FINAL_OOS pristine. Engine rework (V4.0
> re-opened) + V4.1 cost screen are deferred to a later cold session; no strategy code written in the
> signing session.

---

## Exit criteria
- [x] §12 locked by Arafat (DRAFT → LOCKED) — 2026-06-23.
- [x] §14 Amendment 1 signed by Arafat — 2026-06-24 (concentration cap + `U=200` universe; return-blind, K unchanged).
- [x] V4.0 — engine built + fidelity/no-lookahead tested + Amendment-1 rework applied (`02_SWING_ENGINE.md`,
      2026-06-24): `target_positions=15` cap+divisor, top-N `adv_20` selector, `stable_universe` U=200,
      `starting_capital=₹3.5L`; footprint re-run as a diagnostic (stable U=200 mean 46 ≫ 15 ⇒ cap binds);
      675 tests green; no return computed; FINAL_OOS untouched.
- [x] V4.1 — DISCOVERY cost screen DONE 2026-06-24 → **NULL CLOSE** (0/3 clear §6.1; best ratio 0.31 < 1.0;
      selection-quality diagnostic = edge-discarding, non-gating); v4 ledger K=6; FINAL_OOS untouched.
- [x] V4.2 — N/A (no §6.1 survivor ⇒ §6 acceptance unreachable; pre-accepted null closes at V4.1).
- [x] V4.3 — N/A (no locked candidate ⇒ v4-FINAL_OOS NEVER touched; pristine for the v4 family).

> **PROGRAM CLOSE — 2026-06-24:** the v4 daily-swing family closes as a **research note** (§6 pre-accepted
> null). On this market, daily single-name swing — even with per-name ATR trailing exits + a continuous
> regime throttle — does **not** clear a costed bar vs the cheap passive alternative (Nifty 50 TRI): the high
> turnover (828–2660% annualized) erases the edge, and the book trails the index even *before* costs. The
> edge-discarding selection diagnostic is the one live forward lead — it authorizes a *separate future*
> prereg for a return-informed (not liquidity) selector, carrying its own K. FINAL_OOS pristine throughout.
>
> **Forward lead taken up:** `04_SELECTOR_PREREG.md` (LOCKED 2026-06-24) — the return-informed selector
> program the §6 edge-discarding read + the `03_V41_FORENSIC.md` analysis authorize. K **carries** from
> this family (≥6, not reset); inherits the still-pristine v4-FINAL_OOS one-shot. Honest prior: NULL is the
> most likely outcome (the V4.1 reference books 0.09–0.14 sit far below the 0.346 bar), and a null there
> permanently closes the v4 family.
>
> **`04` V4.4 DONE 2026-06-25 → NULL CLOSE → v4 family PERMANENTLY CLOSED (`04` §12).** 0/3 selectors clear
> §6.1: the candidate MOM *worked as a mechanism* (base Calmar 0.083 → **0.179**, per-trade expectancy +0.72%
> → +1.98% — the §6 edge-discarding diagnosis vindicated) but ~800% turnover keeps the costed Calmar at
> **0.39×** the Nifty 50 TRI bar (pessimistic ratio 0.39 < 1.0). RS≡MOM confirmed (§3 identity). ADV re-derived
> V4.1 exactly (parity OK). The §5 deployment diagnostic read **"deployment is a real lever"** (D_more Calmar
> 0.179→0.281, maxDD ≤ benchmark) — a *separate* pre-authorized future prereg, not acted on. **v4-FINAL_OOS
> NEVER touched (pristine across the entire v4 family); V4.5/V4.6 N/A; K≈12.**
