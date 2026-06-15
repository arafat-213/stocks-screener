"""
backtest_v2 — v2 simulation core (time-driven daily loop).

Separate from backtest/ (v1). v1 stays runnable in parallel.
Build order: types → config → costs → signals → regime → portfolio → engine → metrics.
"""
