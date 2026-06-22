# v3 / 11 — Probationary Forward Paper-Trade of S3 (6-month live OOS before real capital)

> **Status: LOCKED (2026-06-21; rev.3 signed 2026-06-22) — §10 signed by Arafat; tolerances confirmed; §5e CA-reconciliation added & approved; P11.0 authorized.** Authorizes a
> 6-month forward **paper** trade of the byte-frozen `10` S3 candidate as a fresh, real-time OOS
> that accrues *after* the spent `FINAL_OOS`, before any real capital is risked. Written BEFORE
> the forward data exists (`00` §1 / `04` §5): the success bar, the kill bar, the frozen config,
> the fidelity rule, and the data/engine conventions are fixed now, so no later session moves the
> stick after seeing a live month.
>
> **This is an OPERATIONAL prereg, not a backtest prereg.** It does not re-open the strategy
> search. It commits to running the locked S3 forward, faithfully, and to a pre-agreed reading of
> what 6 paper months can and cannot earn.
>
> **rev.1 changes (Arafat review):** (§2) v2-native rewrite of the paper/alert engines is the
> preferred path — reuse v1 plumbing only where genuinely clean, never contort to fit v1; v1
> removal is a SEPARATE later refactor sprint, explicitly out of scope here. (§3e/§4) the
> close→next-open execution gap is now explicit: a persisted pending-fills queue mirrors the engine
> loop, so the next session's job fills what the prior session queued. (§5) the independent v2 data
> pipeline already exists (`app/data/bhavcopy/`) and is reused — never v1's yfinance path; the
> tested CA back-adjustment (`adjust.py`) is reused, with incremental-append correctness gated by a
> regression test.
>
> **rev.2 changes (Arafat review):** (§3e) the execute→stop ordering is promoted to a **named, tested
> HARD INVARIANT** (fill the prior queue at today's open BEFORE the same-day catastrophic-stop check —
> a fresh buy that craters on its fill day must be stop-eligible the same evening). (§4c) the live
> jobs **reuse v1's Celery + Redis + Beat infra** (`app/core/celery_app.py` / `app/tasks.py`) — one
> new task + one beat entry; no new scheduler. (§7.2) the operational gate is **relaxed for local-only
> running**: punctuality is replaced by *ordered replay completeness* — missed days are backfilled
> deterministically (EOD replay is fidelity-neutral for a paper book), so a missed day or two does
> NOT break the run and does NOT force early deployment.
>
> **rev.3 changes (Arafat review):** (§5e — NEW) a **corporate-action portfolio-state reconciliation**
> invariant is added. Back-adjustment anchors the *latest* date to factor 1.0 and rescales all prior
> history (`adjust.py` convention), so in a single-anchor backtest a split is invisible — but **live**
> the anchor moves daily, and a new CA retroactively rescales the stored price series while the
> *persisted* portfolio `cost_basis`/`shares` stay in the **old** anchor. Unreconciled, a clean 2:1
> split reads as a −50% crash and **falsely trips the daily catastrophic stop** (`engine.py:219`), and
> MTM equity halves silently. §5e requires rescaling held-position state by the CA factor ratio
> *before* the same-day stop check, gated by a regression test in P11.0. The monthly §2 parity check
> does **not** cover this (the stop is daily; a false stop can fire intra-month before parity runs).

---

## 0. Why this prereg exists — and the honest ceiling on what it can prove

`10` ended at **EXPLORATORY OOS PASS, DEFLATION-MARGINAL**: S3 beat the fair-costed Nifty200
Mom30 ~3× on Calmar at both cost levels out-of-sample (base 1.348 / pess 1.275, maxDD 13.1%),
held all four hard gates OOS — but reached the OOS via a disclosed §6.3 waiver (`10` §13) and its
deflated Sharpe is ≤ 0 at every K. The verdict ceiling is **"exploratory," never "validated."**
`FINAL_OOS` is now spent; a *statistical* re-validation needs a fresh multi-year OOS block that
does not yet exist.

