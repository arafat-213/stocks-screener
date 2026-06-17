# v3 / 02 — Track B: Point-in-Time Fundamentals Data Layer (BUILD SPEC)

> **Status: COMMITTED 2026-06-17 — §8 locked by Arafat. Build may proceed via `02_TRACK_B_TASKS.md` (TB0→TB7).**
> This is the **prerequisite data-layer build** gated in `00_PREREGISTRATION.md` §4 / §11.
> It is *not* a factor pre-registration. It scopes the survivorship-free, point-in-time
> fundamentals source, its acceptance gate, and the sequencing into the Track-B factor
> prereg. **No Track-B factor is pre-registered, and no backtest is run, until the data
> built here passes the §6 acceptance gate.**
>
> **Source decision (Arafat, 2026-06-17): self-ingest NSE/BSE filings.** Chosen over a paid
> PIT vendor, a mid-tier API, and deferral — it is the only freely-reproducible path with
> genuine filing-date PIT and real delisted-name coverage, and it matches the project's
> correctness-over-convenience standard. The cost is build effort, scoped below.

---

## 0. Why this build exists (the gate that opened it)

Track A closed as a research note: the T6 §6 battery scored 1/5, and the **§6.4 hardened
concentration gate failed** — the candidate's entire edge lived in the post-COVID bull
(Calmar 5.242 ≫ 5× the other subperiods). Track A's price/volume factors are
momentum-correlated, so they *cannot* fix single-regime dependence (prereg §10, confirmed).

`00_PREREGISTRATION.md` §11 item 1 gated committing to Track B on Track A being
"promising but H3 (regime diversification) remains unmet." That is exactly where we are:
H1/H2 partially addressed, **H3 untested for lack of fundamentals data.** Value & quality
are the factors genuinely uncorrelated with momentum — the real §6.4 fix — and they need a
data layer that does not exist yet. This spec builds it to spec-01 standard.

---

## 1. The two hard problems (why yfinance was forbidden)

Indian-equity fundamentals are easy to get *wrong* in exactly the two ways that invalidate a
backtest. The v1 yfinance fundamentals failed both; this build must pass both:

### 1.1 Point-in-time (no look-ahead)

A quarter ending 31-Mar is typically **filed 4–8 weeks later** (SEBI LODR Reg 33). Using a
period-end-dated figure on a date before its public filing is look-ahead bias. Every record
must therefore carry the **public-availability date** (the filing/submission timestamp), and
factor computation as-of date `D` may only read records with `available_date ≤ D` (with a
safety lag, §3). yfinance serves only latest/restated values with no as-of date → unusable.

### 1.2 Survivorship-free (delisted names present)

Names delisted/merged/suspended during 2018→2026 (e.g. DHFL, Yes Bank dilution, CG Power
pre-resolution, countless SME exits) must be in the panel for the windows in which they
traded. A universe built from *today's* listed set silently drops every failure — inflating
returns. The fundamentals universe must be the same **survivorship-free, ISIN-keyed** set the
v2 price layer already uses, extended with the financials of names that later vanished.

---

## 2. Source & scope (locked: self-ingest)

| Item | Decision |
|---|---|
| Primary source | NSE + BSE corporate-filings repositories (financial results, Reg 33 / LODR) |
| Format | XBRL where available (Ind-AS taxonomy); structured filing index for `available_date` |
| Stable key | **ISIN** (matches the v2 price layer; survives symbol changes) |
| PIT timestamp | Filing/submission date from the exchange filing index — **not** period-end |
| Window | DISCOVERY + FINAL_OOS coverage: filings public from ~2017-01 onward (lookback for TTM) |
| Survivorship | All securities listed at any point in-window, incl. later delisted/merged |
| Statements needed | P&L (revenue, net income, EBIT), Balance sheet (equity/book, total assets, total debt, shares o/s), Cash flow (CFO — for accruals) |
| Storage | New PIT fundamentals tables via **Alembic migration** (CLAUDE.md §2); SQLAlchemy ORM; no raw SQL |

**Explicitly out of scope (forbidden / deferred):** yfinance/any latest-only feed (§1);
analyst estimates, guidance, intraday; non-ISIN keying; scraping anything without an
`available_date`. Daily refresh / live operation is a later concern — this build targets the
*historical* PIT panel for DISCOVERY + the one-shot FINAL_OOS.

