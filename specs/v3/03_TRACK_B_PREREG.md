# v3 / 03 — Track B Pre-Registration: Value & Quality Factors (H3)

> **CLOSED 2026-06-20 — research note. H3 NOT confirmed (vacuous predicate) + §6 fails (3/5).
> Terminal verdict + forward decision in `07_TRACK_B_CLOSE.md`. `FINAL_OOS` never consumed — pristine.**
>
> **Status: LOCKED 2026-06-19 — Arafat signed off §11. Build via `04_TRACK_B_EXEC_TASKS.md`.**
> This is the **separate, separately-approved** factor pre-registration that `02_TRACK_B_DATA.md` §7 and
> `02_TRACK_B_TASKS.md` (TB8) gate on the data layer **passing** its §6 acceptance gate.
> TB8 returned **§6 = PASS** on the full 3470-ISIN panel (2026-06-19, all 5 checks, all 42
> rebalance dates) under the pre-registered "filers-only" denominator — so this file may now
> be written. **Nothing here has been run.** No backtest, no factor return, no Calmar has been
> computed. `FINAL_OOS` (2023-07-01 → 2026-06-12) remains **pristine and unconsumed**.
>
> **This file is a commitment, not a task list.** It fixes the Track-B factor definitions,
> their economic rationale, the as-of read contract, the composition rule, the bounded coarse
> grid, and the H3 test — *before* any number is measured (spec-04 §5; the v1 failure mode is
> committing the design after seeing the result). `04_TRACK_B_EXEC_TASKS.md` decomposes the
> backtest build into cold-session tasks; the grids below are **LOCKED** (§11, 2026-06-19).

---

## 0. Why this prereg exists (the gate that opened it)