This prereg opens the only honest path that does not require waiting years: **run S3 forward as a
paper book and let real, untouched months accrue as a live OOS** — before any real capital.

**What 6 forward months CANNOT do.** A monthly-rebalanced strategy yields ~6 monthly return
observations in 6 months. Six points cannot re-validate an edge statistically (Sharpe/Calmar on
n≈6 is noise). **This prereg does not, and may never be read to, "validate" S3.**

**What the forward phase DOES validate (its four real jobs):**

1. **Operational reliability** — daily and monthly jobs run, idempotently and resumably, every
   trading day; no missed catastrophic-stop check; alerts delivered.
2. **Fidelity** — the live engine's decisions are *byte-identical* to what `backtest_v2` would
   decide on the same dates (live book == shadow backtest; §2). This is the primary deliverable.
3. **Cost realism** — realized paper slippage/impact lands inside the base→pessimistic cost band
   modeled in `10`.
4. **Directional sanity** — the live book does not grossly break versus live Mom30 (a breakage
   detector, **not** an alpha certificate).

**Graduation earns _small real capital_, not "validated."** A clean 6-month run authorizes a
*probationary real-capital* allocation under a future prereg — it does not certify the alpha and
does not lift the `10` "exploratory" ceiling.

---

## 1. The frozen candidate (no knob moves — the v1 sin is forbidden)

The forward book trades **S3 exactly as locked in `10` R10.3**, byte-for-byte:

- `active_factors = [mom_12_1, low_vol, trend_quality, mom_6_1, reversal]` (equal-weight rank-blend),
- `target_positions N = 20`, `sell_rank_buffer M = 130`, `rank_smoothing_months = 0`,
  `rebalance_cadence = monthly`,
- `use_regime_overlay = True` (`risk_off_floor = 0.0`, `debounce_days = 3`, `dma_period = 200`),
- `catastrophic_stop_pct = 25.0`, `liquidity_floor_cr = 5.0`,
- **stable universe:** `universe_mode` stable, `size_U = 350`, `buffer_B = 1.25`, semi-annual review
  (Jan31/Jul31), top-U by 126-td median `adv_20`, B·U hysteresis, min-age via `min_periods`,
- **costs:** `CostConfig.base()` primary; `pessimistic()` tracked as a shadow.

❌ **No re-tuning during the forward run.** Every knob is **frozen**. A surprising live month is
**not** a tuning prompt — it is data. Touching any knob mid-probation voids the run (`00` §1).

---

## 2. Fidelity is the prime directive — wrap the v2 engine, do NOT reimplement

The whole point of a forward OOS is that the live book is *S3*, not a new untested engine that
merely resembles it. Therefore:

- **The strategy brain is the same `app.backtest_v2` code path.** The live "paper engine" is a thin
  shell: a point-in-time **data feeder** + **state persistence** + **order differ** + **paper
  executor** + **alerter**. Selection, ranking, regime fraction, catastrophic stop, and fill model
  are all delegated to `backtest_v2` (§3). We do **not** fork the logic.

- **Build the shell v2-native (preferred); reuse v1 plumbing only where it is genuinely clean.**
  The v1 paper/alert engines are signal-driven swing-trade code (pullback/ATR/`TechnicalSignal`)
  with the wrong paradigm for S3. **Do not contort the shell to fit v1.** Where a v1 utility is a
  clean drop-in — e.g. `alerts/email.py` (`send_alert_email`, HTML builders), the `AlertLog` dedup
  pattern — reuse it. Where it is not, **write the v2-native version** rather than bending S3 onto
  v1 abstractions. The `Paper*` ORM tables are replaced/extended via the §6 migration, not reused
  as-is.

- **v1 removal is OUT OF SCOPE here.** Deleting v1 and its components is a **separate later
  refactor sprint** — not part of this prereg, not done today. `11` neither depends on nor performs
  that removal; v1 may coexist untouched during the probation.

