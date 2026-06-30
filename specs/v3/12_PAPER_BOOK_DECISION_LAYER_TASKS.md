# v3 / 12 — S3 Paper Book: Decision Layer & Ops Observability — EXECUTION TASKS

> **Status: LOCKED (2026-06-29). NOT yet executed.** Spec-now / execute-later. Six
> independent features (F1–F6), each implementable in its **own cold session**. Read §0–§2
> first (shared context), then jump to the one feature section you are executing. Each
> feature section is self-contained: goal, backend, frontend, migration (if any),
> done-criteria, cold-start pointers.
>
> This is a **build-tasks doc subordinate to the LOCKED `11_PROBATIONARY_DEPLOY_PREREG.md`**
> and a sibling of `11_PAPER_BOOK_VIZ_TASKS.md` (COMPLETE). It is **pure observability**:
> persist/aggregate state the engine already computes, expose it read-only, render it. It
> does **NOT** re-open the strategy search, change any decision/fill logic, touch
> `backtest_v2` engine behaviour, move any `10` knob, or touch `FINAL_OOS`.

---

## 0. Why this exists

`S3PaperBook.jsx` (slices 1+2, through V11.7) renders book header, holdings, the NAV curve
(go-live divider + Mom30 overlay + exposure band), parity badge, rebalance log, and a
probation progress/staleness widget. The data **accrues** — but the page does not yet turn
that data into the **decision** the probation exists to make.

The probation's whole purpose (`11` §0, §7) is narrow and pre-registered: validate
**fidelity, operations, and cost** over 6 clean months, then earn the *right to consider*
small real capital under a future prereg. It does **not** and cannot validate the edge from
6 monthly points (`11` §0). These six features make the three pillars — and the go/no-go
verdict against the **locked** graduation/kill gates — **visible and auto-evaluated**, so the
month-6 decision is honest and the goalposts cannot move after seeing data.

**Arafat's request (2026-06-29):** document features #1, #3, #4, #5, #6, #7 from the
brainstorm for independent cold-session implementation. (Brainstorm #2 — per-name parity
breach timeline — was de-scoped.)

| This doc | Brainstorm # | Feature | Pillar | New table? |
|----------|-------------|---------|--------|-----------|
| **F1** | #1 | Cumulative tracking-error tile + sparkline | Fidelity | No | ✅ DONE 2026-06-30 |
| **F2** | #3 | Realized-vs-modeled cost ledger | Cost | No | ✅ DONE 2026-06-29 |
| **F3** | #4 | Turnover-to-date vs backtest expectation | Cost/Fidelity | No | ✅ DONE 2026-06-30 |
| **F4** | #5 | Pipeline heartbeat / run-history strip | Ops | **Yes** | ✅ DONE 2026-06-30 |
| **F5** | #6 | Alert log surfaced in-UI | Ops | **Yes** |
| **F6** | #7 | Probation scorecard / countdown | Decision | No |

Suggested execution order: **F1 → F2 → F3 → F4 → F5 → F6** (F6 reads F1+F4 outputs; the
rest are independent). Each can ship alone.

---

## 1. Hard rules inherited (read before any feature)

1. **Read-only endpoints. No live price fetch.** Project law + `11` §1 + the router
   docstring: every figure derives from **already-persisted state**. Never hit live
   NSE/yfinance. New GET endpoints only (F4/F5 may add tables, never live I/O).
