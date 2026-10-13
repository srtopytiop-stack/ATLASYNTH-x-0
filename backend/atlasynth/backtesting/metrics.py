"""Numerically defensive performance metrics for simulated equity curves."""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    starting_equity: float
    final_equity: float
    total_return_pct: float
    annualized_return_pct: float | None
    annualized_sharpe: float | None
    sortino_ratio: float | None
    max_drawdown_pct: float
    win_rate_pct: float | None
    profit_factor: float | None
    total_trades: int
    average_trade_return_pct: float | None
    exposure_pct: float
    observations: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _finite(values: list[float]) -> bool:
    return all(math.isfinite(float(v)) for v in values)


def calculate_metrics(*, equity_curve: list[float], trade_pnls: list[float],
                       trade_returns: list[float], exposure_bars: int,
                       bars_per_year: float) -> PerformanceMetrics:
    if len(equity_curve) < 2:
        raise ValueError("Equity curve must contain at least two values")
    if bars_per_year <= 0 or not math.isfinite(bars_per_year):
        raise ValueError("bars_per_year must be finite and positive")
    if not _finite(equity_curve) or not _finite(trade_pnls) or not _finite(trade_returns):
        raise ValueError("Metrics input contains non-finite values")
    if any(e <= 0 for e in equity_curve):
        raise ValueError("Equity must remain positive")
    start, end = float(equity_curve[0]), float(equity_curve[-1])
    total_return = end / start - 1
    n_bars = len(equity_curve) - 1
    years = n_bars / bars_per_year
    annualized_return = ((end / start) ** (1 / years) - 1) * 100 if years > 0 else None
    returns = [equity_curve[i] / equity_curve[i - 1] - 1 for i in range(1, len(equity_curve))]
    mean_r = sum(returns) / len(returns) if returns else 0.0
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1) if len(returns) > 1 else 0.0
    near_constant = (max(returns) - min(returns)) <= max(1e-15, max(abs(x) for x in returns) * 1e-12) if returns else True
    annualized_sharpe = mean_r / math.sqrt(variance) * math.sqrt(bars_per_year) if variance > 1e-24 and not near_constant else None
    downside = [min(0.0, r) for r in returns]
    downside_var = sum(x * x for x in downside) / len(downside) if downside else 0.0
    sortino = mean_r / math.sqrt(downside_var) * math.sqrt(bars_per_year) if downside_var > 0 else None
    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)
    winners = [p for p in trade_pnls if p > 0]
    losers = [p for p in trade_pnls if p < 0]
    gross_profit, gross_loss = sum(winners), -sum(losers)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (None if gross_profit == 0 else None)
    return PerformanceMetrics(
        starting_equity=start, final_equity=end, total_return_pct=total_return * 100,
        annualized_return_pct=annualized_return, annualized_sharpe=annualized_sharpe,
        sortino_ratio=sortino, max_drawdown_pct=max_drawdown * 100,
        win_rate_pct=(len(winners) / len(trade_pnls) * 100) if trade_pnls else None,
        profit_factor=profit_factor, total_trades=len(trade_pnls),
        average_trade_return_pct=(sum(trade_returns) / len(trade_returns) * 100) if trade_returns else None,
        exposure_pct=max(0, min(100, exposure_bars / max(1, n_bars) * 100)), observations=n_bars,
    )