**Shadow-backtest parity is the fidelity test.** At each monthly rebalance, run the `backtest_v2`
engine over the full live history through the rebalance date and assert the live target portfolio
(holdings + weights) equals the engine's target portfolio for that date, within the §7 tolerance.
A parity break is an **engine bug**, never a signal — root-cause and fix before the run continues
(§8).

---

## 3. Engine conventions — LOCKED from `backtest_v2/engine.py` (resolves gotchas 3 & 4)

Read from the engine on 2026-06-21; the live shell MUST mirror each exactly:

**3a. Rebalance timing — last trading day of the month, close→next-open.**
`_rebalance_dates` returns the *last trading day* of each cadence period (monthly). The decision is
computed on that day's **close** (`engine.py` §5.v `build_rebalance_plan`), and fills are queued for
the **next session's open** (§5.i `_stamp_fills`). → **The live month-end job DECIDES on month-end
close and queues orders for the next-open fill (it does not, and cannot, fill on the same day — §3e).**

**3b. Regime overlay — evaluated daily, APPLIED ONLY at the monthly rebalance.**
`deployable_fraction(day)` is computed each day (§5.iv) but only enters `build_rebalance_plan`, which
runs solely on rebalance days (§5.v). The 200-DMA + 3-day-debounce state machine (`regime.py`) never
de-risks intra-month. → **The live DAILY job MUST NOT act on regime.** Only the month-end decision
reads the regime fraction, at the rebalance close.

**3c. Catastrophic stop — daily, close-based, 25% below cost basis, next-open fill.**
Each day (§5.iii): for every held name, if today's `close ≤ cost_basis × (1 − 25/100)`, **queue** a
**next-open** sell. → The live daily job mirrors it exactly, including next-open execution (§3e) and
the de-dup against a same-name rebalance sell (§5.v). **A position filled at today's open IS eligible
for the same-day stop check** (its `cost_basis` is set at step §3e.1, before the §3e.3 check) — this
is exactly why the execute-before-stop ordering is a hard invariant (§3e). The stop is
**close-confirmed, next-open executed** — matching the engine; we deliberately do **not** add an
intraday stop (it would diverge from `backtest_v2` and break fidelity).

**3d. Fill model — decision-at-close → next-open fill.**
Sells/trims execute before buys; buys are clamped to projected cash (`_clamp_buys_to_cash`); slippage
is applied as a price adjustment to the cost basis (`03` §1.3a); costs come from `costs.py`. → The
live paper executor replicates this fill model so paper fills match shadow-backtest fills.

**3e. The execution gap — a persisted pending-fills queue mirrors the engine loop (gotcha: live has
no next-open at decision time).** In the backtest the engine holds the whole price history, so a
rebalance/stop decision at day D's close is filled at day D+1's open inside the same loop (§5.i
applies the queue D+1 queued on D). **Live, the next-open price does not exist when the decision is
made.** The faithful equivalent is to **persist the pending-fills queue to the DB** and let the
*next* trading session's job apply it. Concretely, the daily post-close job runs the engine's
per-day loop order over a persisted queue:

```
DAILY POST-CLOSE JOB (mirrors engine.py per-day loop, queue persisted across runs):
  1. EXECUTE: apply any pending fills queued by the PRIOR session at TODAY's open
     (today's open is now available from today's bhavcopy)        ← engine §5.i
  2. MTM at today's close                                          ← engine §5.ii
  3. CATASTROPHIC-STOP check → queue next-open sells               ← engine §5.iii
  4. if month-end: REBALANCE plan (regime fraction at close)
        → queue next-open buys/sells/trims                        ← engine §5.v
  5. persist the updated pending-fills queue + portfolio state
```

