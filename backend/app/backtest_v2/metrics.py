"""
metrics.py — daily-MTM absolute metrics (T8).

Computes from EngineResult:
  - CAGR, Sharpe (daily returns × √252), Sortino, annualized vol
  - Max drawdown (peak-to-trough), DD duration, Calmar = CAGR / maxDD
  - Avg/median exposure, time-in-cash %
  - Annualized turnover + per-rebalance series (warns if > 1000%)
  - Per-name diagnostics: realized P&L, hold period, hit rate

Benchmark-relative metrics (excess CAGR, IR, benchmark Calmar, capture)
are spec 03 — not computed here.  Leave the seam clean.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

import numpy as np

from app.backtest_v2.types import Fill

if TYPE_CHECKING:
    from app.backtest_v2.engine import EngineResult

log = logging.getLogger(__name__)

_TRADING_DAYS_PER_YEAR = 252.0
_CALENDAR_DAYS_PER_YEAR = 365.25
# Annualized turnover above this fraction (= 1000%) is a red flag.
_ABSURD_TURNOVER = 10.0


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PerNameStats:
    """Realized diagnostics for one ISIN over the backtest."""

    isin: str
    symbol: str
    buy_notional: float  # total ₹ spent on buys
    sell_notional: float  # total ₹ received on sells/trims
    cost_paid: float  # total transaction costs for this ISIN
    realized_pnl: float  # sell_notional − buy_notional − cost_paid
    n_buys: int
    n_sells: int  # sell + trim fills
    hold_days: float  # calendar days from first buy to last sell (NaN if still open)
    is_closed: bool  # True if at least one sell fill exists


@dataclass
class BacktestMetrics:
    """All absolute metrics computed from one EngineResult."""

    # ---- Return / risk -------------------------------------------------
    cagr: float  # calendar-time CAGR (annualized)
    sharpe: float  # daily-MTM Sharpe: mean(r)/std(r) × √252
    sortino: float  # downside Sharpe: mean(r)/downside_std × √252
    annualized_vol: float  # std(daily returns) × √252

    # ---- Drawdown ------------------------------------------------------
    max_drawdown: float  # peak-to-trough as positive fraction (0.25 = 25% loss)
    max_dd_duration_days: int  # calendar days from peak to trough in worst episode
    calmar: float  # CAGR / max_drawdown  (nan if max_drawdown == 0)

    # ---- Exposure ------------------------------------------------------
    avg_exposure: float  # mean(exposure) across all trading days
    median_exposure: float  # median(exposure)
    time_in_cash_pct: float  # fraction of days where exposure < 1.0

    # ---- Turnover ------------------------------------------------------
    annualized_turnover: float  # Σ rebalance turnover / n_years
    per_rebalance_turnover: list[tuple[date, float]] = field(default_factory=list)
    turnover_is_absurd: bool = False  # True if annualized > 1000%

    # ---- Diagnostics ---------------------------------------------------
    n_fills: int = 0
    total_cost_paid: float = 0.0
    per_name_stats: list[PerNameStats] = field(default_factory=list)
    hit_rate: float = float("nan")  # % of closed ISINs with positive realized P&L

    # ---- Period --------------------------------------------------------
    start_date: date | None = None
    end_date: date | None = None
    n_calendar_days: int = 0
    n_trading_days: int = 0
    start_equity: float = 0.0
    end_equity: float = 0.0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def compute_metrics(result: "EngineResult") -> BacktestMetrics:
    """
    Compute all absolute metrics from an EngineResult.

    Parameters
    ----------
    result : EngineResult
        The completed backtest run (from engine.run).

    Returns
    -------
    BacktestMetrics
        All absolute metrics.  Benchmark-relative metrics are spec 03.
    """
    snapshots = result.snapshots
    if not snapshots:
        raise ValueError("EngineResult.snapshots is empty — run produced no data.")

    # ---- Equity series ------------------------------------------------
    equities = np.array([s.equity for s in snapshots], dtype=float)
    dates: list[date] = [s.date for s in snapshots]

    start_date = dates[0]
    end_date = dates[-1]
    n_calendar_days = (end_date - start_date).days
    n_trading_days = len(snapshots)
    start_equity = float(equities[0])
    end_equity = float(equities[-1])

    # ---- Daily returns (need ≥ 2 points) ------------------------------
    if n_trading_days < 2:
        daily_returns = np.array([], dtype=float)
    else:
        daily_returns = np.diff(equities) / equities[:-1]

    # ---- CAGR ---------------------------------------------------------
    years = n_calendar_days / _CALENDAR_DAYS_PER_YEAR
    if years > 0 and start_equity > 0:
        cagr = (end_equity / start_equity) ** (1.0 / years) - 1.0
    else:
        cagr = 0.0

    # ---- Sharpe / vol -------------------------------------------------
    if len(daily_returns) > 1:
        mean_ret = float(np.mean(daily_returns))
        std_ret = float(np.std(daily_returns, ddof=1))
        annualized_vol = std_ret * math.sqrt(_TRADING_DAYS_PER_YEAR)
        sharpe = (
            (mean_ret / std_ret) * math.sqrt(_TRADING_DAYS_PER_YEAR)
            if std_ret > 0
            else 0.0
        )
    else:
        mean_ret = 0.0
        std_ret = 0.0
        annualized_vol = 0.0
        sharpe = 0.0

    # ---- Sortino (downside deviation only) ----------------------------
    downside = daily_returns[daily_returns < 0.0]
    if len(downside) > 1:
        downside_std = float(np.std(downside, ddof=1))
        sortino = (
            (mean_ret / downside_std) * math.sqrt(_TRADING_DAYS_PER_YEAR)
            if downside_std > 0
            else 0.0
        )
    else:
        sortino = 0.0

    # ---- Max drawdown + duration -------------------------------------
    max_drawdown, max_dd_duration_days = _compute_max_drawdown(equities, dates)

    # ---- Calmar -------------------------------------------------------
    calmar = cagr / max_drawdown if max_drawdown > 0 else float("nan")

    # ---- Exposure stats -----------------------------------------------
    exposures = np.array([s.exposure for s in snapshots], dtype=float)
    avg_exposure = float(np.mean(exposures))
    median_exposure = float(np.median(exposures))
    time_in_cash_pct = float(np.mean(exposures < 1.0))

    # ---- Turnover -----------------------------------------------------
    annualized_turnover, turnover_is_absurd = _compute_annualized_turnover(
        result.per_rebalance_turnover, start_date, end_date
    )

    # ---- Per-name diagnostics ----------------------------------------
    per_name_stats, hit_rate = _compute_per_name_stats(result.fills_log)

    return BacktestMetrics(
        cagr=cagr,
        sharpe=sharpe,
        sortino=sortino,
        annualized_vol=annualized_vol,
        max_drawdown=max_drawdown,
        max_dd_duration_days=max_dd_duration_days,
        calmar=calmar,
        avg_exposure=avg_exposure,
        median_exposure=median_exposure,
        time_in_cash_pct=time_in_cash_pct,
        annualized_turnover=annualized_turnover,
        per_rebalance_turnover=result.per_rebalance_turnover,
        turnover_is_absurd=turnover_is_absurd,
        n_fills=len(result.fills_log),
        total_cost_paid=result.total_cost_paid,
        per_name_stats=per_name_stats,
        hit_rate=hit_rate,
        start_date=start_date,
        end_date=end_date,
        n_calendar_days=n_calendar_days,
        n_trading_days=n_trading_days,
        start_equity=start_equity,
        end_equity=end_equity,
    )


def summary(m: BacktestMetrics) -> str:
    """Return a compact human-readable metrics table (no benchmark-relative rows)."""
    calmar_str = f"{m.calmar:.2f}" if not math.isnan(m.calmar) else "n/a"
    hr_str = f"{m.hit_rate:.1%}" if not math.isnan(m.hit_rate) else "n/a"
    turnover_flag = " ⚠ ABSURD" if m.turnover_is_absurd else ""
    lines = [
        "=== v2 Backtest Metrics (absolute) ===",
        f"  Period          : {m.start_date} → {m.end_date}  ({m.n_calendar_days}d / {m.n_trading_days} trading days)",
        f"  Equity          : {m.start_equity:,.0f} → {m.end_equity:,.0f}",
        "",
        f"  CAGR            : {m.cagr:+.2%}",
        f"  Sharpe          : {m.sharpe:.2f}",
        f"  Sortino         : {m.sortino:.2f}",
        f"  Ann. Vol        : {m.annualized_vol:.2%}",
        "",
        f"  Max Drawdown    : {m.max_drawdown:.2%}",
        f"  DD Duration     : {m.max_dd_duration_days}d",
        f"  Calmar          : {calmar_str}",
        "",
        f"  Avg Exposure    : {m.avg_exposure:.1%}",
        f"  Median Exposure : {m.median_exposure:.1%}",
        f"  Time-in-Cash    : {m.time_in_cash_pct:.1%}",
        "",
        f"  Ann. Turnover   : {m.annualized_turnover:.1%}{turnover_flag}",
        f"  Rebalances      : {len(m.per_rebalance_turnover)}",
        "",
        f"  Fills           : {m.n_fills}",
        f"  Total Cost Paid : {m.total_cost_paid:,.0f}",
        f"  Names traded    : {len(m.per_name_stats)}",
        f"  Hit Rate        : {hr_str}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_max_drawdown(equities: np.ndarray, dates: list[date]) -> tuple[float, int]:
    """
    Return (max_drawdown_fraction, peak_to_trough_calendar_days).

    max_drawdown is a positive fraction (e.g. 0.25 = 25% loss).
    Duration is from the peak that caused the worst drawdown to its trough.
    """
    if len(equities) < 2:
        return 0.0, 0

    running_peak = float(equities[0])
    peak_date = dates[0]
    max_dd = 0.0
    max_dd_peak_date = dates[0]
    max_dd_trough_date = dates[0]

    for i in range(1, len(equities)):
        e = float(equities[i])
        if e > running_peak:
            running_peak = e
            peak_date = dates[i]
        elif running_peak > 0:
            dd = (running_peak - e) / running_peak
            if dd > max_dd:
                max_dd = dd
                max_dd_peak_date = peak_date
                max_dd_trough_date = dates[i]

    duration = (max_dd_trough_date - max_dd_peak_date).days
    return max_dd, duration


def _compute_annualized_turnover(
    per_rebalance: list[tuple[date, float]],
    start_date: date,
    end_date: date,
) -> tuple[float, bool]:
    """
    Annualized turnover = Σ rebalance_turnover_fractions / n_years.

    Each element of per_rebalance is (date, Σ|Δweight|) from the engine.
    Returns (annualized_turnover, is_absurd) where is_absurd flags > 1000%.
    """
    if not per_rebalance:
        return 0.0, False

    total = sum(t for _, t in per_rebalance)
    days = (end_date - start_date).days
    years = days / _CALENDAR_DAYS_PER_YEAR if days > 0 else 1.0
    ann = total / years
    is_absurd = ann > _ABSURD_TURNOVER
    if is_absurd:
        log.warning(
            "Annualized turnover %.0f%% exceeds 1000%% — inspect rebalance logic.",
            ann * 100,
        )
    return ann, is_absurd


def _compute_per_name_stats(
    fills_log: list[Fill],
) -> tuple[list[PerNameStats], float]:
    """
    Aggregate fills by ISIN → realized P&L, hold period, hit rate.

    Realized P&L = sell_notional − buy_notional − cost_paid.
    Hold period  = calendar days from first buy to last sell (NaN if still open).
    Hit rate     = fraction of closed ISINs (at least one sell) with P&L > 0.
    """
    by_isin: dict[str, list[Fill]] = {}
    for f in fills_log:
        by_isin.setdefault(f.isin, []).append(f)

    stats: list[PerNameStats] = []
    n_closed = 0
    n_profitable = 0

    for isin, fills in by_isin.items():
        symbol = fills[-1].symbol
        buys = [f for f in fills if f.side == "buy"]
        sells = [f for f in fills if f.side in ("sell", "trim")]

        buy_notional = sum(f.qty * f.price for f in buys)
        sell_notional = sum(f.qty * f.price for f in sells)
        cost_paid = sum(f.cost_rupees for f in fills)
        realized_pnl = sell_notional - buy_notional - cost_paid

        first_buy_date = min((f.date for f in buys), default=None) if buys else None
        last_sell_date = max((f.date for f in sells), default=None) if sells else None

        if first_buy_date is not None and last_sell_date is not None:
            hold_days = float((last_sell_date - first_buy_date).days)
        else:
            hold_days = float("nan")  # still held or only sells (edge case)

        is_closed = bool(sells)
        if is_closed:
            n_closed += 1
            if realized_pnl > 0:
                n_profitable += 1

        stats.append(
            PerNameStats(
                isin=isin,
                symbol=symbol,
                buy_notional=buy_notional,
                sell_notional=sell_notional,
                cost_paid=cost_paid,
                realized_pnl=realized_pnl,
                n_buys=len(buys),
                n_sells=len(sells),
                hold_days=hold_days,
                is_closed=is_closed,
            )
        )

    hit_rate = float(n_profitable / n_closed) if n_closed > 0 else float("nan")
    return stats, hit_rate
