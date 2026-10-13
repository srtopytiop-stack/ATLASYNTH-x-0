"""Causal long-only Spot backtest with costs and conservative stop/target logic.

Signals from candle t may only be acted on at candle t+1 open. If both stop-loss
and target are touched within one OHLC bar, the stop is assumed to occur first.
This reduces optimistic intrabar assumptions; OHLC data cannot reveal the exact path.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math

import pandas as pd

from atlasynth.core.models import Candle
from atlasynth.backtesting.metrics import PerformanceMetrics, calculate_metrics
from atlasynth.data.binance_spot import interval_milliseconds


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    starting_cash: float = 1000.0
    fee_rate: float = 0.001
    slippage_bps: float = 5.0
    risk_per_trade: float = 0.01
    max_exposure_fraction: float = 0.90
    atr_stop_multiple: float = 2.0
    reward_risk_ratio: float = 2.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.starting_cash) or self.starting_cash <= 0:
            raise ValueError("starting_cash must be finite and positive")
        if not 0 <= self.fee_rate < 0.05:
            raise ValueError("fee_rate must be in [0, 0.05)")
        if not 0 <= self.slippage_bps <= 500:
            raise ValueError("slippage_bps must be in [0, 500]")
        if not 0 < self.risk_per_trade <= 0.05:
            raise ValueError("risk_per_trade must be in (0, 0.05]")
        if not 0 < self.max_exposure_fraction <= 1:
            raise ValueError("max_exposure_fraction must be in (0, 1]")
        if self.atr_stop_multiple <= 0 or self.reward_risk_ratio <= 0:
            raise ValueError("ATR stop multiple and reward/risk must be positive")


@dataclass(frozen=True, slots=True)
class TradeRecord:
    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    exit_price: float
    quantity: float
    fees_paid: float
    pnl_after_fees: float
    return_pct: float
    exit_reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    symbol: str
    interval: str
    strategy_id: str
    equity_curve: tuple[float, ...]
    timestamps_ms: tuple[int, ...]
    trades: tuple[TradeRecord, ...]
    metrics: PerformanceMetrics
    warnings: tuple[str, ...]
    is_causally_scheduled: bool = True
    live_trading_enabled: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol, "interval": self.interval, "strategy_id": self.strategy_id,
            "equity_curve": list(self.equity_curve), "timestamps_ms": list(self.timestamps_ms),
            "trades": [t.to_dict() for t in self.trades], "metrics": self.metrics.to_dict(),
            "warnings": list(self.warnings), "is_causally_scheduled": self.is_causally_scheduled,
            "live_trading_enabled": False,
        }


def bars_per_year(interval: str) -> float:
    ms = interval_milliseconds(interval)
    # Crypto market trades 24/7. Weekly bars are conventionally annualized as 52.
    return 52.0 if interval == "1w" else (365.0 * 86_400_000 / ms)


def run_backtest(*, symbol: str, interval: str, candles: list[Candle],
                 signals: pd.DataFrame, strategy_id: str,
                 config: BacktestConfig | None = None) -> BacktestResult:
    cfg = config or BacktestConfig()
    if len(candles) < 3:
        raise ValueError("At least three closed candles are required")
    if len(signals) != len(candles):
        raise ValueError("Signals and candles must have equal lengths")
    if not {"entry", "exit", "atr"}.issubset(signals.columns):
        raise ValueError("Signals must contain entry, exit, and atr columns")
    if any(not c.is_closed for c in candles):
        raise ValueError("Backtest requires closed candles only")
    times = [c.open_time_ms for c in candles]
    if times != sorted(times) or len(set(times)) != len(times):
        raise ValueError("Candles must be unique and chronologically ordered")
    if any(not math.isfinite(c.close) for c in candles):
        raise ValueError("Non-finite market data")

    cash = cfg.starting_cash
    quantity = 0.0
    entry_price = 0.0
    entry_time = 0
    entry_fee = 0.0
    initial_cost = 0.0
    stop_price = 0.0
    target_price = 0.0
    exposure_bars = 0
    trade_pnls: list[float] = []
    trade_returns: list[float] = []
    trades: list[TradeRecord] = []
    curve: list[float] = [cfg.starting_cash]
    warnings: list[str] = [
        "Signals execute no earlier than the next candle open.",
        "OHLC intrabar ordering is unknowable; if stop and target both touch, stop is assumed first.",
        "Fees and slippage are modeled assumptions; calibrate them to your actual venue and order style.",
    ]
    slip = cfg.slippage_bps / 10_000.0

    def close_position(fill_raw: float, time_ms: int, reason: str) -> None:
        nonlocal cash, quantity, entry_price, entry_time, entry_fee, initial_cost, stop_price, target_price
        fill = fill_raw * (1 - slip)
        gross = quantity * fill
        exit_fee = gross * cfg.fee_rate
        cash += gross - exit_fee
        pnl = gross - exit_fee - initial_cost
        denom = initial_cost if initial_cost > 0 else 1.0
        ret_pct = pnl / denom * 100
        fees = entry_fee + exit_fee
        trades.append(TradeRecord(entry_time, time_ms, entry_price, fill, quantity, fees, pnl, ret_pct, reason))
        trade_pnls.append(pnl)
        trade_returns.append(pnl / denom)
        quantity = 0.0
        entry_price = 0.0
        entry_time = 0
        entry_fee = 0.0
        initial_cost = 0.0
        stop_price = target_price = 0.0

    for i, candle in enumerate(candles):
        if i > 0:
            prev_signal = signals.iloc[i - 1]
            # A signal formed from candle i-1 can only act at this candle's open.
            exited_at_open = False
            if quantity > 0 and bool(prev_signal["exit"]):
                close_position(candle.open, candle.open_time_ms, "strategy_exit_next_open")
                exited_at_open = True
            elif quantity <= 0 and bool(prev_signal["entry"]):
                try:
                    atr = float(prev_signal["atr"])
                except (TypeError, ValueError):
                    atr = math.nan
                if not math.isfinite(atr) or atr <= 0:
                    warnings.append(f"Skipped entry at {candle.open_time_ms}: ATR was unavailable at decision time")
                else:
                    fill = candle.open * (1 + slip)
                    equity_before = cash
                    risk_budget = equity_before * cfg.risk_per_trade
                    stop_distance = atr * cfg.atr_stop_multiple
                    qty_by_risk = risk_budget / stop_distance
                    notional_cap = equity_before * cfg.max_exposure_fraction
                    qty_by_exposure = notional_cap / fill
                    qty_by_cash = cash / (fill * (1 + cfg.fee_rate))
                    quantity = max(0.0, min(qty_by_risk, qty_by_exposure, qty_by_cash))
                    if quantity > 0 and math.isfinite(quantity):
                        entry_price = fill
                        entry_time = candle.open_time_ms
                        entry_fee = quantity * fill * cfg.fee_rate
                        initial_cost = quantity * fill + entry_fee
                        cash -= initial_cost
                        stop_price = max(fill - stop_distance, fill * 1e-6)
                        target_price = fill + stop_distance * cfg.reward_risk_ratio
                    else:
                        quantity = 0.0
            # Conservative OHLC handling. Do not evaluate stop/target after a signal exit.
            if quantity > 0 and not exited_at_open:
                hit_stop = candle.low <= stop_price
                hit_target = candle.high >= target_price
                if candle.open <= stop_price:
                    close_position(candle.open, candle.open_time_ms, "stop_gap")
                elif candle.open >= target_price:
                    close_position(candle.open, candle.open_time_ms, "target_gap")
                elif hit_stop:
                    close_position(stop_price, candle.close_time_ms, "stop_loss")
                elif hit_target:
                    close_position(target_price, candle.close_time_ms, "take_profit")
        if quantity > 0:
            exposure_bars += 1
        equity = cash + quantity * candle.close
        if not math.isfinite(equity) or equity <= 0:
            raise RuntimeError("Equity became non-finite or non-positive")
        if i == 0:
            curve[0] = equity
        else:
            curve.append(equity)

    # Close any remaining position at the last observed close; include costs.
    if quantity > 0:
        last = candles[-1]
        close_position(last.close, last.close_time_ms, "end_of_test_liquidation")
        curve[-1] = cash

    metrics = calculate_metrics(
        equity_curve=curve, trade_pnls=trade_pnls, trade_returns=trade_returns,
        exposure_bars=exposure_bars, bars_per_year=bars_per_year(interval),
    )
    return BacktestResult(
        symbol=symbol.upper(), interval=interval, strategy_id=strategy_id,
        equity_curve=tuple(curve), timestamps_ms=tuple(c.open_time_ms for c in candles),
        trades=tuple(trades), metrics=metrics, warnings=tuple(dict.fromkeys(warnings)),
        is_causally_scheduled=True, live_trading_enabled=False,
    )