> **⚠️ HARD ORDERING INVARIANT (named, tested, must never be reordered):**
> **EXECUTE queued fills (step 1) ALWAYS runs BEFORE the catastrophic-stop check (step 3).**
> *Rationale:* a position bought at today's open can crater 25% on that same day. The fill must
> establish the position (and its `cost_basis`) *first*, so the same-day close-based stop check can
> see it and queue the exit. Reverse the order and a fresh buy that collapses on its fill day would
> escape the stop until the *following* day — a silent divergence from `backtest_v2` (§5.i → §5.iii).
> This ordering matches the engine loop exactly and is enforced by a P11.1 regression test
> (seeded: buy at open, −25% close same day ⇒ stop queued that evening). It is not a convenience
> ordering; it is a correctness invariant.

Because a *paper* book reads EOD bhavcopy (today's open is in today's EOD file), a separate
intraday "morning execution" job buys nothing — it would need a live intraday quote feed we do not
have or want for paper. **A real-time morning execution job is therefore deferred to the future
real-capital prereg**, where filling at the actual live open matters. For the paper phase, the
single daily post-close job with a persisted queue is both the most faithful (it reproduces the
engine's §5.i fill ordering exactly) and the simplest design.

---

## 4. The jobs (operational design — interface locked, implementation in §11)

**4a. Daily post-close job (every trading day) — the §3e loop:**
1. Append today's bhavcopy OHLCV via the existing v2 pipeline (§5).
2. **Execute** the prior session's queued pending fills at today's open (with `costs.py`), persist.
3. MTM; **catastrophic-stop** check on held names → queue next-open sells (§3c).
4. Email alert on any stop trigger.
*No regime action. No new entries on non-month-end days.* (§3b/§3c.)

**4b. Month-end addendum (last trading day of the month) — runs inside the same post-close job:**
1. Run the `backtest_v2` engine over live history through today; read the regime fraction at close.
2. **Shadow-parity assert** (§2) — live target == engine target, else halt (§8).
3. Diff target vs current holdings → **queue** buy/sell/trim orders for next-open (§3a/§3e).
4. Email the rebalance preview (queued buys/sells/trims/weights, regime state). Actual fills land
   on the **next** session's post-close job (step 4a.2) and are confirmed by a fill email then.

Both jobs honor the Pipeline Laws: idempotent, resumable from `PipelineCheckpoint`, ISIN/`.NS`
discipline (§5), UTC storage / IST display, `classify_error` on failures, concurrency guard.

**4c. Scheduling & infra — REUSE v1's Celery + Redis + Beat (infra, not logic).** The existing
`app/core/celery_app.py` (Redis broker/backend, `timezone="Asia/Kolkata"`, `enable_utc=True`) and its
`beat_schedule` already run a weekday post-close cron (`crontab(day_of_week="1-5", hour=16, minute=5)`).
The live paper jobs are added as **one new `@celery_app.task`** (`app.tasks.execute_paper_daily_task`)
plus **one new beat entry** (weekday, just after bhavcopy publishes). **No new scheduler is built** —
reusing the queue/broker/scheduler is infra reuse, orthogonal to the v1-logic we discard (§2).

- **Month-end is detected from the trading calendar of the processed date** (`_rebalance_dates`,
  §3a), **not** from wall-clock "is today the last day" — so a replayed/backfilled run triggers the
  rebalance addendum on the correct historical date.
- **The daily task is date-parameterized and replays in order.** Its argument is the trading date to
  process (default: the latest unprocessed date). A multi-day gap is handled by processing each
  missed trading date in ascending order — each run is idempotent and reads/writes the persisted
  queue + portfolio state (§3e), so an ordered backfill reproduces continuous operation byte-for-byte
  (the basis for the relaxed §7.2 operational gate).

---

## 5. Data integrity — reuse the EXISTING v2 pipeline (gotchas 1 & 2 resolved)

**5a. The independent v2 data pipeline ALREADY EXISTS — reuse it, never v1.** `app/data/bhavcopy/`
is a self-contained, ISIN-keyed, idempotent + resumable pipeline: `build.build(start, end)` runs
**download → parse → CA → adjust → store** (`build.py`), with per-day checkpointing, weekend skips,
and `validate.py` acceptance checks. **Daily incremental append = `build(start=today, end=today)`**
(or last-stored → today). This is the v2-independent pipeline Arafat required; **v1's yfinance `.NS`
pipeline is NOT used anywhere in `11`.**

**5b. Corporate-action adjustment — reuse the tested `adjust.py`, gate the INCREMENTAL invocation.**
The CA back-adjustment Arafat referenced is `adjust.adjust_prices(raw_df, events)` (+ the
`corporate_actions.py` feed parser), already concrete and unit-tested. The real risk is **not** that
function — it is that back-adjustment is *retroactive*: a new split on day D rewrites the **entire
prior history's** adjusted series for that ISIN. A naive incremental append that re-adjusts only the
new row is therefore wrong on a CA ex-date. **Pre-reg gate (P11.0):** a regression test that injects
a split and asserts the *incremental* daily build reproduces (byte-for-byte) the adjusted series a
full-history rebuild would produce. Deterministic — Rule 5. This MUST pass before go-live.

**5c. ISIN ↔ `.NS` boundary (gotcha 2).** ISIN is the key everywhere in `backtest_v2` and in the
bhavcopy store. `.NS` symbols belong only to v1; they do not enter `11`. Any external symbol mapping
stays at the pipeline edge.

**5d. Consistency guard.** A daily reconciliation asserts the appended series reproduces yesterday's
adjusted closes byte-for-byte — except for ISINs with a logged corporate action that day. Any
unexplained retroactive drift halts the run (§8). (Leans on `validate.py` where it already covers this.)

**5e. Corporate-action portfolio-state reconciliation (HARD — resolves the moving-anchor / false-stop
gotcha).** Back-adjustment pins the **latest** date to `adj_factor = 1.0` and rescales **all earlier
dates** whenever a CA exists (`adjust.py` docstring; convention: latest → 1.0, earlier < 1.0). In a
backtest the whole series is adjusted **once** against a fixed anchor, so a split is **invisible** —
`cost_basis`, `shares`, and `close` all live in one frozen adjusted space and the catastrophic stop
(`engine.py:219`, `stop_level = cost_basis × 0.75`) stays comparable to today's `close`. **Live, the
anchor moves every day.** Per §5b the daily append re-adjusts the stored series to byte-match a full
rebuild, so a new CA on ex-date D **retroactively rescales the entire prior adjusted series** — but the
*persisted* portfolio's `cost_basis`/`shares` were recorded against the **old** anchor and are **not**
rescaled by the data pipeline. Two failures result, neither caught by the monthly §2 parity (the stop
is **daily**; a false stop can fire intra-month, before parity runs):

- **False catastrophic stop.** A name held at adjusted `cost_basis = 1000` that splits 2:1 now prints
  `close ≈ 500` (re-adjusted). `stop_level = 1000 × 0.75 = 750`; `500 ≤ 750` ⇒ the stop fires — a
  clean split reads as a −50% crash and silently exits a healthy position.
- **Wrong MTM/equity/weights.** `mark_to_market` (`portfolio.py:113`) values `shares × close_tr`;
  `close_tr` is also retroactively rescaled, so without rescaling `shares` the position value halves.

**Invariant (deterministic — Rule 5).** On each daily append, for every ISIN **held in the live book**
whose stored `adj_factor` changed vs. the prior series (a CA hit that day), compute the factor ratio
`r = new_factor / old_factor` and rescale the persisted position **before the §3e step-3 stop check**:

```
cost_basis *= r        # price space   (×0.5 for a 2:1 split)
shares     /= r        # share space   (×2)  → position value (shares × price) invariant
```

`last_price` (recomputed at MTM) and `target_weight` (scale-invariant) need no rescale. This puts the
live state back in the **same anchor** as the freshly-adjusted price series — reproducing what the
single-fixed-anchor backtest gets for free. The shadow backtest (§2) re-derives `cost_basis` from
scratch in the current anchor, so post-rescale the live `cost_basis` must equal the shadow's — making
this reconciliation a *precondition* of monthly parity, not a substitute for it.

**Pre-reg gate (P11.0).** A regression test that seeds a held position, injects a 2:1 split on day D,
and asserts: (a) **no** catastrophic stop fires from the split alone; (b) post-rescale
`shares × cost_basis` equals the pre-split value (position value invariant); (c) the reconciled live
`cost_basis` byte-matches what a from-scratch shadow backtest derives in the new anchor. MUST pass
before go-live. A held-name CA that cannot be cleanly reconciled **halts the run** (§8).

---

## 6. Schema migration (gotcha 5 — migrations are holy)

A new Alembic migration adds S3-style paper-position fields (rank, composite_score, target_weight,
cost_basis, shares, entry_date, days_held, regime_state_at_entry) and a **persisted pending-fills
queue** table (§3e) — augmenting/replacing the v1-only ATR/pullback/EMA21 columns. The position row
also persists the **last-seen `adj_factor`** per held ISIN so the §5e daily job can detect an anchor
change (`r = new_factor / old_factor`) and reconcile before the stop check. No direct DB manipulation;
idempotent; reversible.

---

## 7. Graduation criteria (locked BEFORE the first live month — the goalpost)

S3 graduates **exploratory → "small real-capital allocation authorized (under a future prereg)"**
iff, over **6 consecutive monthly rebalances**, ALL hold:

1. **Fidelity (HARD):** monthly shadow-parity holds every month — live holdings == engine holdings,
   per-name weight deviation attributable **only** to fill-price timing within tolerance
   **T = 25 bps** of book weight. A parity break is an engine bug: root-cause, fix, and the 6-month
   clock **resets** (the run must be 6 *clean* months). [CONFIRMED — Arafat 2026-06-21]
2. **Operational — REPLAY COMPLETENESS, not punctuality (HARD, but local-friendly):** every trading
   day in the window is eventually **processed in ascending order** (live or backfilled), with **no
   gap left unprocessed before the next month-end rebalance**. Wall-clock punctuality is **not**
   required: because the book is paper on EOD bhavcopy, an ordered backfill of missed days is
   *fidelity-neutral* — it fills at the correct historical opens and runs the stop checks against the
   correct closes, reproducing continuous operation byte-for-byte (§4c). So **missing a day or two is
   fine** as long as it is backfilled before the month-end decision that would depend on it; all
   alerts for processed days are delivered (late is acceptable for paper).
   - *Caveat (do not carry to real capital):* this affordance exists ONLY because paper fills can be
     replayed at past opens. **Real capital cannot time-travel** — the future real-capital prereg MUST
     reinstate strict punctuality or deployed infra. The relaxed gate is a paper-phase property, not a
     general one.
3. **Cost realism (HARD):** realized paper slippage/impact stays within the base→pessimistic band
   modeled in `10`.
4. **Directional sanity (SOFT — breakage detector, NOT an alpha claim):** the live book does not
   underperform live Nifty200 Mom30 by more than **margin Y = 15 pp** of cumulative return over the
   window. Catches gross breakage; does **not** certify edge.

**Anything short of 1–3 = research note / engine-fix loop, not graduation.** A clean run does **not**
relabel S3 "validated" (the `10` exploratory ceiling stands); it earns only the *right to consider*
small real capital under a separate, future prereg.

---

## 8. Kill criteria (abort the probation)

- **Persistent fidelity break** that cannot be root-caused → the live engine is not faithfully S3; stop.
- **Catastrophic-stop cascade** (≥ K=5 names stopped within one rebalance window) → halt, investigate.
- **Drawdown breach** beyond the OOS-observed 13.1% by margin **Z = 10 pp** (live maxDD > ~23%) →
  halt, investigate.
- **Data-integrity failure** (unexplained parquet drift, or a missed/mis-applied corporate action) →
  halt until fixed and re-reconciled.
- **Unreconciled held-name corporate action** — a CA on a currently-held ISIN whose §5e portfolio-state
  reconciliation cannot be cleanly applied (factor ratio missing/ambiguous, or post-rescale `cost_basis`
  diverges from the shadow backtest) → **halt before the daily stop check** until reconciled. (Safety
  interlock protecting the daily catastrophic stop from a false split-driven trigger; not a probation
  failure.)
- **Unbackfilled gap reaching a month-end** — if missed trading days are not replayed before a
  month-end rebalance, the rebalance MUST NOT run on incomplete history. **Block the rebalance and
  alert** until the gap is backfilled in order (§4c/§7.2). (Not a probation failure — a safety
  interlock that protects the relaxed operational gate.)

A kill halts execution and triggers a written post-mortem; it does **not** authorize re-tuning S3.

---

## 9. What this prereg does NOT do (guards)

- It does **not** re-tune S3, change the universe, or move any `10` knob (§1).
- It does **not** claim or permit statistical re-validation from 6 months (§0).
- It does **not** authorize real capital — only earns the right to *consider* small real capital
  under a future prereg after a clean run (§7).
- It does **not** touch `FINAL_OOS` (spent) or any backtest split.
- It does **not** fork the strategy logic — the brain stays `backtest_v2` (§2).
- It does **not** use v1's yfinance pipeline (§5), and it does **not** remove v1 — v1 removal is a
  separate later refactor sprint, out of scope here (§2).

---

## 10. Locked commitments (Arafat — sign to flip DRAFT → LOCKED)

Confirm or redline each before any code:

1. Candidate = **S3 frozen byte-for-byte** from `10` R10.3 (§1); no knob moves during the run.
2. Fidelity rule = **wrap `backtest_v2` as the brain**; build the shell **v2-native**, reuse v1
   plumbing only where clean, never contort to fit v1; **v1 removal deferred** to a later sprint (§2).
3. Engine conventions §3a–§3e locked from code (rebalance last-trading-day close→next-open via a
   **persisted pending-fills queue**; regime monthly-only; catastrophic stop daily; v2 fill model),
   including the **§3e HARD ORDERING INVARIANT** (execute queued fills BEFORE the same-day stop check),
   enforced by a P11.1 regression test.
4. Jobs as in §4 — a single daily post-close job mirroring the engine loop (execute prior queue →
   MTM → stop → month-end rebalance → queue), with a real-time morning executor deferred to the
   real-capital prereg; scheduled by **reusing v1's Celery + Redis + Beat infra** (one new task + one
   beat entry, §4c), month-end detected from the trading calendar of the processed date.
