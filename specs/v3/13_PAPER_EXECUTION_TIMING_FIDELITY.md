# v3 / 13 — Paper Execution-Timing Fidelity Gap & Forward Decision

> **Status: SIGNED OFF — 2026-06-30 (Arafat). Calendar + MOO fix ADOPTED; probation clock NOT
> reset. Engine integration LANDED (see Progress).**
> Records a fidelity gap in the S3 probation paper engine (`11`): the rebalance is *computed*
> only after the open at which it is *modeled to fill* has already printed. The paper book
> remains a faithful backtest **replay**, but it is **not** an honest proof of operational
> executability — which is the entire deliverable of S3 probation (P11.3). This doc states the
> problem, the root cause, the rejected alternative, and the fix. **`FINAL_OOS` untouched, S3
> strategy frozen — the fix changes only the live shell's wall-clock timing, not any decision.**

---

## The impossibility (Arafat's diagnosis, confirmed)

Two mechanisms combine to make the live rebalance physically unexecutable:

| Step | Wall-clock | What happens |
|------|-----------|--------------|
| Bhavcopy for month-end day **D** lands | ~4–6 PM IST on D | D's close is now known |
| Beat fires | 19:30 IST on D (`celery_app.py:26`, Mon–Fri) | D is the **trailing edge** → **held back**, not processed |
| Beat fires | 19:30 IST on D+1 | D's bhavcopy now has a successor → D processed. Decision = D's close; modeled fill = next processed open = **D+1's open** |
| D+1's open | 9:15 IST on D+1 | **printed ~10 hours before D was even processed** |

You cannot fill at a price that has already printed. The rebalance fill is always modeled at an
open that is in the past at the moment the rebalance is computed.

## Root cause

Two pieces, both in `backend/app/paper_v2/live_engine.py`:

1. **Execution convention (correct, keep it).** `step_day` decides from data ≤ D and queues orders
   that fill at the *next processed open* (`:64`, `:131` — "decision from data ≤ D, fill at D+1's
   open"). Standard "signal at close → trade at next open"; exists to kill look-ahead. Honorable in
   principle.
2. **Trailing-edge holdback (`confirmed_replay_days`, `:113-149`) — the actual culprit.** The latest
   stored bhavcopy day is held back until a *later* trading day appears, because the repo has **no
   forward trading/holiday calendar** and therefore cannot identify a month-end in real time (a
   month-end is the last *trading* day of its calendar month; without the holiday calendar you only
   learn it once the next month's first day arrives). The holdback is *fidelity-neutral for replay*
   (the held-back day is later processed with the identical information set, byte-identical, `11`
   §7.2) **but it injects a structural one-trading-day lag** that pushes decision-finalization to
   *after* the open it is supposed to fill.

**The holdback is a workaround for missing reference data, and that workaround is what breaks live
executability.**

## What is and isn't broken

- **NOT broken: backtest-replay fidelity.** The paper NAV, parity, and cost ledgers faithfully
  reproduce the frozen S3 backtest. Nothing reported to date is wrong *as a replay*.
- **Broken: the operational-readiness claim.** S3 probation exists to validate **ops / fidelity /
  cost — not the edge** (`s3-probationary-paper-deploy-11`). A shell that books a rebalance fill at a
  price it could never have achieved live is validating *replay*, not *executability*. The thing
  probation is meant to prove is precisely the thing this gap leaves unproven.

## Proposed fix — make the convention physically honorable

The "decision@close D → fill@open D+1" convention **is** achievable; it only requires finalizing the
decision *before* D+1's open instead of after it. The nightly window already exists: bhavcopy for D
lands ~4–6 PM IST on D; the market opens 9:15 IST on D+1; the beat already runs 19:30 IST on D.

1. **Add an authoritative NSE forward trading/holiday calendar** (NSE publishes annually). With it,
   on the evening of D you can deterministically answer "is D the last trading day of its calendar
   month?" → **the trailing-edge holdback becomes unnecessary and is removed.**
2. **Finalize the rebalance on the evening of D** (the 19:30 IST run already holds D's bhavcopy).
3. **Stage the orders overnight as Market-On-Open (MOO) orders for D+1.** The broker fills them at
   D+1's open — exactly the backtest convention, now honorable because orders are staged ~14 hours
   *before* the open rather than discovered ~10 hours *after* it.

Calendar (1) removes the lag; MOO staging (3) makes "fill at next open" a real, achievable
execution. Paper and a future live system then honor the same convention, and the paper book becomes
an honest proof of operational executability.

## Rejected alternative

**Keep the holdback; change the fill convention to D+2's open (or D+1 close/VWAP)** so the fill is
always in the future relative to processing. Rejected because it (a) adds a full extra day of signal
decay and slippage, (b) **changes the strategy's measured edge** → forces a re-backtest, and (c)
breaks the **frozen** S3 convention that `FINAL_OOS` was validated under. This is convention drift on
a frozen strategy traded for a workaround — the wrong direction.

## Progress

- **2026-06-30 — Step 1 (forward calendar) SOURCED.** Authoritative NSE 2026 equity holiday
  list checked in at `backend/app/data/nse_holidays.json` (16 weekday closures, provenance: NSE
  circular CMTR71775, cross-checked cleartax/zerodha/groww — all three agree). Reader at
  `backend/app/data/trading_calendar.py` exposes `is_trading_day`, `next_trading_day`, and
  `is_month_end_trading_day` (real-time month-end test, no successor day needed); **fails loud**
  on any year outside `covered_years` so an un-refreshed file halts rather than mis-detects.
  8 tests pass (`backend/tests/data/test_trading_calendar.py`). Calendar must be refreshed with
  NSE's 2027 list when published (~Dec 2026).

- **2026-06-30 — Step 2 (engine integration) LANDED.** Wiring (all in `app/paper_v2/`):
  - `live_engine.build_live_context` now applies `_confirm_trailing_rebalance(ctx, calendar)` at
    the single context-build chokepoint (shared by the live book, the shadow-parity re-derivation,
    and the warm-start replay → all stay byte-identical). It resolves the **one** date the stored
    frame cannot self-confirm — the trailing edge — against the forward calendar: if the latest
    stored day is not the true last trading day of its month, it is discarded from
    `ctx.rebalance_dates` (kills the spurious daily month-end); if it IS the real month-end it is
    kept, so the rebalance fires the *same evening*. Interior month-ends (which have a successor
    in-frame) are never re-checked → no calendar coverage needed for history.
  - `live_engine.confirmed_replay_days` **drops the trailing-edge holdback** — every unprocessed
    day `last_processed < D ≤ target` is replayed, including the trailing edge, on the evening of D.
  - The backtest engine (`backtest_v2.engine._month_end_dates` / `_rebalance_dates`) is **untouched**
    — FINAL_OOS and the frozen S3 convention are not perturbed; the fix lives entirely in the live
    shell's wall-clock sequencing. Fill convention unchanged (decision ≤ D → fill at D+1's open).
  - **Fail-loud preserved (Rule 12):** the trailing edge is always the latest bhavcopy ≈ today, so
    the calendar lookup is on a covered year in normal operation; a stale calendar (e.g. a Jan-2027
    run before the 2027 refresh) raises `CalendarCoverageError` and halts the run rather than
    silently mis-detecting a month-end.
  - Tests: `confirmed_replay_days` / `_confirm_trailing_rebalance` covered in
    `tests/paper_v2/test_live_engine.py` (DC7 + DC7b — discard false / keep true / leave interior /
    fail-loud uncovered); the DC1–DC5 byte-identical fidelity suite re-run green over covered-year
    fixtures.

- **Step 3 (MOO execution model) — documentation, not code.** The paper shell models the fill at
  D+1's open; a live deployment realises that as an overnight **Market-On-Open** order staged the
  evening of D (after D's close, ~14h before the open it fills at). No order-routing code exists in
  the paper book — there is no broker — so "MOO" is the documented execution semantics that makes
  the unchanged `decision ≤ D → fill@D+1-open` convention physically honorable. It becomes real
  code only at actual live go-live.

## Forward decision (SIGNED — Arafat, 2026-06-30)

- [x] **Adopt the calendar + MOO fix.** Forward NSE calendar → drop holdback → overnight MOO at
      D+1 open. Implemented as above; the backtest engine and FINAL_OOS are untouched.
- [x] **Probation clock NOT reset.** This is the *first* rebalance of the paper book and the gap
      was correctly diagnosed on time (before the first counted month-end fill mattered), so removing
      the holdback is treated as a fidelity-neutral wall-clock correction, not a strategy/operational
      change that invalidates accrual. The 6-month probation clock from `go_live = 2026-06-23`
      (`11` §7.1) **continues** — it is *not* reset.

> **Signed off:** Arafat — 2026-06-30. Calendar+MOO adopted, clock not reset, engine integration
> landed. Remaining standing action: refresh `nse_holidays.json` with NSE's 2027 list (~Dec 2026).