2. **The gates are PRE-REGISTERED — do not invent thresholds.** F6 (and any pass/fail
   colouring in F1–F3) MUST cite the locked values in `11` §7 (graduation) and §8 (kill).
   Quoted verbatim in §2.3 below. **Surfacing data ≠ re-deciding the bar.** If a threshold
   you need is *not* in `11`, STOP and ask Arafat — do not define "pass" yourself (this is
   the exact post-hoc-goalpost failure mode the program's K/DSR discipline guards against).
3. **Pillars are not the edge.** Label everything honestly. Tracking error (F1) and turnover
   (F3) are **fidelity** measures, not alpha. Directional sanity (F6 gate 4) is a *breakage
   detector*, explicitly **not** an alpha claim (`11` §7.4). Never let the UI imply 6 months
   validated S3.
4. **Paper-fill caveat (matters for F2/F3).** Paper fills replay at **historical opens**, so
   the book has **no real market impact** and its "slippage" is *timing* slippage
   (next-open vs decision-close), not impact. Realized paper cost therefore **understates**
   real-world cost — same affordance as the relaxed operational gate (`11` §7.2 caveat).
   F2/F3 MUST state this caveat in the UI; passing the cost gate on paper is necessary, not
   sufficient, for real capital.
5. **Project law unchanged:** `.NS` suffix; UTC storage / IST display
   (`datetime.now(datetime.timezone.utc)`, display via `Asia/Kolkata`); Pydantic in+out;
   migrations are holy (Alembic autogenerate, review, up→down→up); idempotency; tests mock
   external APIs; regression-first. Frontend: `lodash/fp` transforms, dumb components,
   Tailwind palette, immediate UX feedback.

---

## 2. Shared context (what already exists — read once, applies to all features)

### 2.1 Backend surface (`backend/app/routers/paper_v2.py`, ~455 lines)

Existing read-only endpoints + their Pydantic responses (all defined inline in this router):

| Endpoint | Response model | Gives you |
|----------|---------------|-----------|
| `GET /book` | `PaperV2BookResponse` | nav, cash, total_return_pct, n_positions |
| `GET /positions` | `list[PaperV2PositionResponse]` | per-name cost_basis, weight_pct, unrealized_pct |
| `GET /nav` | `NavSeriesResponse` | go-live divider + `NavPointResponse[]` (date, equity, exposure, index_level, index_rebased, is_forward) |
| `GET /parity` | `ParitySeriesResponse` | `latest` + `history[]` of `ParityCheckResponse` (as_of, passed, max_dev_bps, tol_bps, breaches) |
| `GET /rebalances` | `list[RebalanceEventResponse]` | per decision_date: deployable_fraction, n_buys/sells/trims, total_cost_rupees, `fills[]` |
| `GET /pipeline/status` | `PaperPipelineStatusResponse` | status (running/idle/never_run), last_processed_date, go_live_date |
| `POST /pipeline/run` | dict (202) | manual trigger (Redis-locked; 409 if running) |

`RebalanceFillResponse` (per fill) already carries: `symbol, isin, side, qty, holding_before,
reason, status, decision_price, fill_date, fill_price, cost_rupees`. **This is the raw
material for F2 (realized slippage = `fill_price` vs `decision_price`; realized cost =
`cost_rupees`) and F3 (turnover = Σ|qty·fill_price| / NAV).**

### 2.2 Persisted tables (`backend/app/db/models.py`, PaperV2* near L490–579)

- `paper_v2_portfolio` — the book (`created_at` = go-live anchor in IST; `last_processed_date`).
- `paper_v2_position` — open holdings (incl. last-seen `adj_factor`, cost_basis, shares).
- `paper_v2_pending_fills` — every fill (decision_price, fill_price, cost_rupees, reason …).
- `paper_v2_daily_snapshot` — **one row per processed day**: equity, cash, invested_value,
  exposure, n_positions, index_level (Mom30 TRI), is_forward. (Added V11.1.)
- `paper_v2_parity_check` — one row per monthly parity run: as_of, passed, max_dev_bps,
  tol_bps (25.0), breaches JSON. (Added V11.1.)

Current Alembic head at spec time: **`c1e9a4f7b2d6`**. F4/F5 add tables — **always run
`backend/venv/bin/alembic heads` to get the *real* current head before autogenerating**, since
earlier features may have advanced it.

### 2.3 The LOCKED gates (verbatim from `11`; F6 evaluates these — never edit them)

**Graduation (`11` §7) — ALL must hold over 6 *consecutive clean* monthly rebalances:**
1. **Fidelity (HARD):** monthly parity holds every month, per-name weight dev ≤ **T = 25 bps**
   attributable only to fill timing. **A parity break resets the 6-month clock** — the run
   must be 6 *clean* months. (So F6's denominator is "clean months since last reset", not
   naive elapsed months.)
2. **Operational (HARD, local-friendly):** every trading day eventually processed in
   ascending order, **no gap left unprocessed before the next month-end rebalance**.
   Wall-clock punctuality NOT required (paper backfill is fidelity-neutral). Missing a day
   or two is fine if backfilled before the month-end that depends on it.
3. **Cost realism (HARD):** realized paper slippage/impact stays within the
   **base → pessimistic** cost band modeled in `10`.
4. **Directional sanity (SOFT — breakage detector, NOT alpha):** live book does not
   underperform live Nifty200 Mom30 by more than **Y = 15 pp** cumulative return over window.

**Kill (`11` §8) — any aborts the probation (→ post-mortem, NOT re-tune):**
- Persistent un-root-causable fidelity break.
- Catastrophic-stop cascade: **≥ K = 5 names stopped within one rebalance window**.
- Drawdown breach: live maxDD beyond OOS 13.1% by **Z = 10 pp** → **live maxDD > ~23.1%**.
- Data-integrity failure (parquet drift, missed/mis-applied CA).
- Unreconciled held-name corporate action (safety interlock).
- Unbackfilled gap reaching a month-end (safety interlock; not itself a failure).

### 2.4 Cost model constants (`backend/app/backtest_v2/costs.py`) — for F2/F3

`CostConfig` factory levels (decimal, not %):
- **base** (production default): `base_slippage_pct=0.0015` (0.15%/side), `impact_coeff=0.15`.
- **pessimistic** (stress / upper band): `base_slippage_pct=0.003` (0.30%/side),
  `impact_coeff=0.30`.
- Statutory (both levels): STT 0.1% (buy+sell), exchange_txn 0.00297%, SEBI 0.0001%,
  stamp 0.015% (buy only), GST 18% on (exchange+SEBI), `participation_cap=0.10`.

The **modeled band** F2 compares against = total round-trip cost as %/yr implied by `base`
(lower edge) and `pessimistic` (upper edge). Reuse `costs.py` to compute it; do not
re-derive the formula. The realized side comes from `paper_v2_pending_fills.cost_rupees`
plus timing slippage `(fill_price − decision_price)/decision_price`.

### 2.5 Frontend surface

- Page: `frontend/src/pages/S3PaperBook.jsx` (~1430 lines). Sections are plain components
  (`StatCard`, `HoldingsTable`, NAV chart, parity badge, rebalance log, probation progress).
  Match the existing card idiom: `text-lg font-black ... uppercase tracking-tight` headings,
  Tailwind palette tokens (`text`, `border`, etc.), recharts for series.
- API client: `frontend/src/api/client.js` — add a fetch fn per new endpoint here; keep the
  naming/shape of existing paper-v2 client fns.
- Data transforms: `lodash/fp` only (project law §3). Components stay dumb; any aggregation
  that can live in the backend SHOULD (project law §3 / Rule 5).

### 2.6 Per-feature done-criteria (apply to ALL F1–F6)

- New endpoint(s) read-only, Pydantic in+out, derive only from persisted state.
- `pytest` regression tests, external APIs mocked (project law §5 / Rule 9): a test that
  encodes WHY (e.g. "tracking error must exclude warm-start days", "clock resets on a parity
  break"), not just shape.
- Migrations (F4/F5) up→down→up clean; idempotent.
- `cd frontend && npm run build` green.
- Honesty labels per §1.3/§1.4 present in the UI.
- Update `MEMORY.md` pointer if the feature changes a documented behaviour. Do NOT mark Done
  if anything was skipped (Rule 12).

---

## F1 — Cumulative tracking-error tile + sparkline  (brainstorm #1)

**Goal.** One headline number a deploy committee asks for first: *how far has the live book
drifted from the frozen shadow since go-live?* Render it as a StatCard with a sparkline.

**What to compute.** Tracking error = the standard deviation of the **daily return
difference** between the live book NAV and the shadow. Two honest options — pick per §1.2,
prefer (a):
- **(a) Live-vs-shadow (true TE), if a shadow NAV series is available.** The monthly parity
  check (`paper_v2_parity_check`) re-derives the shadow but stores only weight deviations,
  not a daily shadow NAV. If a daily shadow NAV is NOT persisted, do **not** fabricate one;
  fall back to (b) and note the limitation, OR (separate decision with Arafat) extend the
  parity/snapshot job to persist a daily shadow equity. **Do not add live recompute in the
  endpoint** (read-only law).
- **(b) Book-vs-benchmark TE (always available now).** std of daily (book return − Mom30
  return) from `paper_v2_daily_snapshot` (`equity` and `index_level`). This is the
  *benchmark* tracking error, not fidelity TE — label it precisely as "vs Mom30", and keep
  it visually distinct from the §2.3 fidelity gate (which is parity-bps, not TE).

Annualize: `TE_daily × sqrt(252)`. Restrict the window to **forward days only**
(`is_forward = True`) for the headline; the warm-start replay is backtest, not live (NAV
curve already uses the go-live divider for the same reason).

**Backend.** New `GET /tracking-error` → `TrackingErrorResponse { annualized_te_pct: float,
n_days: int, basis: "shadow" | "mom30", series: list[{date, cum_diff_pct}] }`. `series` is
the cumulative return-difference path for the sparkline. Aggregate in SQL/Python over
snapshots; no new table.

**Frontend.** A `StatCard` (TE %, with `basis` in the sub-label) + a small recharts
sparkline of `cum_diff_pct`. Place near the NAV curve. Tooltip: "Fidelity/benchmark drift —
NOT an alpha measure; 6 forward points cannot validate edge (`11` §0)."

**Done-criteria (+ §2.6).** Test: TE excludes warm-start days; TE is 0 when book return ==
benchmark return every day; correct annualization factor. Basis label matches the data
source actually used.

**Execution notes (2026-06-30):**
- No shadow NAV is persisted → option (b) chosen: basis = "mom30" (benchmark tracking error).
  `import math` added to router imports.
- `GET /v2/paper/tracking-error` → `TrackingErrorResponse { annualized_te_pct, n_days,
  basis: "mom30", series: list[TEDiffPoint{date, cum_diff_pct}] }` added inline in
  `paper_v2.py`. Filters `is_forward=True` + `index_level IS NOT NULL`; uses sample std ×
  sqrt(252) × 100 for annualization; anchors cumulative series at 0.0 on the first forward
  day. Handles < 2 rows gracefully (returns 0.0 TE, no series error).
- `getPaperV2TrackingError` added to `frontend/src/api/client.js`.
- `TrackingErrorCard` component with inline sparkline (`LineChart` from the lazy-loaded
  recharts bundle) added to `S3PaperBook.jsx` between `DrawdownCurve` and
  `ConcentrationPanel`. Mandatory honesty label (§1.3/§1.4) present: "Fidelity/benchmark
  drift — NOT an alpha measure; 6 forward months cannot validate the strategy's edge."
- 8 tests in `tests/paper_v2/test_tracking_error.py`; all 107 paper_v2 tests pass;
  `npm run build` green.

---

## F2 — Realized-vs-modeled cost ledger  (brainstorm #3)  ✅ DONE 2026-06-29

**Goal.** The cost pillar (`11` §7.3) is the one most likely to kill the edge and is the
least visible today. Show modeled cost band vs paper-realized cost, cumulative, in bps —
flagged red if realized exceeds the modeled band.

**What to compute.**
- **Realized:** sum `cost_rupees` over all fills (statutory) + timing-slippage cost per fill
  = `|fill_price − decision_price| × qty` (the next-open-vs-decision-close drift). Express
  cumulative realized cost as **bps of traded notional** and as **drag in %/yr** of NAV
  (annualize by elapsed forward days). Group by rebalance event for a per-event ledger row
  and a running total.
- **Modeled band:** from `costs.py` `base` (lower) and `pessimistic` (upper) — the same
  band `11` §7.3 names. Compute the modeled round-trip cost on the *same* fills (reuse
  `fill_cost`/`effective_price`; do not hand-roll). The gate is: realized **within
  base→pessimistic**.

**Backend.** New `GET /cost-ledger` → `CostLedgerResponse { realized_bps_total: float,
realized_drag_pct_yr: float, modeled_base_bps: float, modeled_pessimistic_bps: float,
within_band: bool, rows: list[{decision_date, reason, traded_notional, realized_cost_rupees,
realized_bps, modeled_base_bps, modeled_pess_bps}] }`. Read-only over `paper_v2_pending_fills`
+ `paper_v2_daily_snapshot` (for NAV/annualization).

**Frontend.** A ledger card: headline "realized X bps vs modeled [base..pess] band" with a
band gauge (green inside, red above), and an expandable per-rebalance table. **Caveat banner
(§1.4):** "Paper fills replay at historical opens — no real market impact. Realized cost
here is statutory + timing slippage only; real-world cost will be higher. Passing is
necessary, not sufficient, for real capital."

**Done-criteria (+ §2.6).** Test: realized cost reconciles to Σ`cost_rupees` + slippage on
a seeded fill set; `within_band` flips correctly at the pessimistic edge; annualization uses
forward elapsed days. Reuses `costs.py` (no duplicated cost formula — Rule 5).

**Execution notes (2026-06-29):**
- `GET /v2/paper/cost-ledger` added to `paper_v2.py`; `_compute_modeled_cost` helper
  delegates to `costs.py` `fill_cost` + `effective_price` (Rule 5 — no re-derived formula).
- `CostLedgerRowResponse` + `CostLedgerResponse` Pydantic models inline in the router.
- Realized = Σ `cost_rupees` (statutory) + `|fill_price − decision_price| × qty` (timing
  slippage) over **filled** fills only; pending fills excluded.
- Modeled band: `CostConfig.base()` (lower) → `CostConfig.pessimistic()` (upper), reusing
  `fill_cost` + `effective_price` at `adv_20=0` (no stored ADV for paper fills → floor
  slippage only).
- Annualisation by `n_forward_days` (count of `is_forward=True` snapshots); `avg_nav` from
  forward snapshot equity values.
- `getPaperV2CostLedger` added to `frontend/src/api/client.js`; `CostLedgerCard` +
  `BandGauge` components added to `S3PaperBook.jsx` below `CostDragPanel`. Mandatory
  caveat banner (§1.4) present in the UI.
- 9 tests in `tests/paper_v2/test_cost_ledger.py`; all 70 paper_v2 tests pass; `npm run build` green.

---

## F3 — Turnover-to-date vs backtest expectation  (brainstorm #4)

**Goal.** Every prior strategy family in this program died on a **turnover wall** (see
memory: v4 ~800–2660%, v2 ~934% churn-dominant). A live "turnover run-rate vs expected"
gauge catches immediately if the live book churns more than the frozen S3 predicts — which
would mean either a fidelity break or a cost-gate risk.

**What to compute.**
- **Live turnover:** annualized two-way turnover = Σ over forward fills of
  `|qty · fill_price|` / average NAV, annualized by forward elapsed days. (Two-way = buys +
  sells; state the convention in the UI to avoid the classic 1×/2× ambiguity.)
- **Expected turnover:** S3's backtest turnover from `10` (monthly-rebalanced, stable
  universe). **This number must come from `10`/the frozen shadow, not be invented** (§1.2).
  If it is not recorded in a `10` artifact, STOP and ask Arafat where the canonical S3
  turnover figure lives; do not guess. Acceptable interim: compute it from the shadow
  backtest over the same window via existing `backtest_v2` machinery in a **one-off
  offline** step and store it as a documented constant in `s3_config.py` (a frozen expected
  value, clearly commented with provenance) — NOT recomputed live in the endpoint.

**Backend.** New `GET /turnover` → `TurnoverResponse { live_annualized_pct: float,
expected_pct: float, ratio: float, basis: "two-way", n_forward_days: int }`. Read-only over
fills + snapshots + the frozen expected constant.

**Frontend.** A gauge/StatCard: live vs expected, ratio badge (green ≈1.0, amber drift, red
if materially above — exact colour thresholds are presentational, NOT a pre-reg gate;
keep them visibly distinct from the §2.3 hard gates so nobody mistakes a UI colour for a
graduation criterion). Sub-label: "two-way, annualized; fidelity check, not a gate."

**Done-criteria (+ §2.6).** Test: live turnover matches Σ|notional|/NAV on a seeded fill
set; basis convention asserted; expected value sourced from a documented constant, not a
literal in the endpoint.

**Execution notes (2026-06-30):**
- `S3_EXPECTED_TURNOVER_TWO_WAY_PCT = 581.0` added to `app/paper_v2/s3_config.py` with
  full provenance comment (FINAL_OOS R10.3, `10` §R10.3 table, base cost). Frozen
  documented constant — not recomputed live (Rule 5).
- `GET /v2/paper/turnover` → `TurnoverResponse` added inline in `paper_v2.py`. Imports
  `S3_EXPECTED_TURNOVER_TWO_WAY_PCT` from `s3_config` (no literal). Forward fills only:
  `decision_date >= go_live_date` + `status="filled"` (warm-start replay excluded, pending
  excluded). Annualisation via `is_forward=True` snapshot count (same denominator as F2).
- `getPaperV2Turnover` added to `frontend/src/api/client.js`; `TurnoverCard` component
  with gauge bar + ratio badge added to `S3PaperBook.jsx` below `CostLedgerCard`. Honesty
  label (§3) present: "Fidelity check, not a gate. Colour thresholds are UI-only and do
  NOT represent pre-registered criteria."
- 9 tests in `tests/paper_v2/test_turnover.py`; all 79 paper_v2 tests pass; `npm run
  build` green.

---

## F4 — Pipeline heartbeat / run-history strip  (brainstorm #5)  — **NEW TABLE** ✅ DONE 2026-06-30

**Goal.** Operator confidence in a 6-month unattended run comes from *seeing the streak*
(✓✓✗✓ …), not from the absence of a watchdog email. Today `/pipeline/status` only reports
the *current* Redis-lock state + `last_processed_date`; there is **no per-run history**
(`PipelineRun` is the research pipeline, not the paper job). Persist each paper-job run and
render a heartbeat strip. This also feeds F6's operational gate.

**Migration (table).** `paper_v2_run`:
- `id` PK; `portfolio_id` FK → `paper_v2_portfolio.id`.
- `started_at` / `finished_at` `DateTime(timezone=True)` (UTC).
- `trigger` str — `"beat" | "manual" | "backfill"`.
- `status` str — `"success" | "failed" | "noop"` (noop = nothing to process, e.g. go-live
  idle day — see `11` §P11.2 session log).
- `days_processed` int; `first_date` / `last_date` Date (the ordered span replayed).
- `error_class` str | None (via `classify_error` — project law §1); `error_msg` str | None.
- Indexed on `(portfolio_id, started_at)`. Idempotent insert per run.

Verify the real head first (`alembic heads`), autogenerate, review, up→down→up.

**Task instrumentation.** In `app/tasks.py` `execute_paper_daily_task` (the
`s3-paper-daily-postclose` beat job), wrap the run to insert a `paper_v2_run` row capturing
outcome. Use `classify_error` on failure (project law §1). Do **not** change decision/fill
logic — only record outcome around it. Keep idempotent: a re-run of the same day records a
new run row but must not double-process (engine is already idempotent).

**Backend.** New `GET /runs?limit=N` → `list[PaperRunResponse]` (most recent first), and
extend (or add) a summary the heartbeat needs: last N outcomes, current streak of clean
days, last failure. Keep `/pipeline/status` as-is (Redis live state) — `/runs` is history.

**Frontend.** A horizontal heartbeat strip (last ~30 runs as ✓/✗/◦ chips with hover =
date + days_processed + error) above or beside the existing pipeline-status widget. Failures
expand to show `error_class`/`error_msg`.

**Done-criteria (+ §2.6).** Migration up/down clean. Test: a simulated successful run
records `status=success` + correct span; a simulated failure records `failed` +
`error_class` from `classify_error`; a no-op idle day records `noop`. Heartbeat summary
(streak) computed correctly. The beat task still processes days identically (no behavioural
change — assert engine output unchanged around the instrumentation).

**Execution notes (2026-06-30):**
- Migration `1b67f5d050b2` (down_revision `0a1f85aef724`); up→down→up clean. Unrelated
  autogenerate drift (`ix_sr_slug_date` drop + `technical_signals` alter) trimmed from the
  migration — F4 only adds `paper_v2_run`.
- `PaperV2Run` model added to `models.py` after `PaperV2Alert` with full index on
  `(portfolio_id, started_at)`.
- `execute_paper_daily_task` gains `trigger: str = "beat"` param. Outer-scope state vars
  (`_run_status`, `_days_processed`, `_first_date`, `_last_date`, `_error_class`,
  `_error_msg`, `_portfolio_id`) are updated as the task progresses; `finally` block calls
  `_persist_paper_run` which uses a **fresh** `SessionLocal()` so a dirty main session
  (post-parity-halt rollback) cannot prevent the run record.
- `run_paper_pipeline` router endpoint updated to pass `trigger="manual"`.
- `classify_error` imported at the top of `tasks.py` (project law §1).
- `GET /v2/paper/runs?limit=N` → `list[PaperRunResponse]` added to `paper_v2.py`; scoped
  to active `portfolio_id`, ordered `started_at DESC`. `PaperV2Run` imported into router.
- `getPaperV2Runs` added to `frontend/src/api/client.js`; `HeartbeatStrip` component with
  chip strip (✓/✗/◦), hover detail, streak counter, and last-failure summary added to
  `S3PaperBook.jsx` above `AlertFeedCard`. Concurrent-guard note present in footer.
- 10 tests in `tests/paper_v2/test_run_history.py`; all 99 paper_v2 tests pass;
  `npm run build` green.

---

## F5 — Alert log surfaced in-UI  (brainstorm #6)  — **NEW TABLE** ✅ DONE 2026-06-29

**Goal.** The alerter (`app/paper_v2/alerter.py`) emails stop / rebalance-preview /
fill-confirm / pipeline-failure notices into the void (Resend) and discards them. The paper
trail should live **with the book**. Persist each emitted alert and show a queryable feed.

**Migration (table).** `paper_v2_alert`:
- `id` PK; `portfolio_id` FK → `paper_v2_portfolio.id`.
- `created_at` `DateTime(timezone=True)` (UTC).
- `kind` str — `"stop" | "rebalance_preview" | "fill_confirm" | "pipeline_failure" |
  "staleness"` (cover both `alerter.py` and `watchdog.py` emitters).
- `as_of` Date | None (the process/decision date the alert pertains to).
- `subject` str; `body_summary` str (short text, NOT the full HTML — keep rows light);
  `delivered` bool (True if `send=True` path actually called Resend; False for the
  build-only `send=False` path used by tests).
- Indexed on `(portfolio_id, created_at)`. Idempotent.

**Instrumentation.** In `alerter.emit_alerts` / `emit_failure_alert` and `watchdog.run_watchdog`,
after building each alert, persist a `paper_v2_alert` row. **Reuse the existing
`send=False`/`send=True` discipline** so tests still render-without-I/O (project law §5):
persist on both paths, set `delivered` from the `send` flag. Do not change what gets emailed
or when.

**Backend.** New `GET /alerts?limit=N&kind=` → `list[PaperAlertResponse]` (most recent
first, optional kind filter). Read-only.

**Frontend.** An alert-feed card (timeline list, kind-coloured chips, `as_of` + subject +
summary, "delivered" indicator). Place near the rebalance log. Filter by kind.

**Done-criteria (+ §2.6).** Migration up/down clean. Test: each alert kind persists a row
with correct `kind`/`as_of`/`delivered`; `send=False` path persists with `delivered=False`
and performs no network I/O (Resend mocked/asserted-not-called); endpoint filters by kind.
No change to email content/timing.

**Execution notes (2026-06-29):**
- Migration `0a1f85aef724` (down_revision `c1e9a4f7b2d6`); up→down→up clean.
- `alerter.emit_alerts` / `emit_failure_alert` gained `session=` kwarg; `tasks.py`
  passes `session=db` to both. `watchdog.run_watchdog` restructured to persist inside
  the try block (before session close) via `_persist_staleness_alert` helper.
- `_persist_alert` in alerter resolves `portfolio_id` from `PaperV2Portfolio.is_active`
  (same as `_active_book` in the router) — callers don't need to pass the ID.
- `GET /v2/paper/alerts?limit=N&kind=` added to `paper_v2.py`; `getPaperV2Alerts` added
  to `frontend/src/api/client.js`; `AlertFeedCard` component with kind-filter chips added
  to `S3PaperBook.jsx` below the RebalanceLog.
- 15 new tests in `tests/paper_v2/test_alert_log.py`; all 61 paper_v2 tests pass; `npm
  run build` green.

---

## F6 — Probation scorecard / countdown  (brainstorm #7)  — depends on F1, F4

**Goal.** The single panel that converts "data accruing" into "a decision being made":
days/months elapsed of the 6-month window **and** live pass/fail against the **locked** `11`
§7 graduation gates + §8 kill criteria. Given how many families died here, the verdict
criteria must be visible and **auto-evaluated** so nobody moves goalposts post-hoc.

**Hard constraint (§1.2).** Every threshold is quoted in §2.3 from `11` §7/§8 — use those
**verbatim**. If a gate cannot be evaluated yet from persisted data, render it
**"insufficient data"**, never a guess. Do NOT add or relax a gate.

**What to evaluate (read-only aggregation; no new table):**
1. **Window progress.** Calendar months since `go_live` (book `created_at`, IST) vs 6. BUT
   the graduation denominator is **6 *clean* months** — the fidelity clock **resets on a
   parity break** (`11` §7.1). Show "clean monthly rebalances passed: k / 6" computed from
   `paper_v2_parity_check`: count consecutive passing months from the **last** failing
   `as_of` (exclusive). A fail anywhere = clock reset; show the reset date.
2. **Gate 1 Fidelity (HARD):** every monthly parity `passed` and `max_dev_bps ≤ 25`. Status
   from `paper_v2_parity_check`.
3. **Gate 2 Operational (HARD):** every trading day processed in ascending order, no gap
   left unprocessed before a month-end. Derive from F4's `paper_v2_run` history +
   `last_processed_date` vs expected trading calendar. If F4 not yet shipped, render
   "insufficient data" and note the dependency.
4. **Gate 3 Cost realism (HARD):** realized within base→pessimistic band — reuse F2's
   computation (`within_band`). If F2 not shipped, "insufficient data".
5. **Gate 4 Directional sanity (SOFT):** book cumulative return not below Mom30 by > 15 pp
   over window. From `paper_v2_daily_snapshot` (`equity` vs `index_rebased`). Label SOFT /
   "breakage detector, NOT alpha" (`11` §7.4).
6. **Kill watch (§8):** show live status of each kill trigger where derivable —
   catastrophic-stop count within current window (≥5 = kill) from fills with
   `reason="catastrophic_stop"`; live maxDD vs ~23.1% from the snapshot equity curve; flag
   data-integrity / CA / gap interlocks if F4/F5 surface them. A tripped kill criterion
   renders a loud **HALT** state.

**Backend.** New `GET /scorecard` → `ScorecardResponse` with: `go_live`, `months_elapsed`,
`clean_months_passed`, `clock_reset_at: date | None`, a list of `gates` (each:
`id, label, severity: "hard"|"soft", status: "pass"|"fail"|"insufficient_data", detail,
source`), and `kill_watch` (each criterion: `label, value, threshold, tripped`). Pure
aggregation over existing tables (+ F1/F2/F4 outputs).

**Frontend.** A scorecard panel at the top of the page: 6-month progress ring (clean months,
with reset annotation if any), a gate checklist (HARD gates prominent, SOFT clearly marked),
and a kill-watch row. Overall verdict chip: **ON TRACK / CLOCK RESET / HALT / GRADUATED
(advisory)**. Footer (mandatory, `11` §0/§7): "Graduation earns only the *right to consider*
small real capital under a future prereg — it does NOT validate the edge; 6 months cannot."

**Done-criteria (+ §2.6).** Test (the most important suite in this doc — Rule 9): clean
months resets to 0 after a failing parity month and counts only consecutive passes since;
each gate maps to the exact `11` §7 threshold (25 bps / band / 15 pp); kill-watch trips at
≥5 stops and at maxDD > 23.1%; un-evaluable gates return `insufficient_data`, never a
fabricated pass. No threshold appears as a literal that disagrees with §2.3.

---

## 7. Cold-start checklist (per feature)

1. Read §0–§2 of this doc, then your feature section (Fn).
2. `git log --oneline -5` + read the latest paper-book close/session notes; confirm Fn not
   already shipped (check `MEMORY.md` + `routers/paper_v2.py` for the endpoint).
3. Use the **code-review-graph MCP tools first** (project CLAUDE.md) to find callers/tests
   before editing; fall back to Grep/Read only if the graph misses.
4. Backend: add endpoint + Pydantic models inline in `routers/paper_v2.py` (match house
   style). New table (F4/F5 only): `alembic heads` → model in `models.py` next to PaperV2* →
   autogenerate → review → up→down→up.
5. Tests: `backend/venv/bin/python -m pytest` for the new endpoint/table; mock external APIs;
   encode WHY (Rule 9).
6. Frontend: client fn in `api/client.js` → component in `S3PaperBook.jsx` → honesty labels
   (§1.3/§1.4) → `npm run build` green.
7. Verify against §2.6 + your Fn done-criteria. Surface anything skipped (Rule 12). Update
   `MEMORY.md` pointer if behaviour documentation changed.

## 8. What this doc does NOT do (guards)

- Does not re-open the strategy search, change decision/fill/cost logic, or move any `10`
  knob. Pure observability over persisted state.
- Does not invent or relax any graduation/kill threshold — all are locked in `11` §7/§8
  (§2.3). UI colour thresholds (F3/parity sparklines) are presentational and MUST be visibly
  distinct from the pre-registered gates.
- Does not claim 6 months validate the edge (`11` §0); every alpha-adjacent figure is
  labelled fidelity/breakage, not alpha.
- Does not add live price fetches or write paths that mutate book/engine state.
- Does not touch `FINAL_OOS` (spent) or any backtest split.