5. Data = **reuse the existing `app/data/bhavcopy/` v2 pipeline** (`build`, `adjust`, CA, `validate`),
   never v1; incremental-append back-adjustment correctness gated by a passing split-injection
   regression test before go-live (§5b); **§5e corporate-action portfolio-state reconciliation**
   (rescale held `cost_basis`/`shares` by the CA factor ratio before the daily stop check) gated by
   its own held-position regression test, with an unreconciled held-name CA halting the run (§8).
6. Alembic migration for S3 position fields + the pending-fills queue table (§6).
7. Graduation = §7 items 1–4 over **6 clean months** (where "clean operational" = **replay-complete,
   not zero-gap** — local running with backfilled gaps is allowed, §7.2); a parity break resets the
   clock; graduation earns only *small real capital under a future prereg*, never "validated."
8. Kill criteria = §8; a kill triggers a post-mortem, not a re-tune.
9. Tolerances **CONFIRMED (Arafat 2026-06-21):** **T = 25 bps** parity, **Y = 15 pp** sanity,
   **Z = 10 pp** DD-breach, **K = 5** stop-cascade, and the **clock-reset-on-parity-break** rule (§7.1).

> **Signed:** Arafat — date 2026-06-21  (DRAFT → LOCKED; P11.0 authorized)
> **rev.3 signed:** Arafat — date 2026-06-22  (§5e corporate-action portfolio-state reconciliation added: rescale held `cost_basis`/`shares` by the CA factor ratio before the daily stop check; P11.0 gate + §8 interlock; locked)

