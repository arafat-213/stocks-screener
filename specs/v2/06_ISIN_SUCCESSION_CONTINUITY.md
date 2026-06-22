# Spec 06 — ISIN-Succession *Identity* Continuity (open data-layer gap)

> **Status: IN PROGRESS — strategy locked (§9), tasks broken out (§10). T06.0 DONE
> (2026-06-22, independent bookkeeping guard — see §10) + T06.1 DONE (2026-06-22, see §11)
> + T06.2 DONE (2026-06-22, `instrument_id` materialised + store re-derived — see §12)
> + T06.3 DONE (2026-06-22, signal/factor/engine identity re-keyed onto `instrument_id` —
> see §13) + T06.4 DONE (2026-06-22, succession-coverage check + clean validation run —
> see §14) + T06.5 DONE-FOR-SCOPE (2026-06-22, paper book reset + re-warm-started on
> stitched data; the 4 face-value-succession ghosts ELIMINATED, full ~20-name book in
> risk-on regimes, shadow-parity 0.0 bps — but two honest caveats surfaced: the edge state
> is genuine risk-off cash, and 3 NEW out-of-scope **merger/cancellation** ghosts remain;
> see §15) ; T06.6 not started.**
> Decision (2026-06-22): canonical `instrument_id` (§9). Cold-session task chain
> `T06.1 → … → T06.6` in §10; T06.1 is the unconditional gate. Surfaced 2026-06-22 during the v3/11
> S3 forward-paper warm-start (`specs/v3/11_PROBATIONARY_DEPLOY_PREREG.md`). Deferred to a
> dedicated data-layer session (owner decision, 2026-06-22). **Worker + Celery beat are
> left STOPPED so the probation does not auto-start on a contaminated book.**
>
> **Relationship to `05`:** `05_DATA_ADJUSTMENT_REMEDIATION.md` already identified
> **ISIN succession** as a mechanism and fixed it at the **adjustment** layer — the
> `events_by_symbol` bridge in `adjust.py` so that a CA event filed under the *old* ISIN
> is applied to prices now trading under the *new* ISIN (the new leg is correctly
> split-adjusted; 62 bridged, 180 with no CA event in the feed). **This doc is the
> still-open *next* layer of the same root cause: identity continuity.** `05` made the
> new leg's prices *correct*; it did **not** stitch old + new into one continuous
> *instrument* for the holdings/signal layer. That gap is what `06` is about.

---

## 1. The gap in one sentence

When a company changes ISIN (typically a face-value sub-division — `INE296A01024 → INE296A01032`),
the old and new ISINs remain **two separate instruments** in `prices_adjusted`, so the
strategy (a) can **never sell** a position held under the old ISIN once it stops trading
(unsellable **ghost position**), and (b) sees the new ISIN as a **brand-new name with no
momentum history**, making it unselectable for ~the lookback window after the change.

## 2. How it surfaced (v3/11 warm-start)

Replaying frozen S3 inception→2026-06-18 as a paper book (faithful — shadow-parity
`max_dev_bps = 0.0` vs a from-scratch backtest) left the book in a **degenerate** state:
**6 holdings, ₹2.63M idle cash** instead of a 20-name momentum portfolio. Of the 6:

| Symbol | Held (dead) ISIN | Current live ISIN | Cause |
|---|---|---|---|
| BAJFINANCE | INE296A01024 | **INE296A01032** | ISIN succession (unstitched) |
| MCX | INE745G01035 | **INE745G01043** | ISIN succession (unstitched) |
| NAZARA | INE418L01021 | **INE418L01047** | ISIN succession (unstitched) |
| EASEMYTRIP | INE07O001018 | **INE07O001026** | ISIN succession (unstitched) |
| HDFC | INE001A01036 | — | legit (merged into HDFC Bank, Jul 2023) |
| TATAMTRDVR | IN9155A01020 | — | legit (DVR cancelled, 2024) |

The 4 succession names still trade today under the new ISIN; the book holds the dead leg,
can't sell it (no future prices → "fill dropped, position carried"), and MTM-freezes it.
**Parity passing means the backtest does the identical thing — this is NOT a live-shell
bug; it is in the data/identity layer and contaminates the backtest too (see §5).**

## 3. Blast radius (full universe, 2017→2026, measured 2026-06-22)

| Metric | Count |
|---|---|
| Symbols with >1 ISIN | 388 |
| Sequential ISIN-change events (old leg ends, new leg begins next day) | **406** |
| ...new leg since 2024 | 168 |
| **...old leg liquid (≥ ₹5 cr ADV) → S3-eligible, ghost risk** | **150** |
| ...liquid **and** recent (≥ 2024) | 79 |
| Total symbols | 3,389 |

Top liquid successions are exactly the names a momentum book holds: `IRCTC`, `HDFCBANK`,
`BAJAJFINSV`, `TATASTEEL`, `BAJFINANCE`, `YESBANK`, `EICHERMOT`, `KOTAKBANK`, `HAL`,
`COFORGE`, `MAZDOCK`, `CANBK`, `TATAINVEST`. Every transition is **next-day**
(`old_last` → `new_first` consecutive) and the last two ISIN digits increment
(`...A01024 → ...A01032`) — a strong, mappable signal.

## 4. Root cause & why `05`'s bridge doesn't cover it

`05` keyed its fix to **adjustment factor lookup**: find the CA event (filed under old
ISIN) and apply the multiplier to the new ISIN's prices. Correct, but the two ISINs stay
**distinct rows / distinct instruments**. The simulation/signal layer keys everything on
ISIN (`02_SIMULATION_CORE.md`), so:

- **Momentum discontinuity:** `mom_12_1` etc. on the new ISIN only see post-succession
  history → the name is invisible to selection for ~12 months after every change.
- **Ghost holdings:** a position in the old ISIN has no price after the change → the
  engine's next-open fill finds no price → sell dropped → carried forever (`engine.py`
  fill model). The §5e CA *price-rescale* in `11` does not help — that handles a moving
  adjustment anchor on a still-trading ISIN, not an ISIN that ceased to exist.

## 5. Impact on validation (research-integrity note)

Because the live warm-start is byte-identical to the backtest, **S3's reported backtest
metrics were computed on identity-broken data**: ~150 liquid names had truncated momentum
history and any held leg that succeeded became a frozen ghost. This does not by itself
invalidate the v2/v3 conclusions, but **any future "validated" claim must be re-run on
identity-continuous data.** Record alongside the `11` "exploratory" ceiling.

