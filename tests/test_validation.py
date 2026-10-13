import numpy as np
import pytest
from atlasynth.validation.statistics import probabilistic_sharpe_ratio, deflated_sharpe_ratio
from atlasynth.validation.bootstrap import moving_block_bootstrap_mean
from atlasynth.validation.cscv import cscv_probability_of_backtest_overfitting
from atlasynth.validation.walk_forward import expanding_walk_forward_splits


def test_sharpe_inference_returns_explicit_undefined_for_constant_returns():
    result = probabilistic_sharpe_ratio([0.01] * 20)
    assert result.computed is False
    assert result.probability_sharpe_exceeds_benchmark is None


def test_dsr_probability_stays_bounded():
    rng = np.random.default_rng(13)
    r = rng.normal(0.001, 0.02, 400)
    result = deflated_sharpe_ratio(r, trials_considered=20)
    assert result.computed
    assert 0 <= result.deflated_sharpe_probability <= 1
    assert result.estimated_max_sharpe_benchmark is not None


def test_bootstrap_is_reproducible_and_reports_uncertainty():
    r = np.sin(np.arange(300) / 7) * 0.01 + 0.0005
    a = moving_block_bootstrap_mean(r, replications=200, seed=42)
    b = moving_block_bootstrap_mean(r, replications=200, seed=42)
    assert a.computed and a.lower_confidence_bound == b.lower_confidence_bound


def test_cscv_reports_none_when_underpowered_and_computes_with_varied_trials():
    small = cscv_probability_of_backtest_overfitting([[0.01] * 10, [0.02] * 10])
    assert not small.computed and small.pbo_probability is None
    rng = np.random.default_rng(14)
    matrix = rng.normal(0.0005, 0.02, size=(8, 200))
    result = cscv_probability_of_backtest_overfitting(matrix, n_splits=10)
    assert result.computed
    assert 0 <= result.pbo_probability <= 1
    assert result.combinations_evaluated > 0


def test_walk_forward_splits_are_chronological_and_embargoed():
    folds = expanding_walk_forward_splits(250, min_train_size=100, test_size=25, embargo=5)
    assert folds
    for f in folds:
        assert f.train_end_exclusive <= f.test_start - 5
        assert f.train_end_exclusive > f.train_start
        assert f.test_end_exclusive > f.test_start


def test_prefix_invariance_causality_diagnostic_passes_for_rolling_features():
    from atlasynth.features.indicators import compute_features
    from atlasynth.validation.causality import prefix_invariance_diagnostic
    from conftest import make_candles
    candles = make_candles(100)
    result = prefix_invariance_diagnostic(candles, compute_features, ["ema_fast", "atr", "rsi"])
    assert result.computed and result.checks > 0
    assert result.failed == 0