---

## 11. Execution stages (cold-session runnable — NO live trading until P11.1 signs off)

> Read this file + the one stage you are doing. Honor the token budget (Rule 6). Update Status, fill a
> Session log, check off Done-criteria. Do not mark Done if anything was skipped (Rule 12).

### P11.0 — data + schema foundation (reuse existing pipeline; no engine wiring, no live)
- **Do:** Alembic migration (§6). Operationalize **daily incremental append** on the existing
  `app/data/bhavcopy/build` (`build(today, today)`) + the §5d reconciliation guard. Write the
  split-injection regression test (§5b), the daily-reconciliation test, and the **§5e held-position
  CA-reconciliation regression test** (split on a held name ⇒ no false stop, value invariant,
  `cost_basis` matches shadow). Implement the §5e rescale (`cost_basis *= r`, `shares /= r`) applied
  before the §3e stop check.
- **Done-criteria:** migration up/down clean; incremental append reproduces a full-history rebuild
  byte-for-byte across an injected split (§5b); reconciliation test green; **§5e CA-reconciliation
  test green** (no false stop; position value invariant; reconciled `cost_basis` == shadow);
  mocked data only (no live NSE).

### P11.1 — live engine as a v2-wrapper + parity harness (dry-run, still no live capital)
- **Do:** build the v2-native shell (data feeder + state persistence + **persisted pending-fills
  queue** + order differ + paper executor + alerter) delegating to `backtest_v2`; register the
  `app.tasks.execute_paper_daily_task` Celery task + beat entry (§4c); build the monthly shadow-parity
  harness (§2). Dry-run on a **known historical month** and assert the live rebalance + next-session
  fill reproduces the backtest's rebalance for that date byte-for-byte.
