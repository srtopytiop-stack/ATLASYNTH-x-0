"""Small, explicit long-only candidate strategies for research comparison."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    strategy_id: str
    description: str
    regime_filter: str


STRATEGIES: tuple[StrategyDefinition, ...] = (
    StrategyDefinition("trend_pullback", "Trend continuation after a controlled pullback", "TREND_UP"),
    StrategyDefinition("mean_reversion", "Oversold deviation in a non-trending range", "RANGE"),
    StrategyDefinition("breakout", "Close above prior rolling range with volume confirmation", "TREND_UP or TRANSITION"),
)


def _frame_copy(features: pd.DataFrame) -> pd.DataFrame:
    required = {"close", "ema_fast", "ema_slow", "rsi", "atr", "volume_zscore", "price_zscore", "adx"}
    missing = required - set(features.columns)
    if missing:
        raise ValueError(f"Missing feature columns: {sorted(missing)}")
    out = features.copy()
    out["entry"] = False
    out["exit"] = False
    out["reason"] = "No entry condition"
    return out


def trend_pullback(features: pd.DataFrame) -> pd.DataFrame:
    f = _frame_copy(features)
    valid = f[list({"close", "ema_fast", "ema_slow", "rsi", "atr", "volume_zscore"})].notna().all(axis=1)
    up = (f.ema_fast > f.ema_slow) & (f.close > f.ema_fast) & (f.rsi.between(45, 68)) & (f.volume_zscore > -1.0)
    f["entry"] = valid & up
    f["exit"] = (f.ema_fast < f.ema_slow) | (f.rsi < 38)
    f.loc[f.entry, "reason"] = "Upward EMA alignment, price above fast EMA, and non-extreme momentum"
    f.loc[f.exit, "reason"] = "Trend alignment weakened or RSI fell below exit threshold"
    return f


def mean_reversion(features: pd.DataFrame) -> pd.DataFrame:
    f = _frame_copy(features)
    valid = f[["price_zscore", "rsi", "adx", "atr"]].notna().all(axis=1)
    f["entry"] = valid & (f.price_zscore <= -2.0) & (f.rsi < 35) & (f.adx < 22)
    f["exit"] = (f.price_zscore >= 0) | (f.rsi >= 60)
    f.loc[f.entry, "reason"] = "Negative price z-score with oversold RSI and weak trend strength"
    f.loc[f.exit, "reason"] = "Deviation reverted toward its mean or RSI reached the exit threshold"
    return f


def breakout(features: pd.DataFrame, *, lookback: int = 20, volume_z_min: float = 0.5) -> pd.DataFrame:
    if lookback < 5:
        raise ValueError("lookback must be >= 5")
    f = _frame_copy(features)
    prior_high = f.high.shift(1).rolling(lookback, min_periods=lookback).max() if "high" in f else None
    if prior_high is None:
        raise ValueError("Breakout strategy requires high prices in the feature frame")
    valid = f[["close", "ema_fast", "ema_slow", "volume_zscore", "atr"]].notna().all(axis=1) & prior_high.notna()
    f["entry"] = valid & (f.close > prior_high) & (f.ema_fast > f.ema_slow) & (f.volume_zscore >= volume_z_min)
    f["exit"] = (f.close < f.ema_fast) | (f.ema_fast < f.ema_slow)
    f.loc[f.entry, "reason"] = "Close broke prior rolling high with upward EMA alignment and volume confirmation"
    f.loc[f.exit, "reason"] = "Price fell below fast EMA or trend alignment weakened"
    return f


def run_strategy(strategy_id: str, features: pd.DataFrame) -> pd.DataFrame:
    if strategy_id == "trend_pullback":
        return trend_pullback(features)
    if strategy_id == "mean_reversion":
        return mean_reversion(features)
    if strategy_id == "breakout":
        return breakout(features)
    raise ValueError(f"Unknown strategy_id: {strategy_id}")
