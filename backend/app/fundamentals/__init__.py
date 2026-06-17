"""
fundamentals — Track-B survivorship-free, point-in-time fundamentals data layer.

Built per specs/v3/02_TRACK_B_DATA.md, decomposed in specs/v3/02_TRACK_B_TASKS.md
(TB0→TB7). Kept entirely separate from backtest_v2/ so the v2/v3 price pipeline
stays runnable. This is a DATA layer only — no Track-B factor is defined here and
no backtest is run; FINAL_OOS is never touched from this package.

Build order: data_config (TB0) → schema/ORM (TB1) → universe master (TB2) →
filing index (TB3) → XBRL parser (TB4) → as-of reader (TB5) → corp-action
consistency (TB6) → §6 acceptance gate (TB7).
"""