- **Done-criteria:** historical dry-run parity == byte-identical (decision AND next-open fill); the
  **§3e ordering-invariant test passes** (seeded: buy at open, −25% close same day ⇒ stop queued that
  evening, fill-before-stop); daily 25%-stop path reproduces `engine.py` §5.iii; an **ordered backfill
  of an injected multi-day gap reproduces continuous operation byte-for-byte** (§7.2); alert emails
  render; idempotent/resumable.

### P11.2 — go live (paper), 6-month window
- **Do:** enable the daily post-close Celery job forward. Daily order (§3e): append → **execute prior
  queue at today's open** → MTM → stop-check → (month-end) rebalance → persist. Each month-end: parity
  assert → rebalance preview → next-session fill + confirm. **Missed days are backfilled in order
  before the next month-end** (§7.2); an unbackfilled gap reaching a month-end blocks the rebalance
  (§8). Log everything for the §7 verdict.
- **Done-criteria:** 6 consecutive **replay-complete** monthly rebalances (parity holds each month;
  clock resets on any break per §7.1); cost-realism + DD + cascade tracked against §7/§8 each month.

### P11.3 — end-of-window verdict
- **Do:** evaluate §7 (graduation) / §8 (kill). Write the verdict: graduate (→ future real-capital
  prereg) or research-note/engine-fix loop.
- **Done-criteria:** written verdict against §7/§8; explicit statement that S3 remains "exploratory"
  (the `10` ceiling is not lifted by paper months).

---

## Exit criteria
- [x] §10 locked by Arafat (DRAFT → LOCKED) — 2026-06-21.
- [ ] P11.0 — migration + daily incremental append on the existing bhavcopy pipeline + regression/reconciliation tests green.
- [ ] P11.1 — v2-native wrapper + persisted queue + parity harness; historical dry-run reproduces backtest (decision + fill) byte-for-byte.
- [ ] P11.2 — 6 consecutive clean monthly paper rebalances.
- [ ] P11.3 — verdict against §7/§8; "exploratory" ceiling restated.
