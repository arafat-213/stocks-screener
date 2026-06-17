"""
tb0_5_probe — TB0.5 feasibility-probe, Part A (the §6.1 denominator).

Computes the *liquidity-eligible* universe size (the §6.1 pinned denominator)
on a handful of DISCOVERY rebalance dates by reusing the v2 price layer and the
v2 entry-gate `adv_20` liquidity floor — NOT raw `universe_membership`. This is
the denominator the by-name coverage floor (75%) is measured against in TB7.

Part A is fully offline (local parquet only, no network). It is the *only* half
of TB0.5 that can be produced without fetching real NSE/BSE XBRL; Part B
(standard-tag parseability of those names) needs real filings and is gated on an
explicit network-scope decision (see the TB0.5 session log).

Run: backend/venv/bin/python -m app.fundamentals.tb0_5_probe
"""

from __future__ import annotations

import argparse
import random
import re
import time
from datetime import date, datetime

import pandas as pd

from app.backtest_v2.config import MomentumConfig
from app.backtest_v2.engine import _rebalance_dates
from app.data.bhavcopy import store
from app.fundamentals.data_config import COVERAGE_THRESHOLD_NAME

# Frozen DISCOVERY split (validation.py) — referenced for date ranges only,
# never consumed as an evaluation window here.
DISCOVERY_START = date(2018, 2, 6)
DISCOVERY_END = date(2023, 6, 30)

# --- Part B (live parseability probe) constants ----------------------------
SAMPLE_PER_DATE = 20  # liquidity-eligible names sampled per rebalance date
RANDOM_SEED = 20260617  # reproducible sample
REQUEST_SLEEP_S = 0.5  # polite spacing between NSE hits
HTTP_TIMEOUT_S = 15
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
_FIN_RESULTS_API = (
    "https://www.nseindia.com/api/corporates-financial-results"
    "?index=equities&symbol={symbol}&period={period}"
)
# Broadened source (re-probe): pool Annual + Half-Yearly + Quarterly feeds.
# A name's full-year balance sheet (total_equity) often arrives via its Q4
# quarterly / half-yearly filing rather than the Annual feed, so the annual-only
# run undercounted availability (bucket-a) for names like TATAMOTORS/SPICEJET.
# Pooling these is a §8.1 "more INPUT, same threshold" lever — it never lowers
# the 75% §6.1 floor. Modelled like the real as-of reader: a line item counts as
# available if it resolves to a standard tag in ANY recent (<= as_of) filing.
_PERIODS = ("Annual", "Half-Yearly", "Quarterly")
_MAX_XBRL_DOWNLOADS = 4  # lazy per-name cap across pooled filings (early-stop)
# The standard Ind-AS taxonomy namespace prefix mandated for NSE/BSE filings.
_STD_NS_PREFIX = "in-bse-fin"
_STD_NS_MARKER = "in-bse-fin"  # must appear in the xmlns URI for that prefix
# Core line items → accepted STANDARD local-names (first = primary).
# `ProfitLossForThePeriod` and `ProfitLossFromOrdinaryActivitiesAfterTax` are the
# PAT-family elements used by banks/NBFCs (and older-taxonomy commercial filings)
# — verified present under the STANDARD in-bse-fin namespace in SOUTHBANK/DCBBANK/
# BANKINDIA filings during the tightening diagnostic (2026-06-17). They are NOT
# custom extensions; adding them corrects an incomplete recognizer (a false
# `missing-standard:net_income`), tightening the conservative lower bound toward
# true coverage WITHOUT touching the 75% floor.
_NET_INCOME_TAGS = (
    "ProfitLossForPeriod",
    "ProfitLossForPeriodFromContinuingOperations",
    "ProfitLossForThePeriod",
    "ProfitLossFromOrdinaryActivitiesAfterTax",
)
# Total equity is reported either as a single balance-sheet element (newer,
# full-BS results XBRL) OR — in the DISCOVERY-era results XBRL — as its standard
# Ind-AS components (paid-up share capital + reserves), which is the canonical
# derivation, NOT a custom extension. Either standard form counts.
_TOTAL_EQUITY_DIRECT_TAGS = ("Equity", "EquityAttributableToOwnersOfParent")
_EQUITY_SHARE_CAPITAL_TAG = "PaidUpValueOfEquityShareCapital"
_EQUITY_RESERVES_TAG = "ReserveExcludingRevaluationReserves"


