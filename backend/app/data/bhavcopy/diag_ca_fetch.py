"""Phase 0 probe — pin the CA fetch failure mode (Spec 05 §5 Phase 0).

Read-only: makes live NSE calls, writes no files, changes no data.

What this checks
----------------
1. Full-range fetch (2017-01-01 → 2026-06-12): total records returned.
2. Chunked monthly fetches over the same span: total records when queried in
   ≤1-month windows.  Compares count to (1) to confirm the per-query window cap.
3. CUPID-specific check (ISIN INE509F01029, ex-date 2026-03-09):
   - Present in a narrow 60-day window around ex-date?  (proves CA data exists)
   - Present in the full-range fetch?  (proves the cap drops it)

Run from backend/:
    venv/bin/python -m app.data.bhavcopy.diag_ca_fetch

Expected outcome:
  full-range  → very few records (O(10–100), truncated by NSE)
  chunked sum → O(10 000–30 000) records (full coverage)
  CUPID       → absent from full-range, present in narrow window

Outputs a human-readable summary + exits non-zero if the cap cannot be
confirmed (so CI could gate on it, though this is for one-off diagnosis).
"""

import logging
import sys
import time
from datetime import date, timedelta

import pandas as pd

from app.data.bhavcopy.corporate_actions import (
    CA_DATE_FMT,
    fetch_corporate_actions,
    parse_corporate_actions,
)
from app.data.bhavcopy.download import build_session

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)

# ── constants ──────────────────────────────────────────────────────────────────
FLOOR_START = date(2017, 1, 1)  # same start used for the actual build
FLOOR_END = date(2026, 6, 12)  # same end used for the floor run

CUPID_ISIN = "INE509F01029"
CUPID_EXDATE = date(2026, 3, 9)
CUPID_NARROW_START = date(2026, 1, 9)  # 60 days before ex-date
CUPID_NARROW_END = date(2026, 5, 8)  # 60 days after ex-date

CHUNK_MONTHS = 1  # window size for the chunked probe

INTER_REQUEST_SLEEP = 1.5  # seconds; be polite to NSE


# ── helpers ───────────────────────────────────────────────────────────────────
def _month_windows(start: date, end: date):
    """Yield (win_start, win_end) pairs in CHUNK_MONTHS-month steps."""
    cur = start
    while cur <= end:
        # advance by CHUNK_MONTHS months
        month = cur.month - 1 + CHUNK_MONTHS
        year = cur.year + month // 12
        month = month % 12 + 1
        nxt = date(year, month, 1)
        win_end = min(nxt - timedelta(days=1), end)
        yield cur, win_end
        cur = nxt


def _cupid_in(records: list[dict]) -> bool:
    """Return True if CUPID's split event is in *records*."""
    for r in records:
        if r.get("isin", "").strip() == CUPID_ISIN:
            raw = (r.get("exDate") or "").strip()
            try:
                ex = pd.to_datetime(raw, format=CA_DATE_FMT).date()
                if ex == CUPID_EXDATE:
                    return True
            except Exception:
                pass
    return False


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    session = build_session()
    try:
        return _run(session)
    finally:
        session.close()


