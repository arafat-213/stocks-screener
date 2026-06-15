"""
Cost model (spec 03 T1): statutory charges + DP as a cash deduction;
slippage as an effective fill price adjustment (spec 03 §1.3).

Verified rates (T0, 2026-06-15):
  STT           0.1%    buy + sell   zerodha.com/charges
  Exchange txn  0.00297% buy + sell  revised Oct 1 2024
  SEBI          0.0001% buy + sell
  Stamp duty    0.015%  buy only
  GST           18%     on (exchange txn + SEBI); brokerage = 0
  DP charge     ₹15.34  flat per scrip on sell (CDSL + Zerodha + GST)

Slippage model (spec 03 §1.2):
  participation = order_value / adv_20   (clamped at participation_cap)
  slip_pct      = base_slippage_pct + impact_coeff × participation
  buys  fill at open × (1 + slip_pct)  → higher basis, lower realized return
  sells fill at open × (1 − slip_pct)  → lower proceeds

fill_cost()      → statutory + DP cash deduction only.
effective_price() → slippage-adjusted fill price (used by engine._stamp_fills).

Backward-compatible: CostConfig(round_trip_bps=N) enables the spec-02
flat-bps placeholder path, keeping existing spec-02 test suites passing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

SideLiteral = Literal["buy", "sell", "trim"]
CostLevel = Literal["optimistic", "base", "pessimistic"]


@dataclass
class CostConfig:
    """Real per-fill cost config (spec 03 T0 verified rates).

    All percentage fields are in decimal (0.001 = 0.1%).
    Set round_trip_bps to a float to use the legacy flat-bps path
    (backwards-compat for spec-02 tests — bypasses statutory model).
    """

    # --- Statutory charges ---
    stt_pct: float = 0.001  # STT 0.1% on buy + sell
    exchange_txn_pct: float = 0.0000297  # NSE txn 0.00297% both sides (Oct 2024)
    sebi_pct: float = 0.000001  # SEBI 0.0001% both sides
    stamp_duty_pct: float = 0.00015  # Stamp 0.015% buy only
    gst_pct: float = 0.18  # GST 18% on (exchange + SEBI)
    dp_charge: float = 15.34  # ₹15.34 flat per scrip on sell

    # --- Slippage (applied via effective_price, not fill_cost) ---
    base_slippage_pct: float = 0.0015  # 0.15%/side zero-participation floor
    impact_coeff: float = 0.15  # linear impact per unit participation
    participation_cap: float = 0.10  # hard ceiling: 10% of ADV

    # --- Legacy flat-bps override (spec-02 placeholder compat) ---
    # None → use real statutory model; float → use flat half-RT per leg.
    round_trip_bps: float | None = None

    @classmethod
    def optimistic(cls) -> "CostConfig":
        """Real statutory charges; zero slippage (≈0.3% RT, best-case sensitivity)."""
        return cls(base_slippage_pct=0.0, impact_coeff=0.0)

    @classmethod
    def base(cls) -> "CostConfig":
        """T0-verified statutory + real slippage model (production default)."""
        return cls()

    @classmethod
    def pessimistic(cls) -> "CostConfig":
        """Real statutory + 2× base slippage (worst-case sensitivity)."""
        return cls(base_slippage_pct=0.003, impact_coeff=0.30)


# Injectable cost-function type (signature unchanged from spec-02 placeholder).
CostFn = Callable[[SideLiteral, float, float, float, CostConfig], float]


def fill_cost(
    side: SideLiteral,
    qty: float,
    price: float,
    adv_20: float,  # unused in statutory path; kept for CostFn signature parity
    cfg: CostConfig,
) -> float:
    """Return total ₹ statutory + DP cash deduction for one fill.

    Slippage is NOT included here — it is applied as an effective price
    adjustment in the engine's _stamp_fills step (spec 03 §1.3, option a).

    When cfg.round_trip_bps is set, falls back to the spec-02 flat half-RT
    per leg for backwards compatibility with spec-02 test suites.
    """
    if cfg.round_trip_bps is not None:
        return qty * price * (cfg.round_trip_bps / 2.0) / 10_000.0

    notional = qty * price
    exchange = notional * cfg.exchange_txn_pct
    sebi = notional * cfg.sebi_pct
    stt = notional * cfg.stt_pct
    stamp = notional * cfg.stamp_duty_pct if side == "buy" else 0.0
    gst = (exchange + sebi) * cfg.gst_pct
    dp = cfg.dp_charge if side in ("sell", "trim") else 0.0
    return stt + exchange + sebi + stamp + gst + dp


def effective_price(
    side: SideLiteral,
    price: float,
    qty: float,
    adv_20: float,
    cfg: CostConfig,
) -> float:
    """Return the slippage-adjusted effective fill price (spec 03 §1.3).

    Participation = (qty × price) / adv_20, clamped at participation_cap.
    When adv_20 ≤ 0 (unknown liquidity), uses base_slippage_pct floor only.

    Buys fill higher (cost basis rises); sells/trims fill lower (proceeds fall).
    Returns raw price unchanged in the legacy round_trip_bps path.
    """
    if cfg.round_trip_bps is not None:
        return price  # legacy path: no slippage model

    if adv_20 > 0.0:
        participation = min((qty * price) / adv_20, cfg.participation_cap)
        slip = cfg.base_slippage_pct + cfg.impact_coeff * participation
    else:
        slip = cfg.base_slippage_pct  # unknown liquidity: floor only

    if side == "buy":
        return price * (1.0 + slip)
    return price * (1.0 - slip)  # sell / trim
