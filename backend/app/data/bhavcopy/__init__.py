"""
NSE bhavcopy data layer (v2) — survivorship-free, corporate-action-adjusted
daily OHLCV.

This package is a standalone batch pipeline, independent of the FastAPI app and
the v1 engine (see specs/v2/01_DATA_LAYER.md). Build order:

    download.py          # T2 — fetch raw daily files (legacy + UDiFF) to disk cache
    parse.py             # T3 — parse both schemas -> unified raw rows
    corporate_actions.py # T4 — CA feed -> per-ISIN back-adjustment factors
    adjust.py            # T5 — apply factors -> adjusted OHLC + close_tr
    universe.py          # T6 — point-in-time membership + adv_20 liquidity
    store.py             # T1 — canonical parquet read/write contract  (THIS TASK)
    build.py             # T7 — idempotent, resumable orchestrator
    validate.py          # T8 — acceptance checks (the gate)
"""
