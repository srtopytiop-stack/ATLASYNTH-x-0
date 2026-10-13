import numpy as np
import pandas as pd
import pytest
from atlasynth.features.indicators import compute_features, FeatureError
from atlasynth.core.models import Candle
from conftest import make_candles


def test_feature_history_is_deterministic_and_keeps_warmup_nan():
    candles = make_candles(100)
    first = compute_features(candles)
    second = compute_features(candles)
    pd.testing.assert_frame_equal(first, second)
    assert np.isnan(first.loc[0, "ema_slow"])
    assert np.isfinite(first.loc[99, "ema_slow"])


def test_features_at_past_index_do_not_change_when_future_bars_are_appended():
    candles = make_candles(180)
    full = compute_features(candles)
    cutoff = 120
    prefix = compute_features(candles[:cutoff + 1])
    for col in ["ema_fast", "ema_slow", "rsi", "atr", "realized_volatility", "price_zscore"]:
        assert np.isclose(full.loc[cutoff, col], prefix.loc[cutoff, col], equal_nan=True)


def test_feature_engine_rejects_incomplete_candle():
    candles = make_candles(10)
    candles[-1] = Candle(**{**candles[-1].model_dump(), "is_closed": False})
    with pytest.raises(FeatureError):
        compute_features(candles)