Track A closed as a research note: its price/volume factors are **momentum-correlated**, so
they cannot fix single-regime dependence — the §6.4 hardened-concentration failure (the
candidate's entire edge lived in the post-COVID bull). `00_PREREGISTRATION.md` §11 item 1
gated Track B on Track A being "promising but **H3 (regime diversification) remains unmet**."
That is exactly where we are.

**H3 needs factors genuinely uncorrelated with momentum — value and quality — and those need a
survivorship-free, point-in-time fundamentals layer that did not exist.** `02_TRACK_B_DATA.md`
built it (TB1–TB6) and TB8 ran the §6 acceptance gate over the real panel: **PASS**. This file
pre-registers the factors that layer unlocks, and the one test that justifies the entire Track-B
build: **does adding value/quality to the momentum composite narrow the §6.4 subperiod spread?**

This is the *only* reason Track B was authorized. If the answer is no, that is a reported
failure (Rule 12), not something to engineer around.

---

## 1. Scope discipline (the v1 sins, carried over — explicitly forbidden)

This prereg inherits **every** prohibition in `00_PREREGISTRATION.md` §1, restated because
adding a second factor family enlarges the search space and makes overfitting *easier*:

- ❌ Adding a factor without a **pre-registered economic rationale** (no "try it and see").
- ❌ Searching factor weightings on a fine grid / optimizing the blend to the backtest.
- ❌ Touching `FINAL_OOS` more than once, or moving any frozen boundary.
- ❌ Reading fundamentals by any path **other than** `read_fundamentals_asof` (§4) — no factor
  touches the raw ORM tables; the safety-lag and restatement guards live only in the reader.
- ❌ **Re-opening the §6 data gate.** The data layer is closed and PASSED. Coverage thresholds,
  the safety lag, and the restatement policy are **frozen in `data_config.py`** (TB0). This
  file adds **no** data-layer threshold and re-runs **no** §6 check.
- ❌ Zero-filling a missing fundamental (a NULL line item is *absent*, never 0 — TB4 invariant).

Every config evaluated is logged to the v2 `ConfigLedger`; K feeds the deflated Sharpe (§9).

---

## 2. Hypothesis under test (H3 — restated as a falsifiable predicate)

From `00_PREREGISTRATION.md` §2:

> **H3 (regime).** Factors with **low cross-correlation to momentum** (value, quality) smooth
> performance across regimes → the §6.4 subperiod spread narrows (no single period carrying
> the result).

**Pre-registered test of H3 (binding).** On `DISCOVERY` (Track-B window, §8), holding the
Track-A construction knobs at their accepted values, compare the **momentum/Track-A composite
baseline** against the **same composite + value/quality**:

1. **Primary predicate (the §6.4 stick, unchanged from `00` T0 lock).** The augmented composite
   **PASSES** the §6.4 hardened-concentration gate — *no positive subperiod has Calmar > 5× the
   mean of the other positive subperiods* — where the Track-A-only baseline **fails** it. This is
   the binding, pre-committed pass/fail.
2. **Supporting evidence (reported, not a second gate).** The subperiod Calmar **spread narrows
   materially** vs the baseline, and the momentum↔value/quality cross-sectional rank correlation
   is **low** (|ρ| pre-registered expectation < 0.3) — confirming the smoothing comes from genuine
   orthogonality, not a momentum proxy in disguise.

**H3 is confirmed** only if (1) holds. If value/quality fail to narrow the spread, or only do so
by introducing a *new* single-regime dependence, **H3 is reported as unmet** and Track B closes
as a research note (Rule 12) — `FINAL_OOS` stays pristine. Confirming H3 on DISCOVERY is the
*precondition* for the one-shot `FINAL_OOS` run (§9), never a substitute for it.

---

## 3. The factors (definitions, rationale, sign — committed)

Five factors over two families — the set named in `02_TRACK_B_DATA.md` §4, the genuinely
**momentum-orthogonal** ones. All monetary quantities use the **TB6 raw×raw convention**
(§4.2); all reads go through `read_fundamentals_asof` (§4.1). A higher factor score is always
"better" (cheaper / higher-quality) **after** the sign in the last column, so the percentile
rank-blend (§5) is directionally consistent across all factors.

| # | Factor | Family | Definition (TTM unless noted) | Inputs | Sign |
|---|---|---|---|---|---|
| V1 | **Earnings yield (E/P)** | Value | `ttm(net_income) / market_cap_raw` | net_income, close_raw, shares_outstanding | higher = better |
| V2 | **Book-to-price (B/P)** | Value | `total_equity / market_cap_raw` = `book_to_price_raw` | total_equity, close_raw, shares_outstanding | higher = better |
| Q1 | **ROE** | Quality | `ttm(net_income) / avg(total_equity)` | net_income, total_equity | higher = better |
| Q2 | **Accruals** | Quality | `(ttm(net_income) − ttm(cfo)) / total_assets` | net_income, cfo, total_assets | **lower = better** (sign-flipped) |
| Q3 | **Leverage** | Quality | `total_debt / total_equity` | total_debt, total_equity | **lower = better** (sign-flipped) |

**Economic rationale (pre-registered, per `00` §1 — no factor without one):**

- **E/P / B/P (value).** The value premium is the canonical momentum *complement*: cheap names
  are typically out-of-favour / recently weak — mechanically anti-correlated with 12-1 momentum,
  which is the source of H3's regime smoothing.
- **ROE (quality).** Persistent profitability is rewarded across regimes and is largely
  orthogonal to price trend; it screens the "cheap because broken" value trap that raw value buys.
- **Accruals (quality).** Low accruals (earnings backed by cash, not by working-capital timing)
  predict earnings persistence (Sloan); a quality overlay independent of both price and headline P&L.
- **Leverage (quality).** Low leverage cushions drawdown in risk-off regimes — directly on-thesis
  for narrowing the §6.4 spread (the post-COVID-only edge was a leveraged-beta artifact).

**Honest scope limits (Rule 12):**

- **EBIT/EV is NOT in the core grid.** Enterprise value needs cash & equivalents, which is **not**
  one of the 8 ingested line items (TB1 schema: revenue, net_income, ebit, total_equity,
  total_assets, total_debt, shares_outstanding, cfo). Shipping `EBIT/(market_cap + total_debt)`
  with no cash subtraction would be a knowingly-biased EV. The earnings-yield factor is therefore
  **E/P** (V1). An EBIT-based enterprise multiple is deferred to a robustness variant only, and
  only if a later layer needs it — it does not enter the §6 grid without its own prereg.
- **Financials (banks/NBFCs)** carry leverage and accruals that are not comparable to non-financials
  (TB0.5 flagged their non-standard P&L tags, since mapped). For V/Q ranking they are **excluded
  from the leverage (Q3) and accruals (Q2) cross-sections** (ranked NULL → not counted, §5), but
  retained for E/P, B/P, and ROE. This is a pre-committed exclusion, not a post-hoc drop.

---

## 4. The read contract (sole path — non-negotiable)

### 4.1 As-of reader is the only fundamentals access

Every factor value at as-of date `D` is computed **exclusively** from
`read_fundamentals_asof(session, isin, D)` (TB5, `reader.py`). That reader — and **only** that
reader — enforces:

- **Safety lag = 2 trading days** (§8.4 locked): a filing is visible only once
  `available_date ≤ D − 2 trading days`. No factor re-implements or bypasses this.
- **Restatement = as-of-latest-version-known** (§8.5): for each `period_end`, the latest version
  with `available_date ≤ D − lag` wins; earlier-known figures are returned at earlier `D` (the
  look-ahead guard, validated end-to-end by §6.4 of the data gate).
- **Absence is absence:** the reader returns `[]` (or NULLs) when nothing qualifies — never a
  future-filed or guessed figure. A factor that cannot be computed is **missing**, not 0 (§5).

No factor imports the ORM models or queries `fundamentals_line_items` directly. This is enforced
by package boundary + the TB5 frozen-snapshot return type, and re-asserted here as a prereg term.

### 4.2 TTM construction & the raw×raw convention (locked for unambiguous math)

- **Flow items** (`net_income`, `revenue`, `cfo`) are **trailing-twelve-month**: sum the four
  most recent quarterly periods whose `period_end` spans ≤ 15 months and are all visible as-of
  `D − lag`. **Fallback:** if four clean quarters are unavailable but the latest **annual** period
  is, use the annual figure as the TTM (Indian filings are frequently annual/half-yearly — TB3).
  A name with neither is **missing** for that factor (not counted, §5), never partially summed.
- **Stock items** (`total_equity`, `total_assets`, `total_debt`, `shares_outstanding`) are the
  **latest as-of point-in-time** value (most recent qualifying `period_end`). `avg(total_equity)`
  in ROE (Q1) averages the latest two annual equity points when both are visible; else the latest.
- **Market cap = `market_cap_raw(close_raw, shares_outstanding)`** (TB6): `close_raw × shares_
  outstanding`, the raw×raw basis that is continuous across splits/bonuses. **`close × shares`
  or `close_tr × shares` is forbidden** (adjusted price × raw shares → artificial discontinuity —
  the TB6 finding). `book_to_price_raw(total_equity, close_raw, shares_outstanding)` is the
  sanctioned B/P helper. These are the **only** sanctioned market-cap / B/P paths.

### 4.3 Degenerate-denominator & sign handling (pre-committed)

- **Non-positive book value** (`total_equity ≤ 0`): B/P (V2) and ROE (Q1) are **NULL** for that
  name (a meaningless ratio), not a large/negative outlier. Counted as missing, not winsorized.
- **Negative earnings** (loss-makers): E/P (V1) is computed and ranked as-is (a genuine low/negative
  yield is real information); the percentile rank handles the ordering. ROE likewise.
- **Zero/negative `total_assets`** (Q2 denominator) → NULL.
- Because the composite is a **percentile rank-blend** (§5), per-factor winsorization is not
  required to tame outliers (ranks are scale-free); it is therefore **not** applied (Rule 2 — no
  knob we don't need). Sign-flips for Q2/Q3 are applied as `−value` *before* ranking so "lower =
  better" maps to a higher percentile.

---

## 5. Composition rule (extends `00` §5 — pre-committed)

Track-B factors enter the **same** equal-weight percentile rank-blend `00` §5 already commits:

```
composite_rank(name, day) = mean_over_active_factors( percentile_rank(factor_value) )
```

- **Equal-weight rank-blend** is the default (`00` §5 / §11 item 3). Any non-equal weighting needs
  its own pre-registration — not in scope here.
- **Factors are added one layer at a time** (§6), each accepted only on a **plateau** (04 §4),
  never as a bulk value+quality dump. This protects the clean attribution H3 needs.
- **Missing-fundamental handling (the breadth/coverage interaction — pre-committed):** a name
  with no usable value/quality factor is **not zero-filled and not dropped** — it averages over
  the factors it *does* have (its Track-A momentum/price factors), per the "mean over active
  factors" rule. **Consequence, surfaced (Rule 12):** the ≤25%-by-name uncovered tail leans on
  momentum alone, mildly diluting H3's reach into the small-cap tail. This is the honest cost of
  a 75%-by-name floor and is *reported*, not hidden. A name must have **≥1** active value/quality
  factor to count as "receiving" the Track-B signal in the H3 attribution.
- **No sector or size neutralization** in the coarse grid (Rule 2 — value's known sector tilt is
  left raw, as Track-A factors were). Sector-neutralized value is an explicitly **deferred** late
  layer requiring its own prereg, used only if H3 is unmet *and* sector tilt is shown to be the cause.
- **Entry gate unchanged** (`00` §5): `close > 200-MA AND liquidity floor`, momentum-positive gate
  retained while momentum is in the blend. Track B changes the **ranker**, not the gate.

---

## 6. Bounded coarse grid (one layer at a time — PROPOSED, lock in §11)

Continues `00` §6's layer ladder. Each layer holds all other knobs at the **best accepted Track-A
configuration** (the §6 plateau winner from `01_TRACK_A_TASKS.md`), runs on the **Track-B DISCOVERY
window only** (§8), logs every config to the `ConfigLedger`, and is accepted only on a **plateau**
(04 §4) **and** only if it does not worsen the §6.4 spread. The grid is deliberately tiny — a
factor that needs a large grid to help is noise and is dropped.

**Primary proposal — two family blocks (keeps the grid to a handful of points, tests the V/Q
*families* H3 names):**

| # | Layer | Coarse grid (proposed) | Tests |
|---|---|---|---|
| B1 | Add **Value block** = equal-blend{E/P, B/P} | baseline vs {Track-A best} + value | H3 |
| B2 | Add **Quality block** = equal-blend{ROE, accruals, leverage} | + quality | H3 |
| B3 | Block weighting (only if B1+B2 both help) | composite weight {momentum : value : quality} ∈ {1:1:1, 2:1:1} — **coarse, 2 points** | H3 |

- **B1/B2** are the core H3 test: each block is an internal equal-weight blend of its members
  (§3), added as one composite layer, accepted on a plateau. Within-block equal weighting avoids a
  per-factor fine search.
- **B3** is a *single* coarse choice (does momentum stay dominant, or do the families get equal
  say?) — at most **2 points**, only opened if both blocks earn a place. No finer weight grid exists.

**Decision (Arafat, 2026-06-19): the two-block grid above is chosen.** The rejected alternative —
five individual factor layers (B1=+E/P, B2=+B/P, B3=+ROE, B4=+accruals, B5=+leverage) mirroring
`00` §6 layers 4–7 — was set aside for tighter K (fewer configs → lighter deflation) and because
H3 is a claim about the value/quality *families*, not any single ratio. Per-factor attribution, if
ever needed, is read off the `ConfigLedger` post-hoc, not bought with extra in-sample trials.

No layer exceeds a handful of points. If a layer needs a large grid to find a winner, the layer is
noise and is dropped (04 §4).

---

## 7. Reuse of the existing harness (no new infra unless a layer needs it)

Track B is a **factor-library extension**, driven through the same test-gated machinery as Track A:

- `read_fundamentals_asof` (TB5) — the sole fundamentals read path; the new factor functions call it.
- `ca_consistency.market_cap_raw` / `book_to_price_raw` (TB6) — the only market-cap / B/P helpers.
- `factors.py` + the composite ranker (`00` §7) — the value/quality factors register here as new
  `(day, isin) → float` callables, blended by the unchanged percentile-rank composite.
- `engine.run(...)`, `costs.py`, `benchmark.py` — unchanged daily loop, three cost levels, benchmarks.
- `validation.py` — `ConfigLedger`, `deflated_sharpe`, `pbo_cscv`, walk-forward — unchanged; the
  Track-B DISCOVERY window (§8) is passed in, the canonical v2 split constants are **not** edited.
- `robustness.py` — the five §6 *performance* checks (incl. §6.4 concentration), reused as the
  candidate gate before OOS. **(Distinct from the §6 *data* gate in `02`, which is already closed.)**

New code is confined to the five factor functions + their TTM/raw×raw plumbing. No `MomentumConfig`
change; the v3 `V3Config` gains an `active_factors` extension only (value/quality factor names).

---

## 8. Frozen splits & OOS discipline (Track-B window)

- **Track-B DISCOVERY = 2020-01-31 → 2023-06-30.** The start is the §10 pre-registered rescope
  (`00`, 2026-06-17), pinned by TB8 to **2020-01-31** — the first monthly rebalance with durable
  ≥75%-by-name coverage over the full liquidity-eligible panel (not a probe estimate). This is a
  **data-feasibility** window, not a performance tune; the §6 thresholds were never moved.
- **`FINAL_OOS` = 2023-07-01 → 2026-06-12 — pristine and unchanged.** Never observed by Track A or
  the Track-B data build. Post-2023 coverage is ~95%, so the window is feasible as-is.
- DISCOVERY is ~3.5 yr (41 months) — it **retains the Mar-2020 COVID crash**, the largest regime
  contrast in the panel and precisely the diversification H3 is built to test. Walk-forward
  (`walk_forward_windows`, `min_is_months=24` + `oos_months=6`) yields **2–3 expanding folds**.
  Acknowledged cost (Rule 12): the 2018 mid-cap crash and 2018-19 NBFC crisis are out of the
  Track-B in-sample window (the early XBRL desert made them unreachable, not optional).
- The chosen Track-B candidate runs on `FINAL_OOS` **exactly once**. If it fails, it fails — no
  iteration against it. **Deflation:** K counts Track-B's own trials (the value/quality grid above)
  *plus* the Track-A trials already spent on the shared composite — reported with raw Sharpe and PBO.

---

## 9. Decision predicates & Definition of Done (same bar as `00` §9 — not lowered)

The Track-B candidate is "validated, deployable" only if a **single, pre-committed** config:

- Beats Nifty200 Momentum 30 TRI on **Calmar** after **base** costs, with **max DD ≤ 70%** of
  benchmark, on the Track-B `DISCOVERY` window; AND
- Passes **all five** robustness checks (04 §6) — including **§6.1 pessimistic-cost**, **§6.2
  top-10-drop ≥ 70% retention**, and critically **§6.4 hardened concentration** (the H3 target,
  §2); AND
- **Confirms H3 (§2):** the §6.4 subperiod spread narrows vs the Track-A-only baseline and §6.4
  passes where the baseline failed; AND
- Passes the **one-shot `FINAL_OOS`** without re-tuning; AND
- Is tradeable on realized turnover/capacity (not just planned).

Anything less is a research note (Rule 12). No softening. It is a legitimate, pre-accepted outcome
that Track B **also** ends as a research note — the point is honest measurement of H3, not a
guaranteed deployable strategy (`00` §10).

---

## 10. What this prereg does NOT do (the guards, restated)

- It does **not** re-open or re-run the §6 **data** gate (closed, PASS — `02`/TB8). No data
  threshold, lag, or restatement rule is touched.
- It does **not** move any frozen split or the §9 DoD bar.
- It does **not** read fundamentals outside `read_fundamentals_asof`, zero-fill a NULL, or use any
  market-cap basis other than raw×raw.
- It does **not** fine-tune factor weights, sector-neutralize, or add EBIT/EV — each is a separate,
  separately-approved prereg if ever needed.
- It does **not** touch `FINAL_OOS` until a single DISCOVERY-selected candidate is locked.

---

## 11. Locked commitments (Arafat, 2026-06-19)

*Arafat read the full draft and signed off, 2026-06-19. The items below are now binding,
mirroring `00` §11. No later session may change a locked item without a new pre-registration
entry and explicit session approval.*

1. **Factor set = the five in §3** (E/P, B/P, ROE, accruals, leverage), raw×raw math, sole read
   path `read_fundamentals_asof`. EBIT/EV, sector-neutralization, and non-equal within-block
   weights are **out of scope** (each needs its own prereg).
2. **Grid shape = two family blocks** B1 (+Value{E/P, B/P}) / B2 (+Quality{ROE, accruals,
   leverage}) + optional coarse B3 block-weight {1:1:1, 2:1:1}. The five-individual-layer
   alternative was rejected for K economy (Arafat, 2026-06-19). §6.
3. **Composition = equal-weight percentile rank-blend**, factors added one layer at a time on a
   plateau, missing-fundamental = mean-over-active (not zero-filled, not dropped). §5.
4. **H3 test as pre-registered in §2** — primary predicate = the §6.4 hardened-concentration gate
   passes where the Track-A baseline fails; supporting = spread narrows + low momentum↔V/Q ρ.
5. **Track-B DISCOVERY = 2020-01-31 → 2023-06-30; `FINAL_OOS` pristine; §9 DoD bar unchanged.** §8.

Build proceeds via `04_TRACK_B_EXEC_TASKS.md` (decomposing the DISCOVERY backtest + the one-shot
`FINAL_OOS` into cold-session tasks). No `FINAL_OOS` figure is observed until a single
DISCOVERY-selected candidate is locked by that file's penultimate task.
