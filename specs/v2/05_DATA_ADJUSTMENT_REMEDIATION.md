# Spec 05 — Split/Bonus Adjustment Remediation (data-layer bug found by the T1 floor)

> **Status:** Phase 0 COMPLETE (2026-06-16). Phase 1 shape revised by findings. No data changed yet.
> **Owner:** Arafat. **Created:** 2026-06-16.
> **Trigger:** Spec 04 T1 floor returned NO-GO; the §3.3 diagnosis
> (`04_FLOOR_DIAGNOSIS.md`) uncovered a **systemic split/bonus adjustment failure**
> in `prices_adjusted`. Per the `04` §2 gate this is the one legitimate
> *fix-data + single same-config re-run* path — it is **not** parameter tuning.
> **Touches the holy data pipeline** (`backend/app/data/bhavcopy/`). Read CLAUDE.md
> "Data Integrity & Schema" and "Pipeline Laws" before writing code.

---

## 0. How to use this doc (cold-start checklist)

You can start this in a fresh session with no prior context. Do this first:

1. Read this whole doc, then `04_FLOOR_DIAGNOSIS.md` §3.3 (the evidence) and
   `01_DATA_LAYER.md` §4–§7 (the adjustment + validation spec).
2. Reproduce the bug yourself (§3 below) — one command, ~5 min — so you trust it.
3. Confirm the project venv: `backend/venv/bin/python` (CLAUDE.md §4 — **never**
   create a venv).
4. Work the phases in order (§5). Phase 0 is a read-only probe that locks the exact
   fetch failure mode before you change fetch code.
5. This is a **single-branch** effort on `refactor/v2-momentum-engine` (or a child
   branch). The data rebuild (Phase 3) must be **one `run_build` call over the full
   range** — see the ⚠ clobber caveat in `build.py` and §5 Phase 3.

**Success, in one line:** `validate.py` passes a new universe-wide unadjusted-split
check with ~0 violations, and `floor.py` re-runs on rebuilt data to produce a verdict
we can trust (GO or NO-GO) on the same pre-committed config.

---

## 1. Why this exists (context)

The T1 floor (`backend/app/backtest_v2/floor.py`) ran 2026-06-16 on the pre-committed
default `MomentumConfig` and returned **NO-GO**: base-cost strategy Calmar **0.283** <
Nifty 50 TRI Calmar **0.302**. The `04` §2 gate forbids tuning and forbids T2–T5 on a
NO-GO; it permits exactly one thing — fixing a **genuine data/cost bug** and re-running
the *same* config.

The §3.1 cost diagnosis cleared costs (NO-GO is not a cost artifact). The §3.3
universe/data diagnosis found a **real, systemic data bug** described below. Until the
data is fixed and the floor re-run, the NO-GO verdict rests on corrupted input and
**cannot be trusted** — and the bug biases the strategy's measured returns *downward*,
i.e. it could be masking a GO.

---

## 2. The bug (what is wrong)

`prices_adjusted` is missing split/bonus back-adjustment for a large fraction of the
survivorship-free universe. A clean split must **step the back-adjustment factor**
(`adj_factor`, and `tr_factor`) so the adjusted price series stays continuous across the
ex-date. For the affected names the factor never steps, so a raw split cliff (e.g. a 5:1
split = −80%) survives into the adjusted `close`/`open` (the **signal** prices that drive
momentum ranking and fills) and `close_tr` (the **P&L** price that drives MTM → equity →
Calmar). It is **not** a cosmetic `close_raw`-only artifact:

```
close   = close_raw × adj_factor      # signal price  — cliffs if adj_factor flat
close_tr = close_raw × tr_factor      # P&L price      — cliffs if tr_factor flat
```

### Scale (universe-wide scan, base data as of 2026-06-16)
- **556 events inside the floor window (2018-02-06 → 2026-06-12) across 406 distinct
  ISINs** where the raw price drops by a *clean split ratio* while **both `adj_factor`
  and `tr_factor` are flat** across the event.