---

## 3. Build components (each a task in the eventual `02_TRACK_B_TASKS.md`)

One layer at a time, each with its own test (Rule 9), to spec-01 standard:

1. **Survivorship-free universe master.** Assemble the ISIN set listed at any point in-window
   incl. delisted; record list/delist dates. Cross-check against the v2 price universe.
2. **Filing index ingest (the PIT clock).** For each ISIN, the table of filings with
   `period_end`, `available_date` (public filing timestamp), statement type, and a pointer to
   the document. This table *is* the look-ahead guard.
3. **XBRL parser → standardized line items.** Map heterogeneous Ind-AS tags to a fixed schema
   (revenue, net_income, ebit, total_equity, total_assets, total_debt, shares_outstanding,
   cfo). Unmapped/odd taxonomies are logged, never silently zero-filled (Rule 12).
4. **Restatement handling.** Keep **all** versions of a period's figures keyed by
   `available_date`; the as-of reader picks the latest version with `available_date ≤ D`.
5. **As-of reader (the factor-facing API).** `read_fundamentals_asof(isin, D) → line items`
   honoring `available_date ≤ D − lag`. **Safety lag = 2 trading days** after filing
   (§8.4 locked). This is the single chokepoint every Track-B factor calls — no factor reads
   the raw tables directly.
6. **Corporate-action consistency.** Reconcile shares-outstanding / per-share figures with the
   v2 price layer's adjustment basis so earnings-yield and B/P are internally consistent.

Idempotent + checkpointed ingest (CLAUDE.md §1): re-running a stage never duplicates;
per-ISIN failures log to `PipelineError`, never crash the run; `classify_error` for failures.

---

## 4. Factors this unlocks (Track B — defined fully in the factor prereg, NOT here)

Listed only to confirm the data scope is sufficient; their definitions, hypotheses, and grids
are committed in `03_TRACK_B_PREREG.md` **after** this data passes §6 — not now.

| Factor | Needs | Family |
|---|---|---|
| Earnings yield (TTM E/P or EBIT/EV) | net income / ebit, market cap | Value |
| Book-to-price | total_equity, market cap | Value |
| ROE (TTM) | net income, total_equity | Quality |
| Accruals (low = quality) | net income, cfo, total_assets | Quality |
| Leverage (low = quality) | total_debt, total_equity | Quality |

These are the genuinely momentum-orthogonal factors — the H3 fix §6.4 needs.

---

## 5. Frozen splits (unchanged — discipline carries over)

- Same v2 frozen `DISCOVERY` (2018-02-06 → 2023-06-30) and `FINAL_OOS`
  (2023-07-01 → 2026-06-12). **FINAL_OOS is still pristine** (Track A never consumed it).
- Building / auditing this data layer touches **no** backtest split — data acceptance (§6) is a
  data-quality gate, not a performance measurement, so it does not move the measuring stick.
- The Track-B candidate, once selected on DISCOVERY under `03_TRACK_B_PREREG.md`, runs on
  `FINAL_OOS` **exactly once**.

---

## 6. Data acceptance gate (must PASS before the factor prereg is written)

Pure data-quality checks — **no factor returns, no Calmar.** All on the historical panel:

1. **Coverage (dual gate — both must hold at each monthly rebalance date).** Of the DISCOVERY
   universe, ≥ **90% by market-cap weight AND ≥ 75% by name** has ≥ 1 usable TTM fundamental
   set available (§8.2 locked). The weight floor certifies the large caps are covered; the
   **by-name floor guards breadth** — it fails a cap-heavy but name-thin panel that could pass
   on weight alone, because such a panel cannot support the broad, de-concentrated portfolio
   Track B is being built to test (§6.2 / H3). The 75% (not 90%+) by-name level tolerates that
   the messy/late-filing SME tail may legitimately lack clean fundamentals.
2. **PIT integrity.** No record is ever readable before its `available_date`; an automated
   replay confirms `available_date ≤ D` for every figure returned by the as-of reader at a
   sample of historical `D`s. Zero violations — hard fail on any (Rule 12).
3. **Survivorship presence.** A pre-listed set of known in-window delistings (assembled
   independently) is present in the panel for the dates they traded. Hard fail if any are
   silently absent.