def liquidity_eligible_isins(
    prices_on_day: pd.DataFrame, liq_floor_rupees: float
) -> list[str]:
    """ISINs whose adv_20 clears the liquidity floor on a single trading day."""
    eligible = prices_on_day.loc[
        prices_on_day["adv_20"].notna() & (prices_on_day["adv_20"] >= liq_floor_rupees)
    ]
    return sorted(eligible["isin"].unique().tolist())


def _snap_to_rebalance(requested: list[date], rebal: list) -> list:
    """Snap each requested calendar date to the nearest monthly rebalance date
    in the panel (the probe keys Part-A/B off actual rebalance timestamps).
    De-duplicated, sorted. A requested date with no rebalance within the panel
    still snaps to the closest available one (surfaced by the printed date)."""
    snapped = []
    for req in requested:
        req_ts = pd.Timestamp(req)
        nearest = min(rebal, key=lambda d: abs((d - req_ts).days))
        snapped.append(nearest)
    return sorted(set(snapped))


def _parse_dt(s: str) -> date | None:
    """NSE date strings like '31-Mar-2024' -> date; None on failure."""
    try:
        return datetime.strptime(s.strip(), "%d-%b-%Y").date()
    except (ValueError, AttributeError):
        return None


def _std_namespace_ok(xbrl_text: str) -> bool:
    """True iff the in-bse-fin prefix maps to the standard Ind-AS taxonomy URI
    (guards against a filing aliasing the prefix to a custom namespace)."""
    m = re.search(rf'xmlns:{_STD_NS_PREFIX}="([^"]+)"', xbrl_text[:6000])
    return bool(m and _STD_NS_MARKER in m.group(1))


def _has_standard_numeric(xbrl_text: str, local_names: tuple[str, ...]) -> bool:
    """True iff any accepted local-name appears under the standard prefix with a
    numeric body (conservative: custom-namespace or non-numeric/absent = miss)."""
    for ln in local_names:
        # <in-bse-fin:ProfitLossForPeriod ...>-123.45</in-bse-fin:ProfitLossForPeriod>
        pat = rf"<{_STD_NS_PREFIX}:{ln}\b[^>]*>\s*(-?\d[\d,]*\.?\d*)\s*</{_STD_NS_PREFIX}:{ln}>"
        if re.search(pat, xbrl_text):
            return True
    return False


def _eq_in_doc(txt: str) -> bool:
    """total_equity present as a direct element OR the standard component pair."""
    return _has_standard_numeric(txt, _TOTAL_EQUITY_DIRECT_TAGS) or (
        _has_standard_numeric(txt, (_EQUITY_SHARE_CAPITAL_TAG,))
        and _has_standard_numeric(txt, (_EQUITY_RESERVES_TAG,))
    )


