# v3 / 14 — Probation Verdict Hardening (Decision-Layer Faithfulness & Durability)

> **Status: LOCKED — signed off by Arafat 2026-07-01 (§6). Fix #1/#2/#3 DONE 2026-07-01.**
> The F6 scorecard (`specs/v3/12`, `paper_v2.py:964–1379`) computes the four locked graduation
> gates and two kill watches correctly, but it is a **live-recomputed dashboard**, not a
> defensible verdict. Six months from `go_live = 2026-06-23` the probation must yield a clean,
> auditable GO/NO-GO. This spec closes three gaps between what the code does and what `11 §7/§8`
> require. **All three are plumbing/faithfulness fixes. NO locked threshold is touched** (T=25bps,
> Y=15pp, Z=10pp, K=5 stay verbatim); #1 and #3 make the code *more* faithful to the locked spec,
> not less. `FINAL_OOS` untouched; S3 frozen; probation clock NOT reset.

---

## 0. Why this exists — the honest ceiling (unchanged)

This hardens the *decision process*, not the edge. S3 remains `10`-exploratory and deflation-marginal;
a graduation still earns only *"consider small real capital under a future prereg"* (`11 §7`), never
"validated." Nothing here relabels S3 or authorizes capital. It exists so that whatever the 6-month
window concludes, the conclusion is **correct, self-consistent, and frozen in an artifact you can
defend later** — instead of a number that silently re-derives from mutable data.

---

## 1. Fix #1 — Verdict must reflect any HARD-gate failure (correctness bug) — **DONE 2026-07-01**

### The defect
Verdict logic (`paper_v2.py:1364–1376`):
```python
if any_kill:                                     verdict = "HALT"
elif clean_months_passed >= 6 and all_hard_pass: verdict = "GRADUATED"
elif clock_reset_at is not None:                 verdict = "CLOCK RESET"
else:                                            verdict = "ON TRACK"
```
`clock_reset_at` is set **only** by a parity break (Gate 1). So a **HARD** failure of Gate 2
(operational) or Gate 3 (cost) — with no parity break and no kill — falls through to the `else` and
reports **"ON TRACK"** while a hard graduation gate is red. At month 6 this reads green-ish while the
probation is actually failing. A verdict that says "ON TRACK" over a failing HARD gate is
indefensible.

### The fix (no new threshold)
Add one verdict state, `AT RISK`, driven purely by the already-computed gate statuses. New precedence:
```
any_kill tripped                          → HALT
any HARD gate status == "fail"            → AT RISK      # NEW — before GRADUATED/CLOCK RESET/ON TRACK
clean_months_passed >= 6 and all_hard_pass→ GRADUATED
clock_reset_at is not None                → CLOCK RESET  # parity-break reset, gates currently clean
otherwise                                 → ON TRACK
```
Notes:
- `AT RISK` is derived, not stored; it introduces **no** new bar — it just stops the headline from
  contradicting a gate the spec already defines.