def _run(session) -> int:
    sep = "─" * 68
    print(sep)
    print("Phase 0 — CA fetch window-cap probe")
    print(f"Full range: {FLOOR_START} → {FLOOR_END}")
    print(sep)

    # ── 1. Full-range fetch ────────────────────────────────────────────────
    print("\n[1/3] Full-range fetch …")
    full_records = fetch_corporate_actions(
        FLOOR_START,
        FLOOR_END,
        session=session,
        max_retries=3,
        backoff=2.0,
        sleep=time.sleep,
    )
    full_count = len(full_records)
    cupid_in_full = _cupid_in(full_records)
    full_ca = parse_corporate_actions(full_records)
    full_events = len(full_ca.events)
    print(f"  raw records returned : {full_count:,}")
    print(f"  parsed events        : {full_events:,}")
    print(f"  CUPID split present  : {cupid_in_full}")

    time.sleep(INTER_REQUEST_SLEEP)

    # ── 2. Chunked monthly fetches ─────────────────────────────────────────
    print(f"\n[2/3] Chunked fetch ({CHUNK_MONTHS}-month windows) …")
    windows = list(_month_windows(FLOOR_START, FLOOR_END))
    chunked_total = 0
    window_counts = []
    for i, (ws, we) in enumerate(windows):
        recs = fetch_corporate_actions(
            ws,
            we,
            session=session,
            max_retries=3,
            backoff=2.0,
            sleep=time.sleep,
        )
        n = len(recs)
        chunked_total += n
        window_counts.append((ws, we, n))
        print(f"  {ws} → {we}: {n:>5,} records", flush=True)
        if i < len(windows) - 1:
            time.sleep(INTER_REQUEST_SLEEP)

    # Re-collect: windows are already done; reassemble from window_counts isn't
    # possible without storing records.  Re-fetch is expensive, so just report
    # raw count and spot-check CUPID separately.

    print(f"\n  total chunked raw records : {chunked_total:,}")
    print(f"  full-range raw records    : {full_count:,}")

    ratio = chunked_total / full_count if full_count else float("inf")
    if full_count == 0:
        cap_msg = "FULL RANGE RETURNED 0 — API likely returning empty for large window"
    elif ratio >= 5:
        cap_msg = f"CONFIRMED window cap: chunked is {ratio:.0f}× larger"
    elif ratio >= 2:
        cap_msg = f"LIKELY window cap: chunked is {ratio:.1f}× larger"
    else:
        cap_msg = f"INCONCLUSIVE: ratio only {ratio:.2f}× (may not be a window cap)"

    print(f"\n  => {cap_msg}")

    time.sleep(INTER_REQUEST_SLEEP)

    # ── 3. CUPID narrow-window check ───────────────────────────────────────
    print(
        f"\n[3/3] CUPID narrow-window check ({CUPID_NARROW_START} → {CUPID_NARROW_END}) …"
    )
    narrow_records = fetch_corporate_actions(
        CUPID_NARROW_START,
        CUPID_NARROW_END,
        session=session,
        max_retries=3,
        backoff=2.0,
        sleep=time.sleep,
    )
    cupid_in_narrow = _cupid_in(narrow_records)
    narrow_count = len(narrow_records)
    print(f"  narrow window records: {narrow_count:,}")
    print(f"  CUPID split present  : {cupid_in_narrow}")

    # Show CUPID's record if found
    if cupid_in_narrow:
        for r in narrow_records:
            if r.get("isin", "").strip() == CUPID_ISIN:
                raw = (r.get("exDate") or "").strip()
                try:
                    ex = pd.to_datetime(raw, format=CA_DATE_FMT).date()
                    if ex == CUPID_EXDATE:
                        print(
                            f"  CUPID record: symbol={r.get('symbol')} "
                            f"exDate={raw} subject={r.get('subject', '')[:80]}"
                        )
                except Exception:
                    pass

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    print(sep)
    print("SUMMARY")
    print(sep)
    print(
        f"  Full-range ({FLOOR_START}→{FLOOR_END}): {full_count:,} raw records, "
        f"{full_events:,} parsed events"
    )
    print(
        f"  Chunked  ({CHUNK_MONTHS}-month windows) : {chunked_total:,} raw records total"
    )
    print(f"  CUPID in full-range fetch  : {cupid_in_full}")
    print(f"  CUPID in narrow fetch      : {cupid_in_narrow}")
    print()

    # Determine failure mode
    failure_mode = None
    if cupid_in_narrow and not cupid_in_full and ratio >= 2:
        failure_mode = "WINDOW_CAP"
        print("FAILURE MODE: WINDOW_CAP")
        print("  The NSE API truncates results for large date spans.")
        print("  A 1-month window returns full data; the full-range call is truncated.")
        print("  Fix: chunk the CA fetch into ≤1-month windows (Phase 1).")
    elif not cupid_in_narrow and not cupid_in_full:
        failure_mode = "DATA_NOT_IN_FEED"
        print("FAILURE MODE: DATA_NOT_IN_FEED")
        print("  CUPID is absent even from the narrow window — the action may not be")
        print("  in the NSE CA feed at all (parse miss or ISIN join mismatch).")
    elif cupid_in_full and cupid_in_narrow:
        failure_mode = "DATA_PRESENT_BUG_ELSEWHERE"
        print("FAILURE MODE: DATA_PRESENT_IN_FEED — bug is NOT in fetch coverage.")
        print("  CUPID is in the full-range fetch. The adjustment bug is elsewhere")
        print("  (possibly in parse, factor math, or store).")
    else:
        failure_mode = "UNCLEAR"
        print("FAILURE MODE: UNCLEAR — manual review needed.")

    print(sep)
    print()

    # Exit code: 0 = window cap confirmed (expected); non-zero = unexpected
    if failure_mode == "WINDOW_CAP":
        return 0
    else:
        print(f"WARNING: unexpected failure mode '{failure_mode}' — investigate.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
