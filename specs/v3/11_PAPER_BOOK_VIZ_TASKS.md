# v3 / 11 — S3 Paper Book Observability (frontend viz + persistence) — EXECUTION TASKS

> **Status: LOCKED (2026-06-23). NOT yet executed.** All open decisions resolved — parity
> durability mechanism (V11.2, `db.commit()` not flush), probation denominator (calendar
> months) + staleness threshold (>2 trading days) (V11.6 #4), and `reason` taxonomy assertion
> (V11.3 #3 / V11.4) are now frozen. Index coverage confirmed: `index_prices` spans inception
> → target (tasks.py:92–93), so the §1.2 full-since-inception overlay is executable. This is a build-tasks
> doc subordinate to the LOCKED `11_PROBATIONARY_DEPLOY_PREREG.md`. It does **not**
> re-open the strategy search, change any decision/fill logic, or touch `backtest_v2`
> engine behaviour. It is pure **observability**: persist state the engine already
> computes-then-discards, expose it read-only, and render it.
>
> **Execution will happen in a NEW cold session.** This doc is written so that session
> can execute without re-deriving context. Read this top-to-bottom first, then the
> "Cold-start checklist" (§7).

---

## 0. Why this exists

`S3PaperBook.jsx` (slice 1, commit `ff3449a4`) renders only the book header cards +
holdings table. Arafat asked to add: **(a)** equity/NAV curve, **(b)** shadow-parity
fidelity badge, **(c)** rebalance log, **(d)** a Portfolio.jsx summary card linking
here — plus recommended enhancements.

The blocker for the curve was that **per-day NAV history is not persisted**: the engine
produces a `DailySnapshot` every day but it is discarded. This spec fixes that.

**Hard rule (inherited from `11` §1 + the router docstring):** every endpoint stays
**read-only**. No live price fetch (project law: never hit live NSE/yfinance) — every
figure derives from already-persisted state.

---

## 1. Locked design decisions (Arafat, 2026-06-23)

These were decided in planning and are **frozen** for execution:

1. **Curve scope = full since-inception + go-live divider.** Persist a snapshot for
   *every* replayed day, including the ~115-day warm-start replay (inception 2017 →
   go-live). The chart shows one continuous curve with a vertical divider at
   `go_live_date`: pre-divider = "warm-start (backtest replay)", post-divider = "live
   paper". Never conflate the two in labelling. Rationale: the snapshot is already
   computed for warm-start days, so the full curve is **free**, and the honest framing
   (divider) matches the program's discipline.
2. **Benchmark overlay = YES.** Persist the Nifty200 Mom30 TRI `index_level` per
   snapshot day and overlay it (rebased to the book's starting capital) on the curve.
   The whole v2→v3 arc concluded "S3 ≈ buy the Mom30 index fund after costs"
   ([[skew-recheck-cracks-index-wall]]); the viz must make book-vs-index **visible**,
   not hidden.
3. **Scope = all four + recommended enhancements** (benchmark overlay, exposure band,
   probation progress + staleness), spec-now / execute-later.

---

## 2. Data model changes (one Alembic migration, two new tables)

> Project law §2: migrations are holy; SQLAlchemy ORM only. Add models to
> `backend/app/db/models.py` next to the existing `PaperV2*` classes (~line 490–579),
> then `alembic revision --autogenerate` + review + `alembic upgrade head`. The current
> head is `b7c4f1a2d3e8` (the `decision_price` migration from P11.1).

### 2.1 `paper_v2_daily_snapshot`

One row per processed trading day. Mirrors `backtest_v2.schemas.DailySnapshot` plus the
benchmark level. Idempotent on `(portfolio_id, date)`.

```python
class PaperV2DailySnapshot(Base):
    __tablename__ = "paper_v2_daily_snapshot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_v2_portfolio.id"), nullable=False)
    date = Column(Date, nullable=False)            # the processed trading day
    equity = Column(Float, nullable=False)         # cash + Σ shares·close_tr  (NAV)
    cash = Column(Float, nullable=False)
    invested_value = Column(Float, nullable=False) # Σ shares·close_tr
    exposure = Column(Float, nullable=False)       # invested_value / equity  (0–1)
    n_positions = Column(Integer, nullable=False)
    # Nifty200 Mom30 TRI close on this date (deployment benchmark, 08 §10). Nullable:
    # a day with no index point (gap) stores NULL and the FE skips it in the overlay.
    index_level = Column(Float, nullable=True)
    is_forward = Column(Boolean, nullable=False, default=False)  # date >= go_live
    __table_args__ = (
        UniqueConstraint("portfolio_id", "date",
                         name="uq_paper_v2_snap_portfolio_date"),
        Index("ix_paper_v2_snap_portfolio_date", "portfolio_id", "date"),
    )
```

### 2.2 `paper_v2_parity_check`

One row per monthly shadow-parity run (`11` §2/§7.1). Persists the `ParityReport`.

```python
class PaperV2ParityCheck(Base):
    __tablename__ = "paper_v2_parity_check"
    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("paper_v2_portfolio.id"), nullable=False)
    as_of = Column(Date, nullable=False)           # rebalance date the check ran on
    passed = Column(Boolean, nullable=False)
    max_dev_bps = Column(Float, nullable=False)    # vs PARITY_TOL_BPS (25.0)
    tol_bps = Column(Float, nullable=False, default=25.0)
    breaches = Column(JSON, nullable=True)         # [[isin, dev_bps], ...]
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.datetime.now(datetime.timezone.utc))
    __table_args__ = (
        UniqueConstraint("portfolio_id", "as_of",
                         name="uq_paper_v2_parity_portfolio_asof"),
        Index("ix_paper_v2_parity_portfolio_asof", "portfolio_id", "as_of"),
    )
```
> `JSON` is already imported/used in models.py if other tables use it; if not, import
> `from sqlalchemy import JSON`. Postgres `jsonb` is fine via the generic `JSON` type.

---

## 3. Backend tasks

### V11.1 — Persist the daily snapshot (the curve's data source)

**File:** `backend/app/paper_v2/live_engine.py` → `persist_state(...)`.

`process_day` already has `snapshot = state.portfolio.snapshots[-1]` (live_engine.py:484)
and passes nothing onward. Two clean options — **use option A**:

- **Option A (recommended):** pass the `snapshot` + a `go_live` date + the per-day
  `index_level` into `persist_state` and upsert a `PaperV2DailySnapshot` row there
  (same transaction as the rest of the day's writes ⇒ atomic, idempotent). The caller
  already knows `go_live` (tasks.py:109) and has `index_prices` (a `pd.Series` indexed
  by date) — look up `index_prices.get(pd.Timestamp(process_date))` for `index_level`.

  Signature change: `persist_state(..., snapshot: DailySnapshot | None, go_live: date,
  index_level: float | None)`. Upsert keyed on `(portfolio_id, date)` so a re-run /
  backfill replaces rather than duplicates (Pipeline Law: idempotency or death).
  `is_forward = process_date >= go_live`.

- Option B (rejected): a separate persist call in `process_day`. Splits the day's writes
  across two code paths; A keeps one atomic write.

**Wire-through:** `process_day` must accept `go_live` (it does not today) — add it as a
kwarg threaded from `tasks.py`. `index_level` is looked up inside `process_day` from the
`index_prices` Series it already receives, then handed to `persist_state`.

**Edge cases:**
- `snapshot is None` (no snapshot produced — e.g. empty calendar day): skip the snapshot
  row, don't crash. Should not happen on a real trading day but guard it (Rule 12: fail
  loud only on genuine corruption, not on benign absence).
- Warm-start backfill: the first daily run replays ~115 days; each calls `persist_state`
  once ⇒ the whole historical curve populates in one run, idempotently.

### V11.2 — Persist the parity report

**File:** `backend/app/tasks.py`, right after `par = parity.shadow_parity(...)`
(tasks.py:140, inside the `if report.is_rebalance and d >= go_live:` block).

Upsert a `PaperV2ParityCheck` row from `par` (`as_of=d, passed, max_dev_bps,
tol_bps=parity.PARITY_TOL_BPS, breaches=par.breaches`). Persist **before** the
`if not par.passed: raise` halt, so a BREAK is durably recorded even though the run then
halts and resets the 6-month clock (`11` §7.1).

**LOCKED parity-durability mechanism — `db.commit()`, never flush-only.** The halt's
teardown rolls back: `raise` → `except` re-raises → `finally: db.close()` (tasks.py:142–152),
and closing a session with uncommitted work discards it. A flush-only BREAK row is therefore
**lost on rollback**, defeating the durability requirement. So:
- **PASS path:** the upsert may ride the normal day transaction (committed as usual).
- **BREAK path:** call `db.commit()` (or a separate short-lived session) to durably persist
  the row **before** raising. Flush is insufficient — do not use it here.

### V11.3 — Three read-only endpoints

**File:** `backend/app/routers/paper_v2.py`. Add Pydantic response models + routes
alongside the existing `/book` and `/positions`. All read persisted state only.

1. `GET /v2/paper/nav` → `list[NavPointResponse]`
   - `NavPointResponse`: `date, equity, cash, invested_value, exposure, n_positions,
     index_level: float | None, index_rebased: float | None, is_forward: bool`.
   - `index_rebased` = `index_level / first_non_null_index_level × starting_capital`,
     computed server-side so the FE overlays book-NAV vs rebased-index on one axis
     without client math. Compute the rebase anchor from the earliest snapshot that has
     a non-null `index_level`. If no index points exist, all `index_rebased = None`.
   - Order ascending by `date`. Return `[]` if no active book.
   - Also expose `go_live_date` so the FE can place the divider — either add it to each
     point (redundant) or return an envelope `{ go_live_date, points: [...] }`. **Use the
     envelope** (`NavSeriesResponse { go_live_date: date | None, points: [...] }`) — one
     source of truth for the divider.

2. `GET /v2/paper/parity` → `ParitySeriesResponse { latest: ParityCheckResponse | null,
   history: list[ParityCheckResponse] }`
   - `ParityCheckResponse`: `as_of, passed, max_dev_bps, tol_bps, breaches:
     list[tuple[str, float]]`.
   - `latest` = max `as_of`. `history` ascending. Drives the header badge + a small
     parity history strip.

3. `GET /v2/paper/rebalances` → `list[RebalanceEventResponse]`  **(no new table — reads
   `paper_v2_pending_fills`)**
   - Group `PaperV2PendingFill` rows by `decision_date`; each event lists its fills with
     `symbol, isin, side, qty, reason, status, decision_price, fill_date, fill_price,
     cost_rupees`. Newest `decision_date` first.
   - Shape suggestion: `RebalanceEventResponse { decision_date, reason, n_buys, n_sells,
     n_trims, total_cost_rupees, fills: list[RebalanceFillResponse] }` where `reason` is
     "rebalance" if any fill is a rebalance else "catastrophic_stop".
   - **LOCKED:** the `reason` taxonomy is assumed to be exactly
     `{rebalance, catastrophic_stop}`. The V11.4 test (§4) must assert the engine's fill
     `reason` field emits no third value; if a third value exists, the FE badge would
     silently mislabel — fail loud (Rule 12) rather than fall through to a default.

**Register:** already mounted (`main.py:81`). Keep all responses Pydantic (§2 law).

### V11.4 — Backend tests

**File:** `backend/app/tests/` (match existing `paper_v2` test module location — the
P11.x tests already live there; 28 paper_v2 tests are green per [[isin-succession-...]]).

- Snapshot persistence: process a synthetic 2-day replay (mock prices + index Series,
  **no live yfinance** — §5 law), assert one `PaperV2DailySnapshot` per day, correct
  `equity == snapshot.equity`, `is_forward` flips at `go_live`, and that **re-running the
  same day upserts (no duplicate row)** — encodes the idempotency intent (Rule 9).
- `index_level` lookup: a date present in `index_prices` stores the value; a gap date
  stores NULL.
- Parity persistence: a PASS writes a row; a BREAK writes a row **then** raises (assert
  the row exists after the raise).
- Endpoint shape: TestClient asserts `/nav` envelope (`go_live_date` + ascending points +
  `index_rebased` anchored to first non-null), `/parity` latest==max as_of, `/rebalances`
  grouping + newest-first.

---

## 4. Frontend tasks

> Stack facts (verified): routing in `App.jsx` (`/paper-v2` → `S3PaperBook`, already
> wired). API client `frontend/src/api/client.js` (axios, `apiClient`, existing
> `getPaperV2Book/Positions` at line 43–46 — add new fns in that block). Charts:
> **recharts ^3.8.1**, lazy-loaded — copy the `React.lazy(() => import('recharts')...)`
> pattern from `Backtest.jsx` (do NOT import recharts eagerly; it bloats the bundle).
> Data transforms via `lodash/fp` (project law §3). Tailwind palette tokens
> (`bg-secondary`, `text-muted`, `bullish`/`bearish`, `primary`) — no custom CSS.

### V11.5 — API client functions

Add to `client.js` under the existing v2 paper block:
```js
export const getPaperV2Nav = () =>
  apiClient.get('/v2/paper/nav').then((res) => res.data);
export const getPaperV2Parity = () =>
  apiClient.get('/v2/paper/parity').then((res) => res.data);
export const getPaperV2Rebalances = () =>
  apiClient.get('/v2/paper/rebalances').then((res) => res.data);
```

### V11.6 — `S3PaperBook.jsx` enhancements

Extend the existing page (keep the `notArmed`/`loading`/`Fully in Cash` states, the
header cards, and the holdings table). Add to the parallel `Promise.all` load (each new
call `.catch` → null so one failing endpoint doesn't blank the page; match the existing
404-tolerant pattern for `getPaperV2Book`):

1. **Fidelity badge (header).** New chip next to the "Read-only · Frozen" lock, fed by
   `parity.latest`: green `PASS · max_dev N.N bps` / red `BREAK` (with as_of). If
   `latest` is null → neutral "No parity check yet". If a BREAK exists anywhere in
   history, show a persistent red "CLOCK RESET" note (the 6-month window restarted, §7.1).

2. **Equity/NAV curve** (`NavCurve` sub-component). Recharts `LineChart` (lazy), x=`date`,
   two series: book `equity` (primary colour) + `index_rebased` (muted, dashed). Add a
   `ReferenceLine x={go_live_date}` as the warm-start↔live divider with a label. Tooltip
   shows date, NAV, index, and the gap (book − index) in ₹ and %. Empty state if
   `points` is empty (book armed but not yet replayed).
   - **Exposure band (recommended enhancement / regime proxy):** a thin secondary strip
     (small `Area` or coloured row below the curve) driven by `exposure` — 0 = risk-off
     (in cash), ~1 = risk-on. Surfaces regime transitions without persisting regime
     state (the deliberate slice-1 gap). Keep it visually subordinate to the NAV curve.

3. **Rebalance log** (`RebalanceLog` sub-component). Table/accordion grouped by
   `decision_date` (newest first). Per event: a header row (date · reason badge
   rebalance/stop · counts · total cost) expanding to its fills (symbol, side-coloured
   buy/sell/trim, qty, decision→fill price, cost). Reuse the holdings-table styling.

4. **Probation progress + staleness (recommended enhancement).** A slim progress bar
   `go_live_date → go_live_date + 6 months`. **LOCKED denominator = calendar months**
   (`go_live + 6 months`), not a trading-day count — the `11` prereg frames probation as
   "6 forward months", and a trading-day count drifts on holidays. Plus a **staleness
   warning** when the replay clock (`last_processed_date`) lags the latest expected trading
   day by **more than 2 trading days** (LOCKED threshold) — the worker/beat have been
   stopped before ([[s3-probationary-paper-deploy-11]]), so a visible "replay stale — last
   processed {date}" banner is worth the few lines.

### V11.7 — Portfolio.jsx summary card

Add a compact card (reuse the existing `StatCard` pattern in Portfolio.jsx ~line 208)
linking to `/paper-v2` via `useNavigate` (already imported). Show NAV, total return %,
and the parity status dot. Fetch via `getPaperV2Book` + `getPaperV2Parity`; **hide the
card entirely** (render null) if `/book` 404s (probation not armed) so an unarmed book
doesn't clutter the portfolio page.

---

## 5. Verification (success criteria — Rule 4)

- `alembic upgrade head` then `alembic downgrade -1` round-trips cleanly (both new tables).
- Backend: all existing paper_v2 tests still green + the new V11.4 tests pass. Run with
  the project venv only: `backend/venv/bin/python -m pytest backend/app/tests -k paper_v2`.
- A local daily-task run (or a synthetic replay in a test) populates
  `paper_v2_daily_snapshot` across the full warm-start window once, idempotently, and
  `paper_v2_parity_check` on each forward month-end.
- `/nav`, `/parity`, `/rebalances` return validated Pydantic shapes; `/nav` envelope has
  the go-live date and ascending points with the rebased index anchored to the first
  non-null index level.
- FE: `npm run dev`, open `/paper-v2` — curve renders with the go-live divider + index
  overlay, fidelity badge reflects the latest parity row, rebalance log groups by date,
  progress/staleness render. Portfolio card links through and hides when unarmed.
- **Fail loud (Rule 12):** if any test is skipped or the migration is hand-edited away
  from autogenerate, say so explicitly in the completion note.

---

## 6. Explicitly OUT of scope

- **No engine/decision changes.** `step_day`, parity logic, alerting, the queue — all
  byte-frozen. This spec only *reads* what they produce. Any change that could alter a
  fill or a parity outcome is a violation of `11` §1 (frozen probation).
- **No regime-state persistence.** Exposure is the agreed proxy. If true regime state is
  wanted later, it is a separate change to the engine's snapshot — not this spec.
- **No write endpoints.** The book stays read-only (router docstring + `11` §1).
- **No new scheduler / no live price fetch.** Reuse the existing daily task; all values
  are from persisted state (§5 law).

---

## 7. Cold-start checklist (for the executing session)

1. Read this doc, then `11_PROBATIONARY_DEPLOY_PREREG.md` §1–§5e for the frozen
   constraints, then the memory notes [[s3-probationary-paper-deploy-11]] and
   [[isin-succession-continuity-gap]] for current book state.
2. Confirm current alembic head (`b7c4f1a2d3e8`) before autogenerating the migration.
3. Backend first (V11.1→V11.4), verify migration + tests green, THEN frontend
   (V11.5→V11.7). Keep diffs surgical (Rule 3) and idempotent (Pipeline Law).
4. Use the code-review-graph MCP tools before Grep/Read when exploring (CLAUDE.md).
5. Commit per logical slice; do not push unless Arafat asks. Branch is
   `refactor/v2-momentum-engine`.

---

## 8. Integration-point reference (verified 2026-06-23)

| Concern | Location |
|---|---|
| `DailySnapshot` dataclass | `backend/app/backtest_v2/schemas.py:41` (date, equity, cash, invested_value, exposure, n_positions) |
| Snapshot produced, discarded | `live_engine.py:484` (`process_day`) |
| Persist hook (snapshot) | `live_engine.py` `persist_state(...)` (V11.1) |
| Parity computed, only logged | `tasks.py:140` (V11.2) |
| `ParityReport` shape | `paper_v2/parity.py:34` (as_of, passed, max_dev_bps, breaches) |
| `PARITY_TOL_BPS = 25.0` | `paper_v2/parity.py:31` |
| Rebalance log source (no new table) | `PaperV2PendingFill`, `models.py:544` |
| PaperV2 models block | `models.py:490–579` |
| Router (add endpoints) | `routers/paper_v2.py` (mounted `main.py:81`) |
| go_live derivation | `tasks.py:109` = `created_at` in IST |
| index_prices Series | `tasks.py:93` `benchmark.load_price_index(inception, target)` |
| FE page | `frontend/src/pages/S3PaperBook.jsx` (route `App.jsx:26`) |
| FE client paper block | `frontend/src/api/client.js:42–46` |
| Chart pattern (lazy recharts) | `frontend/src/pages/Backtest.jsx` |
| Portfolio card pattern | `frontend/src/pages/Portfolio.jsx:208` (`StatCard`, `useNavigate`) |
