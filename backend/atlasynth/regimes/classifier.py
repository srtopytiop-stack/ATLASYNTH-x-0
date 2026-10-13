"""Interpretable market-state classification, explicitly not a probability model."""
from __future__ import annotations

import math
import pandas as pd

from atlasynth.core.models import MarketRegime


class RegimeError(ValueError):
    pass


def classify_regime(features: pd.DataFrame, *, min_history: int = 60) -> tuple[MarketRegime, tuple[str, ...]]:
    if len(features) < min_history:
        return MarketRegime.UNKNOWN, (f"Need at least {min_history} observations to classify the regime",)
    row = features.iloc[-1]
    required = ("close", "ema_fast", "ema_slow", "adx", "atr_pct", "realized_volatility")
    if any(k not in features.columns for k in required):
        raise RegimeError("Feature frame is missing regime inputs")
    if any(pd.isna(row[k]) for k in required):
        return MarketRegime.UNKNOWN, ("Regime inputs are not fully initialized",)
    vol_series = features["realized_volatility"].dropna().tail(100)
    atr_series = features["atr_pct"].dropna().tail(100)
    if len(vol_series) < 20 or len(atr_series) < 20:
        return MarketRegime.UNKNOWN, ("Insufficient volatility history",)
    current_vol = float(row["realized_volatility"])
    median_vol = float(vol_series.median())
    high_vol = current_vol > median_vol * 1.8 if median_vol > 0 else False
    low_vol = current_vol < median_vol * 0.55 if median_vol > 0 else False
    trend_gap = (float(row["ema_fast"]) - float(row["ema_slow"])) / float(row["close"])
    adx = float(row["adx"])
    reasons: list[str] = [f"ADX={adx:.2f}; EMA gap={trend_gap:.5f}; realized volatility={current_vol:.5f}"]
    if not all(math.isfinite(v) for v in (current_vol, median_vol, trend_gap, adx)):
        return MarketRegime.UNKNOWN, ("Non-finite regime input",)
    if high_vol:
        return MarketRegime.HIGH_VOLATILITY, tuple(reasons + ["Volatility is materially above its recent median"])
    if low_vol:
        return MarketRegime.LOW_VOLATILITY, tuple(reasons + ["Volatility is materially below its recent median"])
    if adx >= 22 and trend_gap > 0.002:
        return MarketRegime.TREND_UP, tuple(reasons + ["Trend-strength and moving-average separation support an upward-regime label"])
    if adx >= 22 and trend_gap < -0.002:
        return MarketRegime.TREND_DOWN, tuple(reasons + ["Trend-strength and moving-average separation support a downward-regime label"])
    if adx < 18 and abs(trend_gap) < 0.003:
        return MarketRegime.RANGE, tuple(reasons + ["Trend strength and EMA separation are modest"])
    return MarketRegime.TRANSITION, tuple(reasons + ["Inputs do not meet the explicit rules for another regime"])
