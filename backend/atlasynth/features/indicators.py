"""Deterministic OHLCV features; no exchange access and no future observations."""
from __future__ import annotations

import numpy as np
import pandas as pd

from atlasynth.core.models import Candle


class FeatureError(ValueError):
    pass


def candles_frame(candles: list[Candle]) -> pd.DataFrame:
    if not candles:
        raise FeatureError("At least one closed candle is required")
    opens = [c.open_time_ms for c in candles]
    if opens != sorted(opens) or len(opens) != len(set(opens)):
        raise FeatureError("Candles must have unique chronological timestamps")
    if any(not c.is_closed for c in candles):
        raise FeatureError("Feature engine refuses incomplete candles")
    return pd.DataFrame({
        "timestamp_ms": [c.open_time_ms for c in candles],
        "open": [c.open for c in candles], "high": [c.high for c in candles],
        "low": [c.low for c in candles], "close": [c.close for c in candles],
        "volume": [c.volume for c in candles],
        "quote_volume": [c.quote_volume if c.quote_volume is not None else np.nan for c in candles],
    })


def compute_features(candles: list[Candle], *, fast_ema: int = 12, slow_ema: int = 26,
                     rsi_window: int = 14, atr_window: int = 14,
                     volatility_window: int = 20, volume_window: int = 20,
                     zscore_window: int = 20, bollinger_window: int = 20) -> pd.DataFrame:
    """Create features aligned to candle close; rolling warm-up values stay NaN.

    Every row t uses observations at indices <= t. Callers must still execute a
    decision derived from candle t no earlier than candle t+1 open.
    """
    for name, value in {"fast_ema": fast_ema, "slow_ema": slow_ema, "rsi_window": rsi_window,
                        "atr_window": atr_window, "volatility_window": volatility_window,
                        "volume_window": volume_window, "zscore_window": zscore_window,
                        "bollinger_window": bollinger_window}.items():
        if value < 2:
            raise FeatureError(f"{name} must be >= 2")
    if fast_ema >= slow_ema:
        raise FeatureError("fast_ema must be less than slow_ema")
    f = candles_frame(candles)
    close, high, low, volume = f.close, f.high, f.low, f.volume
    prev_close = close.shift(1)
    f["return"] = close.pct_change(fill_method=None)
    f["log_return"] = np.log(close / prev_close)
    f["ema_fast"] = close.ewm(span=fast_ema, adjust=False, min_periods=fast_ema).mean()
    f["ema_slow"] = close.ewm(span=slow_ema, adjust=False, min_periods=slow_ema).mean()
    f["momentum_5"] = close.pct_change(5, fill_method=None)
    f["momentum_20"] = close.pct_change(20, fill_method=None)
    f["candle_range_pct"] = (high - low) / close
    f["body_pct"] = (close - f.open) / f.open
    f["upper_wick_pct"] = (high - np.maximum(f.open, close)) / close
    f["lower_wick_pct"] = (np.minimum(f.open, close) - low) / close
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    f["true_range"] = tr
    f["atr"] = tr.ewm(alpha=1 / atr_window, adjust=False, min_periods=atr_window).mean()
    f["atr_pct"] = f.atr / close
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / rsi_window, adjust=False, min_periods=rsi_window).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / rsi_window, adjust=False, min_periods=rsi_window).mean()
    rs = gain / loss.replace(0, np.nan)
    f["rsi"] = (100 - 100 / (1 + rs)).where(loss.ne(0), 100.0)
    f["realized_volatility"] = f.log_return.rolling(volatility_window, min_periods=volatility_window).std(ddof=1)
    vol_mean = volume.rolling(volume_window, min_periods=volume_window).mean()
    vol_std = volume.rolling(volume_window, min_periods=volume_window).std(ddof=1)
    f["volume_zscore"] = ((volume - vol_mean) / vol_std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    z_mean = close.rolling(zscore_window, min_periods=zscore_window).mean()
    z_std = close.rolling(zscore_window, min_periods=zscore_window).std(ddof=1)
    f["price_zscore"] = ((close - z_mean) / z_std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    bb_mean = close.rolling(bollinger_window, min_periods=bollinger_window).mean()
    bb_std = close.rolling(bollinger_window, min_periods=bollinger_window).std(ddof=1)
    f["bb_mid"] = bb_mean
    f["bb_upper"] = bb_mean + 2 * bb_std
    f["bb_lower"] = bb_mean - 2 * bb_std
    f["bb_width_pct"] = (f.bb_upper - f.bb_lower) / bb_mean
    # Directional movement / ADX baseline, with rolling denominators guarded.
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    smooth_tr = tr.ewm(alpha=1 / atr_window, adjust=False, min_periods=atr_window).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / atr_window, adjust=False, min_periods=atr_window).mean() / smooth_tr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / atr_window, adjust=False, min_periods=atr_window).mean() / smooth_tr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    f["plus_di"] = plus_di
    f["minus_di"] = minus_di
    f["adx"] = dx.ewm(alpha=1 / atr_window, adjust=False, min_periods=atr_window).mean()
    return f
