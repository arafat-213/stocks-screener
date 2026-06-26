"""regime_overlay — v5/00 Direction-D: the frozen v4 regime score as a deploy
throttle on Nifty 50 TRI vs a real-short-rate defensive leg.

A small, self-contained one-instrument simulator (NOT the backtest_v2 / swing_v4
engines). It reuses the frozen signal (``swing_v4.regime.RegimeScore``), the project
cost model (``backtest_v2.costs``), the TRI loader (``backtest_v2.benchmark``), and
the drawdown/CAGR helpers (``backtest_v2.metrics``). See ``specs/v5/00``.
"""