def classify_name(session, symbol: str, as_of: date) -> tuple[str, str]:
    """
    Conservative standard-tag parseability for one name as of `as_of`, pooling
    the Annual + Half-Yearly + Quarterly NSE feeds (the broadened re-probe).

    A line item is "available" if it resolves to a STANDARD numeric tag in ANY
    recent (period-end <= as_of) filing — modelling the real as-of reader, which
    stitches the latest-known value per item across filings. Tag-mapping stays
    conservative (custom/extension/absent = miss), so the broadening adds INPUT
    only, never lowers the 75% floor.

    Returns (bucket, note) where bucket is one of:
      'a' — no usable XBRL document on/before as_of (or all fetches failed)
      'b' — document(s) present but core items not resolvable to STANDARD tags
      'c' — both net_income AND total_equity resolve to standard Ind-AS tags
    """
    import requests  # local import: live-only dependency

    rows: list[tuple[str, dict]] = []
    list_ok = False
    for period in _PERIODS:
        try:
            url = _FIN_RESULTS_API.format(symbol=symbol, period=period)
            r = session.get(url, timeout=HTTP_TIMEOUT_S).json()
        except (requests.RequestException, ValueError):
            continue
        if isinstance(r, list):
            list_ok = True
            rows.extend((period, row) for row in r)
        time.sleep(REQUEST_SLEEP_S)
    if not list_ok:
        return "a", "list-fetch-fail"
    if not rows:
        return "a", "no-filings"

    # Distinct XBRL docs whose period end <= as_of (rough PIT). Order by
    # FILING-TYPE first, NOT raw recency: total_equity (the balance sheet) is
    # reported only in Annual/Half-Yearly XBRL — Indian Quarterly results XBRL is
    # P&L-only — so a newest-first walk would spend the download budget on
    # quarterly P&L docs and never reach the equity. Checking a BS-bearing filing
    # first yields BOTH net_income and total_equity in one download (early-stop).
    # An "Old"-format filing carries a "-" placeholder (no XBRL document) — that
    # is bucket (a) "no XBRL exists", NOT (b) — so it is excluded here.
    seen: set[str] = set()
    candidates: list[tuple[int, date, str]] = []
    for period, r in rows:
        td = _parse_dt(r.get("toDate", ""))
        x = (r.get("xbrl") or "").strip()
        if td and td <= as_of and x and x not in ("-",) and x.lower().endswith(".xml"):
            if x in seen:
                continue
            seen.add(x)
            rank = _PERIODS.index(period) if period in _PERIODS else len(_PERIODS)
            candidates.append((rank, td, x))
    if not candidates:
        return "a", "no-xbrl-document-on-or-before-date"
    # BS-bearing (Annual, then Half-Yearly) first; newest within each rank.
    candidates.sort(key=lambda c: (c[0], -c[1].toordinal()))

    ni = eq = False
    any_doc_ok = False
    downloaded = 0
    for _rank, _td, xbrl_url in candidates:
        if downloaded >= _MAX_XBRL_DOWNLOADS or (ni and eq):
            break
        try:
            resp = session.get(xbrl_url, timeout=HTTP_TIMEOUT_S)
        except requests.RequestException:
            continue
        finally:
            time.sleep(REQUEST_SLEEP_S)
        downloaded += 1
        # A missing/withdrawn document 404s to an HTML error page → skip (a).
        ctype = resp.headers.get("content-type", "")
        txt = resp.text
        if (
            resp.status_code != 200
            or "html" in ctype.lower()
            or "<html" in txt[:300].lower()
            or not _std_namespace_ok(txt)
        ):
            continue
        any_doc_ok = True
        if not ni:
            ni = _has_standard_numeric(txt, _NET_INCOME_TAGS)
        if not eq:
            eq = _eq_in_doc(txt)
    if not any_doc_ok:
        return "a", "xbrl-unavailable"
    if ni and eq:
        return "c", "standard-ok"
    missing = ",".join(
        n for n, ok in (("net_income", ni), ("total_equity", eq)) if not ok
    )
    return "b", f"missing-standard:{missing}"