- A parity fail is still surfaced as `CLOCK RESET` **only** when it is historical and the current
  Gate 1 status is `pass` again (clean run after a reset). A *current* Gate 1 `fail` is HARD → now
  correctly `AT RISK`. This removes today's ambiguity where a live parity fail could read `CLOCK
  RESET` instead of a failing state.
- `insufficient_data` is NOT a fail → an early book with no fills still reads `ON TRACK`, never
  `AT RISK` (fail-safe preserved).
- Extend the `ScorecardResponse.verdict` docstring/enum comment (`paper_v2.py:1018`) to the five
  states.

### Tests (regression-first, Rule 9)
`tests/paper_v2/test_scorecard.py`:
- G3 cost `fail`, no parity break, no kill, `clean_months_passed` ∈ {0, 6} → verdict `AT RISK`
  (encodes: *a hard cost breach cannot read ON TRACK or GRADUATED*).
- G2 operational `fail` → `AT RISK`.
- All hard `pass`, `clean_months_passed = 6` → `GRADUATED` (unchanged happy path still holds).
- Historical parity fail then 3 clean months (Gate 1 currently `pass`) → `CLOCK RESET`, not `AT RISK`.
- All `insufficient_data` early book → `ON TRACK` (fail-safe).

### Implementation note (landed 2026-07-01)
`g1_fidelity.status` is a **permanent all-time record** — any historical parity fail marks
it `"fail"` forever, even after later clean months (existing `test_ts3`, unchanged). Using
that field directly for the `AT RISK` trigger would misfire on a *recovered* book: the
scenario "historical fail → 3 clean months since" would read `AT RISK` instead of the
correct `CLOCK RESET`. So the `AT RISK` check uses a **separate, derived** signal for Gate 1
— whether the *most recent* parity row itself is failing — while Gates 2/3 use their
`.status` directly (both are already computed from current/recent state, no historical
baggage). This is purely a verdict-precedence detail; `g1.status` itself, `clock_reset_at`,
and all four gate definitions are byte-for-byte unchanged. Landed in
`app/routers/paper_v2.py` (`get_scorecard`) + `tests/paper_v2/test_scorecard.py`
(`test_ts17`–`test_ts20`) + `frontend/src/pages/S3PaperBook.jsx` (`VERDICT_META['AT RISK']`,
orange, so the badge doesn't silently fall back to the green `ON TRACK` style).

---

## 2. Fix #2 — Persist an immutable verdict snapshot (durability) — **DONE 2026-07-01**

### The gap
The verdict is recomputed on every GET from mutable tables (`paper_v2_daily_snapshot`,
`paper_v2_parity_check`, `paper_v2_pending_fills`). A later bhavcopy backfill or CA re-adjustment
changes historical NAV/parity, so a `GRADUATED`/`AT RISK` reading can silently change after the fact.
`11 §11`'s "write the verdict" is today a purely manual doc step — there is no dated, frozen record
of *what the scorecard said, on what data, at each month-end*.

### The fix — a snapshot table + a snapshot call at each month-end
**Migrations are holy (project law):** new table via Alembic, following the `paper_v2_run`
(`1b67f5d050b2`) / `paper_v2_alert` (`0a1f85aef724`) migration pattern.

New table `paper_v2_scorecard_snapshot`:
| column | type | note |
|---|---|---|
| `id` | PK | |
| `portfolio_id` | FK → paper_v2_portfolio | |
| `taken_at` | DateTime(UTC) | `datetime.now(timezone.utc)` (project law) |
| `as_of_date` | Date | IST processed date that triggered the snapshot |
| `trigger` | String | `"month_end"` \| `"manual"` |
| `verdict` | String | the five-state string incl. #1's `AT RISK` |
| `clean_months_passed` | Integer | |
| `clock_reset_at` | Date, nullable | |
| `payload` | JSON | full serialized `ScorecardResponse` (gates + kill_watch) — the frozen record |

Behavior:
- Factor today's `get_scorecard` body into a pure `build_scorecard(db, book) -> ScorecardResponse`
  (Rule 5 — deterministic, no model). The endpoint returns `build_scorecard(...)`; the snapshot
  writer persists `build_scorecard(...)`. **One source of truth**, so a snapshot can never disagree
  with the live tile.
- `_persist_scorecard_snapshot(book_id, as_of_date, trigger)` on a **fresh session** (mirrors
  `_persist_paper_run`, per the [[f4-run-history-done]] fresh-session pattern that fixed alert-session
  reuse) so a snapshot write can never poison the daily task's transaction.
- **Called from `execute_paper_daily_task` (`app/tasks.py`) only when the processed date is a
  month-end rebalance** — i.e. gated by the same `is_month_end_trading_day` calendar test the
  rebalance already uses (`specs/v3/13`), so we snapshot exactly at the cadence graduation is
  measured on. No new scheduler, no new beat entry.
- **Idempotency or death (project law):** unique-ish guard — at most one `month_end` snapshot per
  `(portfolio_id, as_of_date)`; a re-run of the same processed date **updates** that row, never
  appends. (Directly supports Fix #3's clock-integrity property.)
- New read endpoint `GET /v2/paper/scorecard/snapshots?limit` (Pydantic response, project law) for
  the eventual close-out review and a future UI timeline. UI card is out of scope here (follow-on).

### Tests
- Month-end processed date → exactly one snapshot row; `payload` round-trips to an equal
  `ScorecardResponse`.
- Non-month-end date → no snapshot written.
- Re-run same month-end date → row **updated in place**, still count 1 (idempotency).
- `build_scorecard` returns byte-equal result to the live endpoint for the same DB state (single
  source of truth).

### Implementation note (landed 2026-07-01)
`get_scorecard` is now a thin wrapper: it fetches the active book and returns
`build_scorecard(db, book)` — the same call the fresh-session snapshot writer makes, so
`test_ts21` asserts the two are byte-equal for identical DB state. The upsert itself is split
into `_upsert_scorecard_snapshot(db, portfolio_id, as_of_date, trigger, scorecard)` (pure,
testable against an ordinary session) and `_persist_scorecard_snapshot(portfolio_id, as_of_date,
trigger)` (the fresh-session wrapper tasks.py calls, mirroring `_persist_paper_run`) — the same
pure-function/fresh-session split Fix #1's note used for `build_scorecard` itself. The uniqueness
key is `(portfolio_id, as_of_date, trigger)`, not just `(portfolio_id, as_of_date)`, so a future
`"manual"` snapshot on the same date can never clobber the `"month_end"` graduation record for
that date (`test_ts24`). The call site lives in `tasks.py` inside the existing
`if report.is_rebalance and d >= go_live:` block, right after `parity.persist_parity` commits and
*before* the BREAK check — so a parity-break month-end still gets a frozen record of that break,
not just clean months. Landed in `app/db/models.py` (`PaperV2ScorecardSnapshot`), migration
`42a9ea26fbe2` (revises `1b67f5d050b2`), `app/routers/paper_v2.py` (`build_scorecard`,
`_upsert_scorecard_snapshot`, `_persist_scorecard_snapshot`, `GET /scorecard/snapshots`),
`app/tasks.py`, and 8 new tests across `tests/paper_v2/test_scorecard_snapshot.py` (`test_ts21`–
`test_ts26`) + `tests/paper_v2/test_paper_task.py` (`test_tc6`, `test_tc7`, plus snapshot
assertions added to the existing `test_tc1`/`test_tc2`). Full `paper_v2` + API suite green
(143 tests). UI timeline card remains out of scope (spec §2, follow-on).

---

## 3. Fix #3 — Gate 2 must audit replay completeness, not recency (faithfulness) — **DONE 2026-07-01**

### The gap
`11 §7.2` HARD gate = *every trading day in the window is processed in ascending order, with **no gap
left unprocessed before the next month-end**.* Today's Gate 2 (`paper_v2.py:1100–1179`) checks only:
(a) the **last 10** run rows for an unrecovered failure, and (b) `days_behind > 10` from
`last_processed_date`. An **interior** unbackfilled trading-day gap — one skipped early, then stepped
over as `last_processed_date` advanced past it — is invisible to both checks. That is precisely the
failure mode `§7.2` names, and the current gate cannot see it.

### The fix — calendar-anchored coverage audit
Reuse `app/data/trading_calendar.py` (`specs/v3/13`; `is_trading_day`, `next_trading_day`) — the same
authoritative NSE calendar the engine already trusts.

- Enumerate expected trading days from `go_live` to `book.last_processed_date` by walking
  `next_trading_day`. Compare against the set of dates actually covered by `success` runs
  (`paper_v2_run.last_date` reach, ascending) / persisted `paper_v2_daily_snapshot.date`.
- **Gate 2 `fail`** if any expected trading day in the window is unprocessed. Detail names the
  earliest missing date and the count.
- Keep the existing unrecovered-`failed`-run check (it catches a *current* break the coverage scan
  wouldn't attribute yet). Coverage audit **replaces** the `days_behind > 10` recency proxy.
- **Fail loud (Rule 12), don't fail wrong:** the calendar raises `CalendarCoverageError` outside
  `covered_years` (currently 2026; 2027 refresh is the standing `specs/v3/13` action, due ~Dec 2026).
  If the window reaches an uncovered year, Gate 2 returns **`insufficient_data`** with a detail
  pointing at the calendar refresh — it does **not** silently pass and does **not** crash the
  endpoint. (An uncovered-year audit is a known-blind gate, not a graduation fail.)

### Tests
- Contiguous processed window, no gaps → Gate 2 `pass`.
- One interior trading day missing (present in calendar, absent from processed set), `last_processed`
  advanced well past it → Gate 2 `fail` naming that date (encodes: *§7.2 is completeness, not
  recency*).
- Missing day is a **holiday/weekend** (not a trading day) → still `pass` (no false gap).
- Window straddles an uncovered year → `insufficient_data` citing the refresh, endpoint returns 200.

### Implementation note (landed 2026-07-01)
Replaced the `days_behind > 10` proxy in-place; the unrecovered-`failed`-run check above it
is untouched. Walk order: `d = go_live`, advance once via `trading_calendar.next_trading_day`
if `go_live` itself isn't a trading day, then loop `while d <= book.last_processed_date:
expected_days.append(d); if d == last_processed: break; d = next_trading_day(d)` — the
`break` before advancing past `last_processed_date` matters: calling `next_trading_day` one
extra step beyond the actual window would probe into the following year even when the window
itself never reaches an uncovered year (e.g. `last_processed_date` = the last trading day of
2026), producing a false `insufficient_data`. Coverage is read from
`paper_v2_daily_snapshot.date` (not `paper_v2_run`) — `live_engine.py`'s `_persist_state`
writes exactly one snapshot row per processed trading day, so this is the authoritative
"was this day actually durable" source, not merely "did a run claim success." A
`CalendarCoverageError` from the walk (window reaches an un-sourced year) is caught and
returns `insufficient_data` citing the `nse_holidays.json` refresh — it does not propagate
into a 500. `book.last_processed_date is None` (no day processed yet) also returns
`insufficient_data` rather than reaching the walk with a null bound.

**Test-fixture consequence:** because coverage is now proven by an actual
`paper_v2_daily_snapshot` row rather than merely a `paper_v2_run(status="success")` row, three
pre-existing tests in `tests/paper_v2/test_scorecard.py` (`test_ts14`, `test_ts19`) and
`tests/paper_v2/test_scorecard_snapshot.py` (`test_ts23`) needed one added `_add_snap(...)`
call each for `go_live` to keep asserting their intended verdict (`CLOCK RESET` / `ON TRACK`)
instead of incidentally tripping the new Gate 2 audit — this is fixing an unrealistic fixture
(a "success" run that never wrote its snapshot), not weakening the check. Four new tests
(`test_ts27`–`test_ts30`) land in `test_scorecard.py` exercising the real NSE calendar sequence
from `_GO_LIVE` (2026-06-23), including the sourced 2026-06-26 holiday (a weekday, deliberately
chosen so a missing non-trading weekday can't be mistaken for a gap) and an uncovered-year
window (`go_live=2026-12-24 → last_processed=2027-01-05`). No new migration — `g2_operational`
detail/source text changed only. Full `paper_v2` suite green (136 tests); `paper_v2` +
`tests/data/test_trading_calendar.py` combined: 144 tests.

---

## 4. Guards — what this spec does NOT do

- Does **not** change any locked threshold or gate definition (`11 §10.9`); T/Y/Z/K verbatim.
- Does **not** add a graduation bar or new gate — `AT RISK` is a derived headline over existing gates.
- Does **not** reset the probation clock (`go_live = 2026-06-23` continues).
- Does **not** touch `backtest_v2`, `FINAL_OOS`, or the frozen S3 convention.
- Does **not** authorize capital or relabel S3 (`10` exploratory ceiling stands).
- Does **not** build the snapshot-timeline UI card (follow-on, out of scope).
- Kill-watch completeness (§8 data-integrity / CA / gap-at-month-end interlocks surfaced in-UI) and
  a terminal `EXPIRED` state are **deferred** to a follow-on (originally items #4/#5) — not in this
  sprint.

---

## 5. Sequencing & acceptance

1. **Fix #1** (verdict correctness) — standalone; smallest blast radius; land first. **DONE 2026-07-01.**
2. **Fix #2** (`build_scorecard` refactor + snapshot table/migration/endpoint) — depends on #1 so the
   persisted `verdict` already includes `AT RISK`. **DONE 2026-07-01.**
3. **Fix #3** (Gate 2 coverage audit) — independent of #2; can land before or after. **DONE 2026-07-01.**

**Done = all of:** new/updated tests green in `tests/paper_v2/`; `alembic upgrade head` clean on the
new migration; `GET /v2/paper/scorecard` unchanged in shape except the five-state `verdict`;
`GET /v2/paper/scorecard/snapshots` live; no locked constant altered (grep-verify
`_FIDELITY_TOL_BPS/_DIRECTIONAL_UNDERPERF_LIMIT_PP/_KILL_CSTOP_PER_WINDOW/_KILL_MAXDD_PCT` unchanged).

---

## 6. Locked commitments (Arafat — sign to flip DRAFT → LOCKED)

Confirm or redline each before any code:

1. **`AT RISK` state** added with the §1 precedence (HALT > AT RISK > GRADUATED > CLOCK RESET >
   ON TRACK); `insufficient_data` is never `AT RISK`.
2. **Snapshot table** `paper_v2_scorecard_snapshot` via Alembic; snapshot written at each **month-end**
   from `execute_paper_daily_task` on a fresh session; idempotent per `(portfolio_id, as_of_date)`;
   read via `GET /v2/paper/scorecard/snapshots`.
3. **Gate 2 → calendar coverage audit** over `go_live → last_processed`; interior gap = `fail`;
   uncovered year = `insufficient_data` (fail-loud, not silent pass); recency proxy removed.
4. **No locked threshold touched**; clock not reset; `FINAL_OOS`/`backtest_v2` untouched.
5. **Scope fence:** kill-watch §8 completeness and a terminal `EXPIRED` verdict are a **separate
   follow-on**, not this sprint.

> **Signed:** Arafat  date 2026-07-01  (DRAFT → LOCKED)