- Ratio clustering is unmistakable: **241× ~2:1, 12× ~5:1, 23× ~10:1, ZERO non-clean.**
  A real crash scatters; these don't — they are unadjusted corporate actions.
- Includes well-known real splits (e.g. JSW Steel 10:1).

### Worked example — CUPID (`INE509F01029`), ex-date 2026-03-09 (held by the floor)
| field | 2026-03-06 | 2026-03-09 |
|---|---|---|
| open / high / low | 412.85 / 419.40 / 397.00 | **82.00 / 93.20 / 81.90** |
| close_raw = close = close_tr | 402.20 | **91.60** |
| adj_factor / tr_factor | 1.0 / 1.0 | **1.0 / 1.0** (no step!) |
| volume | 6.4M | **81.9M (13×)** |

The stock **gap-opened at ₹82** (never traded between 402 and 93) — the signature of an
**ex-date reference adjustment**, not a crash (a crash trades *down through* intermediate
prices). Open ₹82 ≈ 402.20 / 5 = **₹80.44** → an unadjusted **~5:1 split**. The floor held
CUPID across the ex-date and booked a **phantom −77% MTM cliff + a fake ₹−68,756 realized
loss** that is not economically real (post-split you hold 5× shares at ⅕ price).

**Direction = verdict-dangerous.** A missed split injects a phantom −50%…−90% drop on a
*held* name → measured strategy returns biased **down** → could be masking a GO. It also
corrupts *selection* (the phantom crash tanks that name's momentum score), so the net
portfolio sign is genuinely unknown until the rebuild + re-run.

---

## 3. How to reproduce (read-only, do this first)

The diagnostic scripts are committed and parameter-free (same floor config, no tuning):

```bash
cd backend
# §3.3 traded-name scan: glitch flags + carry exposure + universe breadth (+ verdict)
venv/bin/python -m app.backtest_v2.diag_universe_quality
# §3.1 cost decomposition (context; proves costs are NOT the problem)
venv/bin/python -m app.backtest_v2.diag_cost_sanity
```

`diag_universe_quality.py` will flag CUPID (held, −77%, no corp action). The universe-wide
556/406 count comes from the same signature applied to every ISIN: a single-day
`close_raw` drop > 40% where `adj_factor` and `tr_factor` are unchanged across the day.
That scan logic is the basis of the new validation gate in Phase 2.

CUPID inspection (confirms gap-open vs crash):
```bash
venv/bin/python -c "
import pandas as pd
from app.data.bhavcopy import store
df = store.read_prices_adjusted(isins=['INE509F01029']); df['date']=pd.to_datetime(df['date'])
print(df[(df.date>='2026-03-04')&(df.date<='2026-03-11')][['date','open','high','low','close_raw','close_tr','adj_factor','tr_factor','volume']].to_string(index=False))
"
```

---

## 4. Root cause (confirmed by reading the pipeline)

The factor math is **correct**; it was starved of events. Two failures:

### Bug A — incomplete CA fetch (`backend/app/data/bhavcopy/build.py`, Stage 3, ~line 366)
```python
ca_records = ca_mod.fetch_corporate_actions(start_d, end_d, ...)  # 2017→2026 in ONE call
```
The NSE `corporates-corporateActions` API caps the per-query window (months, not years).
A single multi-year call returns truncated/near-empty → most ISINs get **no events →
`adj_factor`/`tr_factor` = 1.0** → split cliffs survive. The parse path
(`corporate_actions.parse_corporate_actions` / `_classify` / `_parse_split`) looks sound;
the gap is **coverage**, not parsing. Secondary contributor to watch: free-text subjects
that fail `_classify`/`_parse_split` land in `CorporateActions.unmatched` (currently only
logged, never persisted).

Also: **CA events are fetched-and-discarded** — never written to disk. No audit trail is
*why* this hid for so long.

### Bug B — the validation gate is a whitelist, not a scan (`backend/app/data/bhavcopy/validate.py`, Check 1)
`_check_1_known_ca_events` validates only **5 hard-coded** large-cap events
(RELIANCE/INFY/TCS/WIPRO/GENSOL). If none are present it appends to `checks_skipped` and
**does not fail** (`checked == 0` only logs). There is **no universe-wide unadjusted-split
scan**, so 556 missed events sailed through Stage 8. My §3.3 scan is the missing gate.

---

## 5. The plan (work these phases in order)

### Phase 0 — Reproduce the fetch gap (read-only, ~30 min) — **do before touching fetch code**
Pin the exact failure mode:
- Call `fetch_corporate_actions` over the full span vs. narrow monthly windows; count
  records per window. Confirm the per-query window cap.
- Confirm **CUPID's 5:1 split (ex 2026-03-09, ISIN `INE509F01029`)** is *absent* from the
  full-range fetch but *present* from a narrow-range fetch (rules out an ISIN-join mismatch
  vs. a pure coverage gap).
- **Live NSE call** — allowed for a one-off diagnostic (the no-live-API rule governs
  `pytest`). Use the cookie-warmed session (`download.build_session`). Be polite (rate
  limit). Do **not** add live calls to any test.
- **Exit:** documented failure mode (window cap vs. join mismatch vs. parse miss). This
  decides Phase 1's exact shape.

### Phase 1 — Fix the adjustment (revised after Phase 0)

> **Phase 0 revised Bug A:** The NSE CA API does NOT have a window cap — a single
> full-range call (2017→2026) returns the same 20,941 records as 113 monthly windows
> summed. The actual failure mode is **ISIN succession**: when a company changes its
> ISIN (typically after a face-value split), subsequent CA events are filed against the
> **old ISIN** while bhavcopy prices trade under the **new ISIN**. The ISIN-keyed join
> in `adjust.py:105` silently misses these events. See §11 Phase 0 Findings for detail.

Two changes to `adjust.py` / `corporate_actions.py`:

1. **ISIN succession bridge** — when `events_by_isin.get(isin)` returns empty,
   look up the ISIN's symbol (from `raw_df`) in a symbol-keyed secondary index of CA
   events and apply any events whose `ex_date` falls within the current ISIN's active
   date range (first/last date in `raw_df` for that ISIN). This bridges the ~62 ISINs
   where the CA event exists under the old ISIN but prices are now under a new ISIN.
   The simplest implementation: build `events_by_symbol` alongside `events_by_isin`
   in `adjust.py`, restrict by ex_date range, and merge in before computing factors.

2. **Persist CA events + `unmatched`** to a new parquet artifact via `store.py`
   (e.g. `corporate_actions/` table + schema). This is the missing audit trail and lets
   validation/diagnosis run without re-fetching. (Schema add only — no change to
   `PRICES_ADJUSTED_SCHEMA`.)

- Triage `unmatched` after a full fetch — manually verify none of them are real
  splits/bonuses that the free-text parser missed. Phase 0 found 2 bonus-parse
  failures and 86 dividend-parse failures; no split/bonus-keyword records were
  dropped silently.
- **180 ISINs** with unadjusted cliffs have NO CA event in the NSE feed by any join
  key — these cannot be fixed via the current data source. Accept this residual;
  document in the rebuilt `validate.py` Check 7 tolerance.
- No monthly chunking needed; keep a single `fetch_corporate_actions` call. (Chunking
  may be added later for API resilience but is NOT required for coverage.)
- **Tests** (CLAUDE.md §5, Rule 9): unit-test the ISIN-succession bridge with a
  synthetic two-ISIN scenario (`_ca_records` injection already exists in `run_build`
  for tests); assert CUPID's Bonus 4:1 is now applied to `INE509F01029` prices.
  Assert that the bridge does NOT apply an old-ISIN event whose ex_date is outside
  the new ISIN's active window.

### Phase 2 — Add the prevention gate (`validate.py`)
- **New Check 7 (universe-wide unadjusted-action scan):** for every ISIN, flag any
  single-day move > 40% in the **adjusted `close`** where `adj_factor` **and** `tr_factor`
  are flat across that day; **fail loud** (AssertionError) if the count exceeds a small
  tolerance. Allow a tiny budget for genuine no-band events, but a cluster fails. This is
  the diagnostic promoted to a permanent acceptance check.
- **Harden Check 1:** fail (not skip) if a multi-year build (range start ≤ 2018) finds
  **zero** of the known events present-and-checked.
- Tests: a synthetic dataset with one unadjusted split must FAIL Check 7; the same dataset
  correctly adjusted must PASS.

### Phase 3 — Rebuild the data (idempotent; holy)
- **Back up the current parquet store first** (`backend/data/...`) — it is the audit
  trail the rebuild overwrites. Copy to a timestamped sibling dir.
- Re-run **Stages 3–7 from the existing `raw_parsed/` checkpoints** — no re-download
  needed; the build re-runs CA→adjust→universe→store from assembled raw every time.
- **One `run_build` call over the ENTIRE date range** (honor the ⚠ caveat in `build.py`
  lines 40–49: partial-range calls clobber earlier partitions and break the adv_20
  rolling window).
- **No Alembic migration:** `prices_adjusted` is parquet and the **schema is unchanged**;
  this is a data-content rebuild, not a schema change. (Alembic governs DB schema; the new
  `corporate_actions` parquet table in Phase 1 is also files, not DB — but if you instead
  choose a DB table for CA audit, that DOES need an Alembic migration. Prefer parquet to
  stay consistent with the rest of the data layer.)
- Re-run `validate.py` (now with Check 7) — must pass with ~0 violations.

### Phase 4 — The single authorized floor re-run
- Re-run `floor.py` on the **same pre-committed config** (§7 below). This is the
  `04` §2-legitimate re-run — **not** tuning. Change no parameter.
- Compare new `C_strat` vs `C_nifty50` (and the full 3×3 grid).
- Update `04_FLOOR_DIAGNOSIS.md` §3.3 + §4 and the memory `v2-floor-no-go.md` with the
  re-run verdict (NO-GO now stands on clean data → spec 04 ends; or GO → proceed to T2
  under spec 04's GO branch).

---

## 6. Definition of done
- [x] Phase 0 failure mode documented (§11 below). Window-cap hypothesis disproved;
      ISIN succession confirmed as the mechanism; 62 fixable + 180 permanently absent.
- [x] ISIN succession bridge in `adjust.py`; symbol-keyed fallback restricted to new
      ISIN's active date range; CUPID's Bonus 4:1 now applies to `INE509F01029`.
      **Phase 1 complete 2026-06-16.** `adjust.py` bridge + `store.py` CA schemas +
      `build.py` persist + 4 unit tests (all green, 145/145).
- [x] CA events + unmatched persisted to `corporate_actions.parquet` / `ca_unmatched.parquet`
      via new `store.write_corporate_actions` / `write_ca_unmatched`; unmatched triaged in
      Phase 0 (no real splits/bonuses hiding there).
- [ ] `validate.py` Check 7 added + tested; Check 1 hardened.
- [ ] Old parquet store backed up; data rebuilt in one full-range call.
- [ ] `validate.py` passes with ~0 unadjusted-split violations (was 556 in-window).
- [ ] `diag_universe_quality.py` shows 0 held phantom-DOWN non-corp flags (was 1: CUPID).
- [ ] Floor re-run on the pre-committed config; verdict recorded in `04_FLOOR_DIAGNOSIS.md`
      + memory.
- [ ] CI green (`pytest`), no live-API calls in tests.

---

## 7. Reference — the pre-committed floor config (re-run with EXACTLY this)
```
MomentumConfig(
    target_positions=20, sell_rank_buffer=35, liquidity_floor_cr=5.0,
    momentum_lookback_days=252, momentum_skip_days=21, vol_lookback_days=126,
    trend_ma='EMA_200', max_position_pct=10.0, starting_capital=1_000_000.0,
    use_regime_overlay=True, catastrophic_stop_pct=25.0, rebalance='monthly',
    date_from=date(2018, 2, 6), date_to=date(2026, 6, 12),
)
```
Built by `floor.build_floor_config()`. Regime overlay uses the **real Nifty 50 price
200-DMA** (`benchmark.load_price_index`). Baseline verdict to beat: `C_strat` 0.283 vs
`C_nifty50` 0.302 (`C_primary` Mom30 TRI = 0.448). GO iff `C_strat ≥ 0.80 × C_primary`;
NO-GO iff `C_strat < C_nifty50`.

## 8. File map (where everything lives)
| Concern | File |
|---|---|
| Build orchestrator (Stage 3 fetch bug) | `backend/app/data/bhavcopy/build.py` |
| CA fetch + parse + factor math | `backend/app/data/bhavcopy/corporate_actions.py` |
| Apply factors → adjusted prices | `backend/app/data/bhavcopy/adjust.py` |
| Validation gate (Check 1 whitelist; add Check 7) | `backend/app/data/bhavcopy/validate.py` |
| Parquet store + schemas | `backend/app/data/bhavcopy/store.py` |
| The floor (re-run target) | `backend/app/backtest_v2/floor.py` |
| §3.3 reproduction | `backend/app/backtest_v2/diag_universe_quality.py` |
| §3.1 cost context | `backend/app/backtest_v2/diag_cost_sanity.py` |
| Evidence + verdict | `specs/v2/04_FLOOR_DIAGNOSIS.md` |
| Data-layer spec (adjustment + validation) | `specs/v2/01_DATA_LAYER.md` |

## 9. Open decisions (resolve with Arafat before/early)
1. **Rebuild scope** — full 2017→2026 (recommended; a partial fix re-corrupts the next
   run and leaves the signal series wrong) vs. held-names-only patch (cheaper, dirty).
2. **CA audit store** — parquet (recommended, consistent) vs. DB table (needs Alembic).
3. ~~Phase 0 live probe — window cap known?~~ **RESOLVED:** No window cap exists. Phase 0
   complete; see §11.
4. **Residual 180 absent ISINs** — accept as permanently unfixable via NSE CA feed, or
   supplement with a second data source (BSE corporate actions, CDSL, manual CSV)?
   Recommendation: accept the residual; adjust Check 7 tolerance accordingly.
   The 62 ISIN-succession fixes likely cover the verdict-relevant held names (CUPID
   confirmed; others TBD by Phase 4 re-run).

## 10. Blast radius (stated, not discovered later)
Every backtest in the project — **v1 and the v2 floor** — ran on these mis-adjusted
prices. After the rebuild, signals, rankings, and the universe all shift (the phantom
cliffs corrupted momentum scores, not just MTM). That is expected and is the point. v1
results are also retroactively invalidated (informational; no action implied here).

---

## 11. Phase 0 Findings (2026-06-16) — documented exit

**Probe script:** `backend/app/data/bhavcopy/diag_ca_fetch.py`
**Scope:** live NSE calls, read-only, no data changed.

---

### 11.1 Window-cap hypothesis — DISPROVED

The original Bug A hypothesis was: *the NSE `corporates-corporateActions` API caps
the per-query window (months, not years), causing a single multi-year call to return
truncated/near-empty results.*

**Result:** Full-range fetch (2017-01-01 → 2026-06-12, a single call) returned
exactly **20,941 records** — identical to the sum of 113 monthly 1-month windows
(each fetched separately). No truncation. The API cap does NOT apply at this volume.

### 11.2 CUPID-specific probe — root cause confirmed

CUPID (ISIN `INE509F01029`, ex-date 2026-03-09) was tested with a 60-day narrow
window. The event is **absent from the CA feed under `INE509F01029`** — but it IS
present under the old ISIN `INE509F01011`:

```
isin=INE509F01011  symbol=CUPID  exDate=09-Mar-2026  subject=Bonus 4:1
```

A Bonus 4:1 = 4 new shares per 1 held → total 5 shares → price divides by 5 →
price multiplier 0.2 — matches the observed ~5:1 price gap (402 → 82). The action
content is correct; the **join key is wrong**.

**ISIN succession history for CUPID:**
| Date | Event |
|---|---|
| 2017 – 2023-12-12 | Trades as `INE509F01011` |
| 2024-04-04 | FV Split (10→1) + Bonus 1:1 under `INE509F01011` |
| 2024-10-28 | Re-lists as `INE509F01029` (new face-value ISIN) |
| 2026-03-09 | Bonus 4:1 — recorded against old `INE509F01011` in NSE CA feed |

The CA feed continues to record events against the **old ISIN** even after the
company re-lists under a **new ISIN**. The join in `adjust.py:105`
(`events_by_isin.get(str(isin), _EMPTY_EVENTS)`) looks up by exact ISIN and
finds nothing for `INE509F01029` → factors = 1.0 → the Bonus cliff survives.

### 11.3 Universe-wide breakdown (all 556 unadjusted cliffs)

Scan: single-day drop >40% in adjusted `close` where `adj_factor == adj_factor[T-1]`
AND `tr_factor == tr_factor[T-1]` (no factor step), floor window 2018-02-06 →
2026-06-12. Matches the spec's 556 total exactly.

Of the subset with a **clean split ratio** (2:1 / 3:1 / 4:1 / 5:1 / 10:1 within
±10%): **332 events across 247 distinct ISINs**.

| Category | ISINs | What it means |
|---|---|---|
| CA event in NSE feed, **ISIN succession** (old ISIN) | **62** | Fixable — ISIN bridge in `adjust.py` |
| CA event in NSE feed, same ISIN, ex_date ≠ cliff | **5** | False positives — genuine market events (VAKRANGEE crash, COVID, etc.) |
| **No CA event in NSE feed at all** | **180** | Permanently absent from this API; unfixable without a 2nd source |

The remaining ~224 clean-ratio cliff ISINs (556 − 332 = 224 non-clean-ratio cliffs)
are predominantly genuine extreme market events and NSE circuit-limit edge cases.

**Unmatched CA records (parse failures):** 8,218 out of 20,941 total. Breakdown:
- 8,130 — no split/bonus/dividend keyword (AGM notices, rights, etc.) → correct to skip
- 86 — dividend: could not parse value (unusual Rs formatting like "Rs - 2") → only dividends; no splits hidden here
- 2 — bonus: could not parse value → marginal, investigated, not splits

**Conclusion on unmatched:** No real splits or bonuses are hidden in the unmatched
pile. The free-text parser correctly classifies all capital-structure events in the feed.

### 11.4 Revised failure mode (replaces Bug A in §4)

| Bug as specced | Actual finding |
|---|---|
| Bug A: window cap → empty full-range fetch | **DISPROVED.** No cap; single call returns complete data |
| — | **REAL BUG: ISIN succession** — NSE CA feed files events against old ISIN after company changes ISIN; `adjust.py` join fails silently |
| Bug B: validate.py whitelist | **CONFIRMED unchanged** — still needs universe-wide Check 7 |

### 11.5 Phase 1 implications

- **No chunking needed** for fetch coverage.
- Phase 1's single real change: add **ISIN succession bridge** to `adjust.py` —
  when `events_by_isin[isin]` is empty, fall back to `events_by_symbol[symbol]`
  filtered to events whose `ex_date` is within the ISIN's active date range.
- Fixes ~62 ISINs (CUPID confirmed; others TBD by re-run).
- **180 ISINs** with no CA event in the NSE feed are accepted as residual; Check 7
  tolerance must account for them.
- Persist CA events parquet (audit trail) as originally planned.