4. **Look-ahead replay.** Reconstruct fundamentals "as known on" a historical date and confirm
   no later-filed/restated figure leaks in (tests §3.4 + §3.5 end-to-end).
5. **Reconciliation.** A random sample of **30 ISIN-quarters** reconciles computed line items
   against the actual filed statements within **±2% per line item** (§8.3 locked; manual
   spot-audit, logged).

Coverage and reconciliation tolerances (C, N, tolerance, safety-lag) were **pre-committed in
§8 before building** — not tuned to whatever the ingest happens to yield (that would be the v1
sin applied to data).

---

## 7. Sequencing (how this feeds the factor prereg)

```
THIS SPEC (02)  →  lock §8  →  build §3 components  →  pass §6 acceptance gate
                                                              │
                                                              ▼
                          03_TRACK_B_PREREG.md  (commit value/quality factors,
                          H3 test, coarse grids — BEFORE any backtest)
                                                              │
                                                              ▼
                          02_TRACK_B_TASKS.md execution on DISCOVERY (§6 of 00),
                          then the one-shot FINAL_OOS, same §9 DoD bar as v2
```

If §6 cannot be passed (data too sparse / too biased to trust), Track B stops here and v3
closes as a research note per `00_PREREGISTRATION.md` §10 — FINAL_OOS stays pristine. That is
a legitimate outcome; manufacturing coverage by loosening §6 after the fact is not.

---

## 8. Locked decisions (Arafat, 2026-06-17) — pre-committed before any ingest

These were fixed **before** building; the §6 gate reads them and may not introduce a new or
loosened threshold (TB7 / Rule 12). TB0 transcribes them verbatim into
`app/fundamentals/data_config.py` as frozen constants.

1. **Exchange priority & dedup — NSE-primary + BSE fallback.** NSE's filing is canonical per
   ISIN-period; BSE is read only where NSE has no record. One source of truth, lower parser
   cost; BSE-only / SME coverage is best-effort. No cross-exchange reconciliation in this build.
   **Escalation (not HARKing):** if TB7's 75%-by-name floor fails *specifically* due to
   BSE-only gaps, upgrading to full both-exchange ingest is a sanctioned remedy — it pulls
   *more input* against an *unchanged* threshold, so it does not move the measuring stick.
2. **Coverage threshold = 90% by market-cap weight AND 75% by name** — dual gate, both must
   hold (§6.1). The weight floor certifies large-cap coverage; the **by-name floor guards
   breadth** so a cap-heavy/name-thin panel (which would pass weight-only) fails here rather
   than silently crippling the de-concentrated portfolio Track B exists to test. 75% by name
   (not higher) tolerates the genuinely sparse SME filing tail.
3. **Reconciliation _N_ = 30 ISIN-quarters, tolerance ±2% per line item** (§6.5). Enough to
   catch systematic parse / tag-mapping errors; ±2% absorbs rounding/units noise without
   hiding a real mismatch.
4. **Safety lag = 2 trading days** after `available_date` (§3.5; revised up from the
   initially-chosen 1 day on review). The as-of reader serves a filing only once
   `available_date ≤ D − 2 trading days`. Fundamentals are quarterly, so the extra day's
   staleness is immaterial to a value/quality signal, while the second day is cheap insurance
   against `available_date` timestamp imprecision (date-only stamps, dissemination lag) — and
   zero look-ahead is the entire reason this layer exists (the v1 yfinance ban, §1.1).
5. **Restatement policy = as-of-latest-version-known** (§3.4). Keep every version keyed by
   `available_date`; the reader returns the latest version with `available_date ≤ D − lag`.
6. **Scope cap = historical PIT panel only.** No live / daily refresh in this build; target is
   the DISCOVERY panel + the one-shot FINAL_OOS window.
7. **Build vehicle = new `backend/app/fundamentals/` package + Alembic migration**, run under
   `backend/venv/`; all exchange fetches mocked in tests (CLAUDE.md §2/§4/§5).

`02_TRACK_B_TASKS.md` decomposes the build (TB0→TB7) — same one-layer-at-a-time, test-gated
discipline as `01_TRACK_A_TASKS.md`. TB0 is now unblocked.