def run_part_b(
    prices: pd.DataFrame, sample_dates: list, liq_floor_rupees: float
) -> None:
    """Live, bounded standard-tag parseability probe over a seeded sample."""
    import requests

    rng = random.Random(RANDOM_SEED)
    session = requests.Session()
    session.headers.update(_NSE_HEADERS)
    # Warm-up (NSE sets cookies even on a 403 home hit).
    try:
        session.get("https://www.nseindia.com", timeout=HTTP_TIMEOUT_S)
    except requests.RequestException:
        pass

    print("\n=== Part B — standard-tag parseability (LIVE, conservative, RE-PROBE) ===")
    print(
        f"sample={SAMPLE_PER_DATE}/date, seed={RANDOM_SEED}, "
        f"source=NSE XBRL pooled {_PERIODS}, standard ns={_STD_NS_PREFIX}; "
        f"usable=(c)=both net_income & total_equity as standard numeric tags "
        f"in any filing <= as_of\n"
    )
    hdr = f"{'rebalance':<12}{'sampled':>8}{'(a)none':>9}{'(b)nonstd':>10}{'(c)usable':>10}{'cover%':>9}{'vs75%':>8}"
    print(hdr)
    for d in sample_dates:
        as_of = d.date()
        on_day = prices.loc[prices["date"] == d]
        elig = on_day.loc[
            on_day["adv_20"].notna() & (on_day["adv_20"] >= liq_floor_rupees)
        ]
        # ISIN -> symbol as-of this date (symbol can change over time).
        isin_sym = dict(zip(elig["isin"], elig["symbol"]))
        isins = sorted(isin_sym)
        sample = rng.sample(isins, min(SAMPLE_PER_DATE, len(isins)))
        counts = {"a": 0, "b": 0, "c": 0}
        notes: list[str] = []
        for isin in sample:
            sym = isin_sym.get(isin)
            if not sym or not isinstance(sym, str):
                counts["a"] += 1
                notes.append(f"{isin}:no-symbol")
                continue
            bucket, note = classify_name(session, sym, as_of)
            counts[bucket] += 1
            notes.append(f"{sym}:{bucket}:{note}")
            time.sleep(REQUEST_SLEEP_S)
        n = len(sample)
        cover = counts["c"] / n if n else 0.0
        flag = "PASS" if cover >= COVERAGE_THRESHOLD_NAME else "FAIL"
        print(
            f"{str(as_of):<12}{n:>8}{counts['a']:>9}{counts['b']:>10}{counts['c']:>10}"
            f"{cover * 100:>8.1f}%{flag:>8}"
        )
        for ln in notes:
            print(f"    {ln}")
    print(f"\nby-name floor (COVERAGE_THRESHOLD_NAME) = {COVERAGE_THRESHOLD_NAME:.0%}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--live",
        action="store_true",
        help="run Part B (live NSE XBRL parseability probe). Off by default.",
    )
    ap.add_argument(
        "--dates",
        default="",
        help=(
            "comma-separated YYYY-MM-DD list; each snaps to the nearest monthly "
            "rebalance date. Overrides the default first/1-3/2-3/last sample. "
            "Use to fill the 2020/2021-H1 coverage holes (TB0.5 Step-1 re-probe)."
        ),
    )
    args = ap.parse_args()

    cfg = MomentumConfig()
    liq_floor_rupees = cfg.liquidity_floor_cr * 1e7

    prices = store.read_prices_adjusted(start=DISCOVERY_START, end=DISCOVERY_END)
    prices["date"] = pd.to_datetime(prices["date"])

    calendar = sorted(prices["date"].unique())
    calendar_ts = [pd.Timestamp(d) for d in calendar]
    rebal = sorted(_rebalance_dates(calendar_ts, cfg.rebalance))

    n = len(rebal)
    if args.dates.strip():
        requested = [
            datetime.strptime(s.strip(), "%Y-%m-%d").date()
            for s in args.dates.split(",")
            if s.strip()
        ]
        sample = _snap_to_rebalance(requested, rebal)
    else:
        # Default: 4 rebalance dates spread across DISCOVERY: first, ~1/3, ~2/3, last.
        idx = sorted({0, n // 3, (2 * n) // 3, n - 1})
        sample = [rebal[i] for i in idx]

    print(
        f"liquidity floor = Rs {cfg.liquidity_floor_cr:.1f} cr "
        f"(adv_20 >= {liq_floor_rupees:.0f})"
    )
    print(f"DISCOVERY rebalance dates available: {n}  (cadence={cfg.rebalance})")
    print(
        f"price panel: {prices['isin'].nunique()} ISINs, "
        f"{calendar[0]} -> {calendar[-1]}\n"
    )
    print(f"{'rebalance_date':<16}{'names_with_print':>18}{'liq_eligible (>=5cr)':>24}")
    for d in sample:
        on_day = prices.loc[prices["date"] == d]
        names_present = on_day["isin"].nunique()
        elig = liquidity_eligible_isins(on_day, liq_floor_rupees)
        print(f"{str(d.date()):<16}{names_present:>18}{len(elig):>24}")

    if args.live:
        run_part_b(prices, sample, liq_floor_rupees)
    else:
        print("\n(Part B skipped — pass --live to run the NSE parseability probe.)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