## 6. Recommended fix (for the dedicated session — NOT started)

1. **Build a successor map** `old_isin → new_isin` from converging signals: (a) the CA
   feed already persisted by `05` (face-value-split subjects), (b) same `symbol` with
   non-overlapping, **consecutive-day** date ranges, (c) the `INE######01NN` issuer-prefix
   match with incrementing suffix. Require ≥2 signals to assert a link; log singletons for
   manual triage (mirror `05`'s `unmatched` audit discipline).
2. **Stitch identity for the sim/signal layer** — choose one:
   - *Canonical-ID column:* add a stable `instrument_id` to `prices_adjusted` that is
     constant across a succession chain; key momentum + holdings on it instead of raw ISIN.
     (Cleanest; larger blast radius — touches `02` signal store + `backtest_v2`.)
   - *Holding remap only:* on a succession ex-date, migrate a held old-ISIN position to the
     new ISIN (rename + the `05` factor already aligns price space). Smaller change; fixes
     ghosts + keeps the book tradeable, but momentum history on the new leg stays truncated.
3. **Re-derive** `prices_adjusted`, re-run `validate.py` (extend with a succession-coverage
   check), then **re-run the `11` warm-start** and re-check shadow-parity.
4. **Re-validation caveat:** acknowledge backtest metrics must be regenerated on the
   stitched data before any "validated" verdict.

## 7. Secondary observations (lower priority, captured here)

- **0-row weekdays are mostly NSE holidays, not gaps:** `2026-03-26, 03-31, 04-03, 04-14,
  05-01, 05-28` are trading holidays — expected (the bhavcopy pipeline tolerates them).
- **Checkpoint vs store max-date mismatch:** `.build_checkpoint.json` marks `2026-06-22`
  "ok" but `prices_adjusted` max date is `2026-06-19` (today's bhavcopy not yet
  published/landed at append time). Cosmetic, but the incremental append should not mark a
  date "ok" when it produced zero stored rows — worth a guard so the checkpoint can't claim
  coverage it doesn't have. **FIXED by T06.0 (2026-06-22):** zero-row days are now marked
  `"empty"` (new status) and never counted as coverage — see §10 T06.0.

## 8. Current operational state (as of 2026-06-22)

- `s3_probation` paper book exists but is in the **degenerate warm-start state** (6 ghost
  holdings, lpd `2026-06-18`). **Do not start the forward probation** until `06` is done;
  the book should be reset + re-warm-started on stitched data.
- **Worker + Celery beat are STOPPED** — the daily post-close job will not auto-fire.
- P11.2 code work (engine-context hoist, hydrate cash-snap, warm-start parity/alert gating,
  `adj_factor` lookup) is complete and test-green (26 `paper_v2` tests); it is sound and
  independent of this data finding — it is what made the warm-start fast enough to surface
  the issue.

---

## 9. Decision (locked 2026-06-22)

**Stitch strategy = canonical `instrument_id` (§6.2 option 1). Holding-remap-only (option 2)
is REJECTED.** Reasons recorded so a cold session does not relitigate:

1. **Remap-only fixes the wrong half for a momentum book.** It cures the can't-*sell* ghost
   but leaves the can't-*buy* blindness — the new leg keeps a truncated momentum history for
   ~the lookback window. The top successions (`IRCTC`, `HDFCBANK`, `BAJFINANCE`, `EICHERMOT`…)
   split *because price ran up*; they are exactly the high-momentum names selection wants, and
   remap-only keeps them invisible right when they are most attractive. Selection blindness is
   the bigger signal distortion than the ghost.
2. **The schema is already shaped for it.** `prices_adjusted` partitions by `isin` and `symbol`
   is *already* allowed to drift ("symbol as of that date"). A chain-constant `instrument_id`
   is the natural third identity column alongside `isin_symbol_map.parquet`. Correct
   architecture, not a workaround.
3. **Remap-first would be wasted work.** The probation has not started — there is no live book
   to keep alive. Canonical-id forces a `prices_adjusted` re-derive + re-warm-start anyway;
   shipping remap first means warm-starting twice and discarding the first.

With a canonical id the held leg *is* the new leg, so **ghosts disappear for free** — remap is
never implemented as a separate thing.

**Re-validation stance (no thumb on the scale).** This is a *correctness* fix, not a tuning
knob. Two effects pull opposite ways on the metrics: momentum truncation *suppressed* reported
returns (fixing → likely return upside); frozen ghosts *dampened* drawdowns (a MTM-frozen dead
leg neither gains nor crashes → reported maxDD likely artificially low; fixing → risk may get
worse). **Net Calmar/Sharpe direction is unknown until re-run.** We fix identity, re-run, and
accept whatever falls out (pre-accepted-null discipline). S3 was already "exploratory, NOT
validated" (`v3/10`,`v3/11`; FINAL_OOS spent) — this does not invalidate a validated claim
(there is none); it removes a known contaminant so any *future* verdict is trustworthy.

---

## 10. Task breakdown — independent cold sessions

Designed so each task is a self-contained cold session: clear inputs, deliverables, and a
**verifiable** success gate. Honor the project laws throughout — **idempotency** (re-running a
task must not double-write or corrupt), **checkpoint/resume**, **tests mock all external feeds**
(no live NSE/yfinance), **regression-first** (each fix ships a failing-then-green test). The
`prices_adjusted`/`isin_symbol_map` store is an **Arrow/parquet dataset** (not Postgres) — the
"migrations are holy" law applies to the `paper_v2` Postgres schema in T06.5, not to the parquet
store (which is rebuilt by re-derive).

**Dependency chain:** `T06.1 → T06.2 → T06.3 → T06.4 → T06.5 → T06.6`. T06.1 is the unconditional
gate; nothing downstream is meaningful without an audited map. T06.0 is an optional independent
cleanup that can run any time.

---

### T06.0 — (optional, independent) checkpoint-coverage guard

**Goal.** Close the §7 cosmetic gap: the incremental append marks a date `"ok"` in
`.build_checkpoint.json` even when it stored **zero rows** (e.g. `2026-06-22` "ok" while
`prices_adjusted` max date is `2026-06-19`).

- **Inputs.** `backend/app/data/bhavcopy/incremental.py`, the checkpoint writer.
- **Steps.** Guard the checkpoint write so a date is only marked `"ok"` when it produced
  > 0 stored rows (or is a confirmed NSE holiday via the existing holiday set from §7);
  otherwise mark `"empty"`/skip so coverage cannot be over-claimed.
- **Deliverable.** Guard + a regression test feeding a zero-row append and asserting the date is
  **not** marked covered.
- **Success gate.** New test red-before/green-after; existing `incremental` tests stay green.
- **Out of scope.** Anything about ISIN identity — this is a pure bookkeeping fix. Sequence it
  whenever; not on the T06.1→…→6 critical path.

> **T06.0 DONE — 2026-06-22.** Root cause located: `build._process_day` marked a day `"ok"`
> whenever the download+parse succeeded — **even when the parsed frame was empty** (the
> "write per-day parquet even if empty" path). A not-yet-final EOD file that parses to zero
> in-scope EQ rows therefore claimed coverage while `prices_adjusted` stored nothing — exactly
> the §7 `2026-06-22 "ok"` vs max-date `2026-06-19` over-claim. (The 404 path already correctly
> marked `"missing"`, so NSE holidays were never the over-claim source — no holiday set needed.)
> **Fix:** new `_STATUS_EMPTY = "empty"` status — a zero-row day is recorded but **never counted
> as coverage** (`BuildReport.days_empty`, surfaced in `summary()`); it is terminal-on-resume like
> `"missing"` (its cached `.zip` is reused by `download` anyway, so re-parsing every run buys
> nothing) — consistent with the existing idempotency model, not a new re-fetch path. **Tests:**
> `TestZeroRowCoverageGuard` in `tests/data/test_bhavcopy_build.py` — red-before/green-after on a
> valid-zip-but-zero-EQ-row day (asserts checkpoint is `"empty"`, not `"ok"`; row not stored) +
> a resume-idempotency test (stays `"empty"`, not double-counted, no network). **177 data-suite
> tests green** (was 175; +2). No ISIN-identity work — pure bookkeeping, per the guardrail.

---

### T06.1 — Build + audit the successor map  *(unconditional gate)*

**Goal.** Produce an audited, persisted `old_isin → new_isin` map keyed by converging signals,
mirroring `05`'s `unmatched`-audit discipline.

- **Inputs.**
  - CA feed already persisted by `05` (face-value-split subjects) — `corporate_actions.py` /
    the events tables in `store.py`.
  - `instrument_lifetimes` (`isin, symbol, first_date, last_date`) for consecutive-day range
    detection.
  - `isin_symbol_map.parquet` for issuer-prefix (`INE######01NN`) matching.
- **Steps.**
  1. Generate candidate links from three signals: (a) same `symbol`, non-overlapping
     **consecutive-day** date ranges (`old.last_date` → `new.first_date` next trading day);
     (b) `INE######01NN` issuer-prefix match with **incrementing** suffix; (c) a
     face-value-split CA event under the old ISIN near the transition date.
  2. **Assert a link only with ≥2 converging signals.** Resolve multi-hop chains (A→B→C) with
     union-find so each chain has one root.
  3. Log singletons / conflicts to an `unmatched` audit artifact for manual triage.
- **Deliverables.**
  - `successor_map.parquet` (alongside `isin_symbol_map.parquet`): `old_isin, new_isin,
    signals_matched (list/count), asserted (bool), transition_date`.
  - `successor_unmatched.parquet` (or log) for singletons/conflicts.
  - A builder module under `backend/app/data/bhavcopy/` (e.g. `succession.py`).
- **Success gate (verifiable against §3 blast radius).** Asserted links reproduce the measured
  counts: **406** sequential ISIN-change events, **388** symbols with >1 ISIN, **150** liquid
  (≥₹5cr ADV) old legs flagged ghost-risk. The 6 warm-start names (§2) classify correctly:
  BAJFINANCE/MCX/NAZARA/EASEMYTRIP → asserted succession; HDFC (HDFC-Bank merger) and
  TATAMTRDVR (DVR cancel) → **not** asserted (legit terminations, no successor).
- **Tests.** Fixture-driven (synthetic CA + lifetime rows); assert ≥2-signal gating, multi-hop
  chain collapse, and that a merger/cancellation is excluded.
- **Guardrails.** No schema change to `prices_adjusted` yet. No engine/signal edits. Read-only
  over the existing store; only writes the two new artifacts. Idempotent rebuild.

> **T06.1 DONE — 2026-06-22.** See §11 for the build results + verification against the §3
> blast radius. Gate met: all measured counts reproduced and the 6 warm-start names classify
> correctly. Artifacts `successor_map.parquet` (406 rows, 333 asserted) + `successor_unmatched.parquet`
> (73 rows) written; builder `backend/app/data/bhavcopy/succession.py`; store I/O + schemas in
> `store.py`; 8 fixture tests in `tests/data/test_bhavcopy_succession.py` (175 data-suite green).

---

### T06.2 — Add `instrument_id` + re-derive `prices_adjusted`

**Goal.** Materialize the chain-constant identity column and rebuild the price store on it.

- **Inputs.** `successor_map.parquet` (T06.1); `store.py` (`PRICES_ADJUSTED_SCHEMA`,
  `ISIN_MAP` schema, read/write paths); `adjust.py`; `build.py`.
- **Steps.**
  1. Define `instrument_id` = the **root (oldest) ISIN** of each succession chain;
     standalone ISINs get `instrument_id == isin` (so non-succession rows are unchanged).
  2. Add `instrument_id` (string) to `PRICES_ADJUSTED_SCHEMA` and `isin_symbol_map`. Keep `isin`
     as partition column (do not re-partition — avoids a full physical reshuffle; `05`'s
     `adj_factor` already aligns price space across the chain).
  3. Re-derive `prices_adjusted` end-to-end (`build.py`) so every row carries its
     `instrument_id`. Extend `read_prices_adjusted` to optionally filter/group by it.
- **Deliverable.** Re-derived `prices_adjusted` + updated `isin_symbol_map` with `instrument_id`;
  store read/write code + schema updated.
- **Success gate.** (a) Non-succession ISINs are **byte-identical** to pre-change (regression
  parity — same discipline as the `floor`-path parity suite). (b) For each of the 4 asserted
  warm-start successions, querying the chain's `instrument_id` returns one **continuous** price
  series spanning old+new `first_date..last_date` with no gap at the transition. (c) Row count
  conserved (no drops/dupes).
- **Tests.** Parity test on a standalone ISIN; continuity test on a synthetic 2-leg chain
  (assert single unbroken series under `instrument_id`); idempotent re-derive.
- **Guardrails.** Signal/engine layers untouched in this task — they still key on `isin` and must
  keep passing. This task only *adds* the column + the continuous read path.

> **T06.2 DONE — 2026-06-22.** See §12 for results + verification. Gate met: standalone ISINs
> byte-identical on every original column, the 4 warm-start chains read back as one continuous
> series under a single `instrument_id`, row count conserved (4,020,618). Signal/engine layers
> untouched and green (606 `paper_v2`+`backtest_v2` tests pass with the added column).

---

### T06.3 — Re-key signal/factor + engine identity onto `instrument_id`

**Goal.** Make momentum and the holdings/position key continuous across a succession.

- **Inputs.** `signals.py`, `signals_v3.py`, `factors.py`, `engine.py` (SignalStore, fill model,
  positions), `portfolio.py`; re-derived store (T06.2).
- **Steps.**
  1. Factor computation (`mom_12_1` etc.) groups price history by `instrument_id` so the
     concatenated chain feeds the lookback — the new leg is no longer momentum-blind.
  2. Position/holdings identity collapses to `instrument_id`; **fills still execute on the
     live `isin`** for the trade date (whatever symbol/ISIN is trading), but a held position
     carried across a transition resolves to the same `instrument_id` → no ghost.
  3. Universe membership + ADV gating continue to evaluate on the live `isin`/date.
- **Deliverable.** Signal + engine layers keyed on `instrument_id` for identity, on live `isin`
  for execution.
- **Success gate.** (a) On the 4 warm-start successions, `mom_12_1` is **defined and continuous**
  through the transition (no ~lookback-length NaN gap on the new leg). (b) A position held across
  a transition is **sellable** the next rebalance (no "fill dropped, position carried"). (c) For a
  universe with **zero** successions, results are byte-identical to pre-change (parity guard).
- **Tests.** Regression: a backtest over a 2-leg chain holds → succeeds → sells cleanly (the §2
  ghost reproduced red, then green); momentum-continuity assertion; no-succession parity.
- **Guardrails.** This is the big blast radius — keep the change *surgical* and behind the
  `instrument_id` resolution join; do not refactor adjacent factor/engine code (Rule 3).

> **T06.3 DONE — 2026-06-22.** See §13 for the implementation + verification. All three
> success gates met (momentum continuity, held-position sellable / ghost red→green,
> no-succession parity byte-identical). Implemented as a **single resolution join**
> (`backtest_v2/identity.collapse_to_instrument_id`) threaded through the four
> identity-consuming primitives; **606→** full suites green (798 `backtest_v2`+`paper_v2`+`data`).
> No FINAL_OOS interaction; the re-measure is T06.6.

---

### T06.4 — Extend `validate.py` with a succession-coverage check + re-validate the store

**Goal.** A data-layer gate that fails loud if identity continuity regresses.

- **Inputs.** `validate.py`; `successor_map.parquet`; re-derived store (T06.2/T06.3).
- **Steps.** Add a check: every asserted succession chain resolves to exactly one
  `instrument_id` with a gap-free price series across the transition; flag any asserted old leg
  whose successor is missing from `prices_adjusted`. Run full `validate.py` on the re-derived
  store.
- **Deliverable.** New validator check + a clean validation run report.
- **Success gate.** `validate.py` passes on the re-derived store; the new check **fails** on a
  deliberately broken fixture (un-stitched chain). 150 liquid ghost-risk legs all resolve.
- **Tests.** Fixture with one stitched + one broken chain; assert pass/fail respectively.
- **Guardrails.** Validator is read-only; it reports, it does not mutate the store.

> **T06.4 DONE — 2026-06-22.** See §14 for the implementation + verification. All success
> gates met: `validate.py` passes on the re-derived store; the new check fails on three
> deliberately broken fixtures; 146/146 liquid ghost-risk legs resolve (note: 146 asserted
> liquid, 4 non-asserted liquid legs remain in `successor_unmatched` for manual triage —
> the 150 §3 count includes those 4 which cannot be validated automatically). **194 data-suite
> tests green** (was 184; +10). 0 regressions in `backtest_v2`+`paper_v2` suites.

---

### T06.5 — Reset + re-warm-start the `v3/11` paper book on stitched data

**Goal.** Replace the degenerate book (6 ghosts, ₹2.63M idle) with a clean inception→latest
warm-start on identity-continuous data, and re-prove fidelity.

- **Inputs.** `app/paper_v2/{incremental,live_engine,parity,s3_config}`, the `paper_v2` Postgres
  schema, the re-derived store + re-keyed engine (T06.2–T06.4).
- **Steps.**
  1. **Reset** the `s3_probation` paper book (truncate/re-init `paper_v2` rows — this is the
     Postgres side; any schema touch needs an **Alembic migration**, per the law).
  2. Re-run the inception→latest warm-start (`incremental.py`, inception-anchored append) on the
     stitched data.
  3. Re-check **shadow-parity** vs a from-scratch `backtest_v2` (`parity.py`).
- **Success gate.** Warm-started book is a **full ~20-name momentum portfolio** (not 6 ghosts,
  not idle cash); **shadow-parity `max_dev_bps ≈ 0.0`** holds on the stitched data; **0 ghost /
  unsellable holdings**. Worker + beat remain **STOPPED** (probation does not auto-start here).
- **Tests.** Warm-start integration test asserting holdings count > 6 and no carried-unsellable
  position; parity assertion.
- **Guardrails.** Do **not** start the forward probation in this task (that is a later `11`
  decision). Any `paper_v2` schema change → Alembic migration. Keep worker/beat stopped.

> **T06.5 DONE-FOR-SCOPE — 2026-06-22.** See §15 for the full results + diagnostic. The
> §2 degeneracy caused by the **4 face-value-succession ghosts** is eliminated and the book
> fills to a full ~20-name portfolio in risk-on regimes (peak 23; ≥18 names on 1,569/2,336
> days); shadow-parity holds at **0.0 bps** on the stitched data. **Two honest caveats keep
> this from a clean literal-gate pass (Rule 7/Rule 12):** (a) the warm-start *edge*
> (2026-06-18) is mostly-cash because the regime overlay is genuinely **risk-off** (Nifty 50
> 24,013 < 200-DMA 24,897; 60/60 of the last days risk-off; parity-confirmed = true S3
> state, not a contamination artifact); (b) **3 NEW carried ghosts remain — HDFC, TATAMTRDVR,
> INOXLEISUR — all share-swap MERGERS / DVR-cancellations, a DISTINCT identity defect
> explicitly OUT of T06's face-value-succession scope.** No schema change ⇒ no migration;
> reset was pure row-deletion. Worker + beat left STOPPED (only the `db` container was
> started). New integration test `tests/paper_v2/test_v3t06_5_warmstart_succession.py`
> (green/red on a synthetic chain) — 28 `paper_v2` tests green.

---

### T06.6 — Re-run the backtest + record the re-validation caveat

**Goal.** Regenerate S3's metrics on identity-continuous data and record the result honestly.

- **Inputs.** Re-keyed `backtest_v2` (T06.3), the S3/`10`/`11` frozen config.
- **Steps.** Re-run the S3 backtest on stitched data; compare Calmar/Sharpe/maxDD/retention vs the
  identity-broken numbers; write the delta into this doc (and the v3/11 record) with the §9
  re-validation stance (direction was pre-declared unknown).
- **Deliverable.** A short results note appended here: old vs new metrics, sign of each move,
  and the explicit statement that this is a *correctness re-measure*, not a re-validation (FINAL_OOS
  stays spent; a real validation still needs new OOS data + a fresh prereg).
- **Success gate.** Metrics regenerated and recorded with no rule-relaxation and no target-chasing;
  whatever the numbers do is reported as-is (incl. if Calmar drops because frozen-ghost
  drawdown-dampening is removed).
- **Guardrails.** **No** new "validated/deployable" claim from this run. Do not consume or
  re-open FINAL_OOS. This closes the §5 contamination as *measured*, nothing more.

---

### Done-criteria for `06`

`06` is complete when: T06.1–T06.6 are green; `validate.py` enforces succession coverage; the
`v3/11` paper book is warm-started clean on stitched data with parity ≈ 0.0 bps and zero
**succession** ghosts; and the re-measured S3 metrics are recorded with the re-validation caveat.
Only then is the forward probation eligible to start (a separate `11` decision). T06.0 is
independent and may land anytime.

> **Scope amendment (2026-06-22, from T06.5 — §15).** "Zero ghosts" is met **for T06's
> face-value-succession scope** (the 4 §2 ghosts are gone). T06.5 surfaced a *distinct*
> identity defect — **share-swap merger / DVR-cancellation** ghosts (HDFC, INOXLEISUR,
> TATAMTRDVR) — that `06` never claimed to fix and cannot fix with a successor map (no
> face-value successor exists). Those 3 remain in the warm-started book and MTM-freeze
> ~₹315K. **Before the `11` probation is armed**, the merger-identity defect needs its own
> spec (a merger-ratio remap onto the acquirer / write-off on cancellation), the same way
> `05` spawned `06`. This is NOT a `06` blocker — it is the next layer.

---

## 11. T06.1 results (2026-06-22)

**Built + audited the successor map.** Read-only over the existing store; wrote two new artifacts;
no `prices_adjusted` schema change, no engine/signal edits (per the T06.1 guardrails).

### What shipped
- **`backend/app/data/bhavcopy/succession.py`** — pure, fixture-testable signal functions
  (`signal_consecutive` / `signal_prefix` / `signal_ca_split`), `_resolve_roots` (union-find,
  root = oldest ISIN), `build_successor_map` (the assemble + assert + conflict-guard step), and a
  `run_succession_build(root)` store wrapper. Idempotent (overwrites the two parquets).
- **`store.py`** — `SUCCESSOR_MAP_SCHEMA` / `SUCCESSOR_UNMATCHED_SCHEMA` + read/write I/O, matching
  the existing `corporate_actions` / `ca_unmatched` convention.
- **`tests/data/test_bhavcopy_succession.py`** — 8 tests (≥2-signal gating, CA-as-2nd-signal,
  multi-hop chain collapse to oldest root, merger/cancel exclusion, fork→unmatched conflict guard,
  liquidity flag, store round-trip, idempotent rebuild). **175 data-suite tests green.**

### Signals (assert only on ≥2 converging — mirrors `05`'s unmatched-audit discipline)
1. **`sig_consecutive`** — old leg's `last_date` is the trading day immediately before the new
   leg's `first_date` (calendar derived from `universe_membership`). Fired on 356/406.
2. **`sig_prefix`** — shared `isin[:9]` issuer prefix **and** the `isin[9:11]` two-digit security
   suffix strictly increments (e.g. `INE296A01`**02**`4 → INE296A01`**03**`2`). Fired on 345/406.
3. **`sig_ca_split`** — a face-value-split CA event (from the `05` feed) filed under the **old**
   ISIN within ±15 days of the transition. Fired on 290/406.

Asserted edges are collapsed with union-find so each chain (A→B→C) has one root = the oldest ISIN
(`root_isin`, what T06.2 materialises as `instrument_id`).

### Verification against the §3 blast radius — **all counts reproduced exactly**
| Metric | §3 expected | Measured | ✓ |
|---|---|---|---|
| Symbols with >1 ISIN | 388 | 388 | ✓ |
| Sequential ISIN-change candidate pairs | 406 | 406 | ✓ |
| New leg since 2024 | 168 | 168 | ✓ |
| **Liquid old legs (ghost-risk)** | **150** | **150** | ✓ |
| Liquid **and** recent (≥2024) | 79 | 79 | ✓ |

> **Liquidity definition pinned down:** the §3 "150 liquid" count is reproduced only by
> `adv_20` **on the old leg's last trading day** ≥ ₹5cr — *not* max/median over its life
> (those give 236/78). This is the correct ghost-risk measure: was the position S3-eligible at
> the moment the ISIN died and it became unsellable. Recorded so T06.4's "150 liquid legs all
> resolve" check uses the same definition.

### Map output
- **`successor_map.parquet`** — 406 candidates, **333 asserted** (≥2 signals), **146** of those
  liquid ghost-risk. 14 multi-hop chains (max 3 legs). 0 conflicts/forks in the real data.
- **`successor_unmatched.parquet`** — 73 candidates (70 single-signal + 3 ETF re-orgs with 0
  signals: `AXISGOLD`/`AXISNIFTY`/`ICICINXT50`, all `INF…` fund ISINs — correctly excluded).
- **4 liquid old legs are NOT asserted** (only 1 signal) — left in `unmatched` for triage rather
  than asserted on thin evidence (Rule 12 — surface, don't infer).

### 6 warm-start names (§2) — classify correctly
| Symbol | old → new | signals | asserted | root |
|---|---|---|---|---|
| BAJFINANCE | `INE296A01024 → INE296A01032` | 2 (consecutive+prefix) | ✓ | `INE296A01024` |
| MCX | `INE745G01035 → INE745G01043` | 3 | ✓ | `INE745G01035` |
| NAZARA | `INE418L01021 → INE418L01047` | 3 | ✓ | `INE418L01021` |
| EASEMYTRIP | `INE07O001018 → INE07O001026` | 3 | ✓ | `INE07O001018` |
| HDFC | (merged into HDFC Bank) | — | **not asserted** (no successor pair) | — |
| TATAMTRDVR | (DVR cancelled) | — | **not asserted** (no successor pair) | — |

T06.1 success gate **MET**. Next on the critical path: **T06.2** (add `instrument_id` +
re-derive `prices_adjusted`). No FINAL_OOS interaction; no validation claim made here.

---

## 12. T06.2 results (2026-06-22)

**Materialised the chain-constant `instrument_id` and re-derived the on-disk store on it.** The
column is a pure function of `isin` × the (T06.1) successor map, so this is a *correctness*
column-add, not a re-computation — every other column is preserved byte-for-byte. No
engine/signal edits (those are T06.3); the layers still key on `isin` and stay green.

### What shipped
- **`store.py`** — `instrument_id` (string) appended to **`PRICES_ADJUSTED_SCHEMA`** and
  **`ISIN_SYMBOL_MAP_SCHEMA`**; `read_prices_adjusted` gained an **`instrument_ids`** filter that
  selects a whole succession chain (row-group predicate on `instrument_id`, not a partition prune
  — `isin` stays the partition column, so the physical layout is unchanged, per the §10 guardrail).
- **`succession.py`** — `instrument_id_map(successor_map)` (asserted chains only → `isin: root`,
  multi-hop collapsed) and `rederive_instrument_id(root)`: reads the existing partitioned store
  directly (the new reader enforces the post-T06.2 schema the pre-migration files lack), attaches
  the column, and rewrites through the conforming writer. Faithful + network-free + idempotent.
- **`universe.py`** — `build_universe(adjusted_df, instrument_id_by_isin=None)` now emits
  `instrument_id` on both prices and `isin_symbol_map` (identity when no map ⇒ a build with no
  succession map is byte-identical on every other column).
- **`build.py`** — Stage 5–6 reads any existing `successor_map` and passes the id-map to
  `build_universe`, so **future full rebuilds and incremental appends** (`incremental.py` delegates
  to `run_build`) carry `instrument_id` natively — no separate migration needed going forward.
- **Tests** — `tests/data/test_bhavcopy_instrument_id.py` (10 tests: map chain-collapse,
  `build_universe` identity-vs-collapse, **parity** on a standalone ISIN, **continuity** on a 2-leg
  chain via the `instrument_ids` read, **idempotent** re-derive against a store written *without*
  the column). Store/universe/validate/succession fixtures updated for the new schema.
  **184 data-suite tests green** (was 177; +7). **606 `paper_v2`+`backtest_v2` tests green** — the
  added column is transparent to the signal/engine/paper layers (T06.2 guardrail verified).

### Re-derive of the real store — success gate **MET**
| Gate | Result |
|---|---|
| (c) Row count conserved | **4,020,618 → 4,020,618** (no drops/dupes) |
| (a) Standalone ISIN byte-identical | `INE002A01018`: all 15 original columns identical; `instrument_id == isin` |
| (b) Chain continuity (4 warm-start names) | each reads back as **one** `instrument_id` spanning **both** legs, gap-free |

```
BAJFINANCE INE296A01024→…032  one_id  2086+250=2336 rows  2017-01-02..2026-06-19
MCX        INE745G01035→…043  one_id  2224+112=2336 rows  2017-01-02..2026-06-19
NAZARA     INE418L01021→…047  one_id  1054+178=1232 rows  2021-03-30..2026-06-19
EASEMYTRIP INE07O001018→…026  one_id   357+881=1238 rows  2021-03-19..2026-06-19
```

`rederive_instrument_id` summary: **319 chains** (= 333 asserted edges − 14 multi-hop collapses),
**652 ISINs** stitched onto a root (= 333 edges + 319 roots). `isin_symbol_map` upgraded too
(3,795 rows; 341 stitched leg-rows; `instrument_id == isin` preserved for every non-chain ISIN).

T06.2 success gate **MET**. Next on the critical path: **T06.3** (re-key signal/factor + engine
identity onto `instrument_id` — the big blast radius). No FINAL_OOS interaction; no validation
claim made here (re-measure is T06.6).

---

## 13. T06.3 results (2026-06-22)

**Re-keyed the signal/factor + engine identity onto `instrument_id`.** The big-blast-radius
task landed as the *smallest possible* change — Rule 3, "behind the `instrument_id` resolution
join" (§10 guardrail): **one** join function, applied at four entry points, no refactor of the
factor/engine internals, no `precompute_v3_signals` / `s3_config` / `portfolio.py` edit.

### The key insight (why this is a relabel, not a rewrite)
A succession's two legs trade on strictly **date-disjoint, consecutive** ranges (§3, verified in
T06.1) and `05` already aligned their price space via `adj_factor`. So *relabelling* the identity
column from raw `isin` to the chain-constant `instrument_id` is sufficient — on any given date
exactly one leg is live, so:
- every per-date lookup (`open`/`close`/`close_tr`/`adv_20`) and the universe-membership set
  resolve to **that live leg** automatically (execution still happens at the live leg's prices);
- the per-instrument *time series* (momentum, EMA, vol) becomes the **gap-free concatenation** of
  both legs (the new leg is no longer momentum-blind);
- a held position keyed on `instrument_id` is carried across the transition as the **same key**
  → it is sellable at the live leg's open → **no ghost**.

### What shipped
- **`backend/app/backtest_v2/identity.py`** — new `collapse_to_instrument_id(prices)`: relabels
  `isin → instrument_id`; **no-op** (returns the input object) when the column is absent (pre-T06.2
  frames) or `instrument_id == isin` for every row (no succession); **fails loud** (Rule 12) if
  collapsing yields overlapping `(isin, date)` rows (a §3 consecutive-day-invariant violation that
  would silently corrupt the concatenated series). Never mutates the caller's frame.
- **Self-collapsing primitives** (each calls the join at its top, idempotent + tolerant, so any
  caller — `precompute_v3_signals`, `s3_config`, `r10_oos`, `floor` — gets consistent identity for
  free with zero edits to *those* callers):
  - `signals.precompute_signals` → continuous gate inputs (EMA_200, momentum_12_1) per chain.
  - `factors.composite_rank` → composite columns are chain-constant; each factor's lookback spans
    both legs.
  - `stable_universe.build_stable_universe_mask` → one continuous membership per chain (adv_20 on
    each review day is still the live leg's).
  - `engine.build_context` → price lookups / membership / positions all key on `instrument_id`
    (resolves the ghost + the live-leg execution).
- **Tests** — `tests/backtest_v2/test_v3t06_3_instrument_identity.py` (8 tests):
  - **gate (a)** momentum continuity — stitched chain has a *defined* `momentum_12_1` 3 days into
    the new leg; the raw-isin frame has `NaN` there (the bug, asserted red);
  - **gate (b)** held-position sellable — full backtest over a 2-leg chain: stitched ⇒ bought then
    **sold cleanly, 0 final positions**; raw-isin ⇒ the OLD leg is bought then becomes a **frozen
    ghost** (1 final position, logged to `suspension_log`) — the §2 ghost reproduced red→green;
  - **gate (c)** parity — adding `instrument_id == isin` to a no-succession universe leaves the
    equity curve and every fill **byte-identical**;
  - the `collapse` contract (two no-op cases, relabel, fail-loud-on-overlap).

### Success gate — **MET**
| Gate | Result |
|---|---|
| (a) momentum defined + continuous through the transition | ✓ (stitched defined; raw-isin NaN — bug shown) |
| (b) held position sellable across a transition (no ghost) | ✓ green (0 ghosts) / red (ghost reproduced) |
| (c) zero-succession universe byte-identical | ✓ (full equity curve + fills identical) |
| No-regression on the existing parity suites | ✓ **798 passed** (`backtest_v2`+`paper_v2`+`data`), 0 failures |

### Notes / carried forward
- **Fill labelling.** A fill carried across a succession is *labelled* with `instrument_id`, not
  the raw live ISIN. Economically identical for the backtest; the **live paper book (T06.5)** maps
  `instrument_id → tradeable ISIN/symbol` (via `sym_map`, latest = new leg) for order placement.
- **Perf (T06.6).** Each of the four primitives collapses independently → up to 4 transient copies
  of the ~4M-row real frame on a full run (zero copies on the no-op path). If T06.6's real re-run
  is memory-bound, collapse once upstream and pass the collapsed frame down — the primitives stay
  correct either way (idempotent). Not optimised now (no real run in T06.3; Rule 2).

T06.3 success gate **MET**. Next on the critical path: **T06.4** (extend `validate.py` with a
succession-coverage check). No FINAL_OOS interaction; no validation claim made here (re-measure is
T06.6).

---

## 14. T06.4 results (2026-06-22)

**Extended `validate.py` with a succession-coverage check (Check 8) and ran full validation on
the re-derived, identity-continuous store.** Validator is read-only; it reports but never mutates
the store (per the T06.4 guardrail).

### What shipped

- **`backend/app/data/bhavcopy/validate.py`** — Check 8 (`_check_8_succession_coverage`):
  for every asserted `old → new` edge in `successor_map.parquet`, enforces three gates:
  (1) the new leg's ISIN must be present in `prices_adjusted` (else the old leg becomes a
  ghost with no forward prices); (2) the old leg's `instrument_id` must equal `root_isin`
  (catches multi-hop middle legs that weren't re-derived); (3) the new leg's `instrument_id`
  must equal `root_isin` (the primary T06.2 correctness invariant — a new leg carrying its
  own raw ISIN means T06.2 wasn't applied and the leg is momentum-blind). Skips gracefully
  (noted in `report.checks_skipped`) when `successor_map` is absent (pre-T06.1 stores) or
  contains no asserted links. `ValidationReport` extended with three new fields:
  `succession_chains_asserted`, `succession_liquid_ghost_risk`, `succession_liquid_resolved`;
  `print_coverage()` surfaces them when non-zero. `run_validation` reads `successor_map` from
  the store and calls the new check between Check 7 and the coverage print.
- **`tests/data/test_bhavcopy_validate.py`** — 10 new tests in `TestCheck8SuccessionCoverage`
  and `TestRunValidationCheck8Integration`:
  - `test_stitched_chain_passes` — both legs + correct `instrument_id` → no raise; report
    counts verified.
  - `test_broken_missing_new_isin_fails` — new leg absent → `AssertionError("check_8")`.
  - `test_broken_wrong_instrument_id_mid_leg_fails` — multi-hop middle leg with stale
    `instrument_id` → `AssertionError("check_8")` (tests the old-leg gate on the non-trivial
    B→C edge where `old_isin ≠ root_isin`).
  - `test_broken_wrong_instrument_id_new_leg_fails` — new leg `instrument_id` not updated →
    `AssertionError("check_8")`.
  - `test_no_map_skips_gracefully` — empty map → skip, noted in report.
  - `test_unasserted_links_ignored` — non-asserted candidate → skip (Rule 12: don't validate
    what was never asserted).
  - `test_liquid_ghost_risk_counts` — two asserted edges (one liquid, one non-liquid) →
    report counts are accurate.
  - End-to-end `TestRunValidationCheck8Integration`: stitched-chain passes, unstitched fails
    at full `run_validation` level, no-map skips.

### Real store validation run — success gate **MET**

```
=== Data Layer Coverage Report ===
  Rows:              4,020,618
  Distinct ISINs:    3,472
  Delisted ISINs:    741
  Date range:        2017-01-02 → 2026-06-19
  Days with gaps:    5.4%
  CA events:         (not supplied)
  Succession chains: 333 asserted (146/146 liquid ghost-risk legs resolved)
==================================
```

All 7 pre-existing checks pass + the new Check 8 is clean. **No checks skipped.**

| Gate | Result |
|---|---|
| `validate.py` passes on re-derived store | ✓ |
| New check fails on broken fixture (missing new leg) | ✓ red-before / green-after |
| New check fails on broken fixture (wrong `instrument_id` new leg) | ✓ red-before / green-after |
| New check fails on broken fixture (multi-hop mid-leg not stitched) | ✓ red-before / green-after |
| **Liquid ghost-risk legs resolved** | ✓ **146/146** |
| No-regression (data suite) | ✓ **194 passed** (was 184; +10) |
| No-regression (`backtest_v2`+`paper_v2`) | ✓ (verified) |

> **Liquid count note.** The §3 "150 liquid ghost-risk legs" includes 4 non-asserted liquid
> old legs (in `successor_unmatched`, left for manual triage per Rule 12). Check 8 validates
> only asserted links — 146 of the 150. The 4 unmatched are correctly surfaced in the audit
> artifact, not silently checked in.

T06.4 success gate **MET**. Next on the critical path: **T06.5** (reset + re-warm-start the
`v3/11` paper book on stitched data). No FINAL_OOS interaction; no validation claim made here
(re-measure is T06.6).

---

## 15. T06.5 results (2026-06-22)

**Reset the degenerate `s3_probation` book and re-warm-started it inception→edge on the
identity-continuous (stitched) store.** Faithful to `tasks.execute_paper_daily_task`'s replay
loop, minus the live `incremental_append` (the store was already re-derived to the latest
published bhavcopy by T06.2, so there was nothing to append — this avoids a live NSE fetch and
keeps the run deterministic). Reset was **pure row-deletion** (positions + pending fills +
cash/lpd back to inception) → **no schema change, no Alembic migration** (per the §10
guardrail; the migrations-are-holy law applies to schema, not data). Only the `db` container
was started; **worker + Celery beat remain STOPPED** — the forward probation does NOT
auto-start (a later `11` decision).

### What ran
- `backend/scripts/t06_5_rewarmstart.py` — reset → warm-start replay → shadow-parity.
- `backend/scripts/t06_5_diagnose.py` — from-scratch S3 backtest capturing the n_positions /
  cash% trajectory + regime + `suspension_log` membership (to explain the edge state).
- `tests/paper_v2/test_v3t06_5_warmstart_succession.py` — **GREEN/RED** integration tests on a
  synthetic succession panel run through the real warm-start loop: green ⇒ full book (>6),
  the chain held across the split is carried as **one** `instrument_id` (sellable, no ghost),
  shadow-parity passes; red ⇒ the same chain on the pre-fix raw-isin shape becomes the §2
  unsellable ghost. **28 `paper_v2` tests green** (was 26; +2).

### Re-warm-start of the real book
```
[BEFORE] cash=2,633,583.82  lpd=2026-06-18  positions=6
         EASEMYTRIP, HDFC, TATAMTRDVR, BAJFINANCE, NAZARA, MCX   (4 succession + 2 merger)
[RESET ] cash=1,000,000.00  lpd=None        positions=0
[REPLAY] 2,335 confirmed days 2017-01-02 → 2026-06-18  (113 rebalances)
[AFTER ] cash=2,626,816.45  lpd=2026-06-18  positions=3  equity=2,941,923.84
         HDFC, INOXLEISUR, TATAMTRDVR                          (3 merger/cancel ghosts)
[PARITY] PASS  max_dev=0.0 bps  (engine names=3 == live names=3)
```

### Why the edge book is mostly-cash + 3 ghosts (diagnostic, from-scratch backtest)
The literal success gate ("full ~20-name book, 0 ghosts") evaluated **at the edge** reads
FAIL — but the diagnostic shows the gate's *premise* (a clean warm-start ⇒ ~20 names at the
edge) conflated two independent causes. Surfaced honestly (Rule 7/Rule 12):

| Finding | Evidence |
|---|---|
| **Book DOES fill to a full ~20-name portfolio in risk-on regimes** | peak **23** positions; **≥18 names on 1,569 / 2,336 days**; 0% cash through the body — 2021-12-31: 21 names; 2023-12-29: 22; 2025-12-31: 23 |
| **The edge (2026-06-18) is a genuine RISK-OFF regime** — cash is *correct* | Nifty 50 **24,013 < 200-DMA 24,897**; **60/60** of the last 60 trading days risk-off. (Same signature as 2020-03-31 COVID: 0 positions, 100% cash.) Parity 0.0 bps ⇒ this is the **true S3 state**, not a warm-start artifact |
| **The 4 face-value-succession ghosts (§2) are ELIMINATED** | BAJFINANCE / MCX / NAZARA / EASEMYTRIP **never appear** in `suspension_log` — T06 fixed exactly what it targeted |
| **3 remaining ghosts are share-swap MERGERS / cancellations — OUT of T06 scope** | HDFC→HDFCBANK (carried 2023-07-13→edge, 722 d), INOXLEISUR→PVRINOX (2023-02-17→edge, 819 d), TATAMTRDVR DVR-cancel (2024-08-30→edge, 445 d). The holder's value migrated to a **different entity's** shares (acquirer) or was cancelled — there is **no face-value successor pair**, so T06's map correctly does not assert them |

### Verdict & honest caveat (Rule 12 — fail loud)
- **Core objective MET:** the §2 succession-ghost degeneracy is gone; the book is a full
  ~20-name portfolio whenever the regime is risk-on; shadow-parity is **0.0 bps** on stitched
  data (fidelity preserved end-to-end). The succession half of the spec-06 root cause is closed.
- **Literal edge-gate not cleanly met,** for two reasons that are NOT T06 failures: (a) the
  end date is a true risk-off window (cash is the correct S3 behaviour), and (b) a **newly
  surfaced, out-of-scope merger/cancellation identity defect** leaves 3 stuck ghosts.
- **New follow-up flagged (NOT in `06`):** share-swap-merger / DVR-cancellation identity is a
  *distinct* remediation from face-value succession (it needs a merger-ratio remap onto the
  acquirer's instrument, e.g. HDFC→HDFCBANK, or a write-off on cancellation). It is the same
  pattern by which `05` spawned `06`: a real defect uncovered downstream that warrants its own
  spec. **Operationally it matters before the probation starts** — those 3 ghosts MTM-freeze
  ~₹315K (equity − cash) of dead capital and would contaminate the forward returns. Recommend a
  new spec (`07`-style) for merger identity before the `11` probation is armed.

No FINAL_OOS interaction; no validation claim made here (the metric re-measure is T06.6).
