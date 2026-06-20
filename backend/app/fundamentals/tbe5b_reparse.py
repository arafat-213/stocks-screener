"""TBE5b — offline re-parse to populate debt_equity_ratio from cached XBRL docs.

Re-parses every in-window filing using the cached raw XBRL (data/raw/xbrl_cache/).
No live NSE fetch — all 40,125 cached docs are already on disk from the TBE2b pass.
Updates the debt_equity_ratio field in place on matching fundamentals_line_items rows.

Run:
    backend/venv/bin/python -m app.fundamentals.tbe5b_reparse
    backend/venv/bin/python -m app.fundamentals.tbe5b_reparse --no-resume
"""

from __future__ import annotations

import argparse
import datetime

from app.db.models import PipelineRun
from app.db.session import SessionLocal
from app.fundamentals.xbrl_parser import (
    fetch_xbrl_document,
    make_caching_fetcher,
    reparse_line_items,
)

_CACHE_DIR = "data/raw/xbrl_cache"
_RUN_ID = "tbe5b-reparse"


def _date(s: str) -> datetime.date:
    return datetime.datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=_date, default=datetime.date(2019, 4, 1))
    ap.add_argument("--end", type=_date, default=datetime.date(2026, 6, 12))
    ap.add_argument("--cache-dir", default=_CACHE_DIR)
    ap.add_argument("--run-id", default=_RUN_ID)
    ap.add_argument(
        "--no-resume",
        action="store_true",
        help="ignore checkpoint and re-walk every ISIN",
    )
    args = ap.parse_args()

    fetcher = make_caching_fetcher(args.cache_dir, inner=fetch_xbrl_document)
    session = SessionLocal()
    if session.query(PipelineRun).filter_by(run_id=args.run_id).first() is None:
        session.add(PipelineRun(run_id=args.run_id, status="running"))
        session.commit()

    print(
        f"[TBE5b] reparse window {args.start} → {args.end} | cache={args.cache_dir} "
        f"| run_id={args.run_id} | resume={not args.no_resume}"
    )
    try:
        stats = reparse_line_items(
            session,
            fetcher,
            args.run_id,
            period_start=args.start,
            period_end=args.end,
            resume=not args.no_resume,
        )
    finally:
        session.close()

    print("[TBE5b] done:")
    print(f"  filings seen:           {stats.total_filings}")
    print(f"  rows updated:           {stats.rows_updated}")
    print(f"  rows unchanged:         {stats.rows_unchanged}")
    print(f"  rows inserted (gap):    {stats.rows_inserted}")
    print(f"  debt_equity_ratio filled: {stats.de_ratio_filled}")
    print(f"  shares filled:          {stats.shares_filled}")
    print(f"  total_debt filled:      {stats.debt_filled}")
    print(f"  filings failed:         {stats.filings_failed}")
    print(f"  ISINs skipped (ckpt):   {stats.isins_skipped_checkpoint}")
    print(f"  filings w/ unmapped:    {stats.filings_with_unmapped}")


if __name__ == "__main__":
    main()
