"""Pure mathematical Spot position sizing. Never submits an order."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math


@dataclass(frozen=True, slots=True)
class PositionRiskEstimate:
    accepted_for_research: bool
    account_equity: float
    entry_reference_price: float
    stop_reference_price: float
    risk_budget_quote: float
    estimated_quantity: float
    estimated_notional_quote: float
    estimated_loss_at_stop_quote: float
    exposure_pct_equity: float
    reasons: tuple[str, ...]
    live_order_placed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def estimate_spot_position(*, account_equity: float, entry_price: float, stop_price: float,
                           risk_fraction: float = 0.01, max_exposure_fraction: float = 0.25,
                           fee_rate: float = 0.001, slippage_fraction: float = 0.0005) -> PositionRiskEstimate:
    values = (account_equity, entry_price, stop_price, risk_fraction, max_exposure_fraction, fee_rate, slippage_fraction)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("All risk sizing inputs must be finite")
    if account_equity <= 0 or entry_price <= 0 or stop_price <= 0:
        raise ValueError("Equity and prices must be positive")
    if stop_price >= entry_price:
        raise ValueError("Long Spot stop_price must be below entry_price")
    if not 0 < risk_fraction <= 0.05 or not 0 < max_exposure_fraction <= 1:
        raise ValueError("Risk and exposure fractions are outside permitted bounds")
    if not 0 <= fee_rate < 0.05 or not 0 <= slippage_fraction < 0.05:
        raise ValueError("Fee or slippage assumption is outside permitted bounds")
    budget = account_equity * risk_fraction
    effective_loss_per_unit = entry_price - stop_price + (entry_price + stop_price) * (fee_rate + slippage_fraction)
    if effective_loss_per_unit <= 0:
        raise ValueError("Computed stop loss per unit must be positive")
    qty_by_risk = budget / effective_loss_per_unit
    qty_by_exposure = account_equity * max_exposure_fraction / entry_price
    qty_by_cash = account_equity / (entry_price * (1 + fee_rate + slippage_fraction))
    quantity = max(0.0, min(qty_by_risk, qty_by_exposure, qty_by_cash))
    notional = quantity * entry_price
    estimated_loss = quantity * effective_loss_per_unit
    reasons = ["Long-only Spot sizing estimate", "Fees and slippage are assumptions, not guaranteed fills", "This output is not an order and does not place a trade"]
    if quantity < qty_by_risk:
        reasons.append("Quantity was capped by cash or maximum exposure")
    return PositionRiskEstimate(True, account_equity, entry_price, stop_price, budget, quantity, notional,
                                estimated_loss, notional / account_equity * 100, tuple(reasons), False)
