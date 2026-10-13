import numpy as np
from atlasynth.regimes.garch import GARCH11Parameters, garch11_variance
from atlasynth.regimes.gaussian_hmm import GaussianVolatilityHMM


def test_garch_variance_is_positive_and_finite():
    result = garch11_variance([0.01, -0.02, 0.015, 0.005], GARCH11Parameters(omega=1e-6, alpha=0.08, beta=0.88))
    assert len(result) == 4
    assert all(np.isfinite(v) and v > 0 for v in result)


def test_hmm_filter_probabilities_are_normalized():
    rng = np.random.default_rng(7)
    train = np.concatenate([rng.normal(0, 0.003, 100), rng.normal(0, 0.02, 100)])
    model = GaussianVolatilityHMM(n_iter=20).fit(train)
    test = np.concatenate([rng.normal(0, 0.004, 20), rng.normal(0, 0.025, 20)])
    state = model.filter(test, initial_prior=model.next_prior())
    assert len(state) == len(test)
    for item in state:
        assert 0 <= item.low_volatility_probability <= 1
        assert 0 <= item.high_volatility_probability <= 1
        assert abs(item.low_volatility_probability + item.high_volatility_probability - 1) < 1e-6
