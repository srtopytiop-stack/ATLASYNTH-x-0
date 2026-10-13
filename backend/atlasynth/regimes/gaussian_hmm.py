"""Small univariate Gaussian HMM for research-only volatility regime discovery.

Fit parameters on a training window only. Use filter probabilities (forward pass),
not smoothed probabilities, for time-t decisions. This is not a trading signal by itself.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True, slots=True)
class HMMFilteredState:
    index: int
    state: int
    low_volatility_probability: float
    high_volatility_probability: float


class GaussianVolatilityHMM:
    def __init__(self, *, n_iter: int = 50, tolerance: float = 1e-6, variance_floor: float = 1e-10):
        if n_iter < 1 or tolerance <= 0 or variance_floor <= 0:
            raise ValueError("Invalid HMM fit parameters")
        self.n_iter = n_iter
        self.tolerance = tolerance
        self.variance_floor = variance_floor
        self.means_: np.ndarray | None = None
        self.variances_: np.ndarray | None = None
        self.transition_: np.ndarray | None = None
        self.initial_: np.ndarray | None = None
        self.terminal_filter_: np.ndarray | None = None
        self.log_likelihood_: float | None = None
        self.n_iter_: int = 0

    def _emission(self, x: np.ndarray, means: np.ndarray, variances: np.ndarray) -> np.ndarray:
        z = x[:, None] - means[None, :]
        log_e = -0.5 * (np.log(2 * math.pi * variances)[None, :] + (z * z) / variances[None, :])
        return np.exp(np.clip(log_e, -700, 100))

    def _forward(self, emission: np.ndarray, transition: np.ndarray, initial: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        n, states = emission.shape
        alpha = np.zeros((n, states), dtype=float)
        scales = np.zeros(n, dtype=float)
        alpha[0] = initial * emission[0]
        scales[0] = max(float(alpha[0].sum()), 1e-300)
        alpha[0] /= scales[0]
        for t in range(1, n):
            alpha[t] = (alpha[t - 1] @ transition) * emission[t]
            scales[t] = max(float(alpha[t].sum()), 1e-300)
            alpha[t] /= scales[t]
        return alpha, scales, float(np.sum(np.log(scales)))

    def _smooth(self, emission: np.ndarray, transition: np.ndarray, alpha: np.ndarray,
                scales: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n, states = emission.shape
        beta = np.ones((n, states), dtype=float)
        for t in range(n - 2, -1, -1):
            beta[t] = transition @ (emission[t + 1] * beta[t + 1])
            beta[t] /= max(scales[t + 1], 1e-300)
        gamma = alpha * beta
        gamma /= np.maximum(gamma.sum(axis=1, keepdims=True), 1e-300)
        xi_sum = np.zeros((states, states), dtype=float)
        for t in range(n - 1):
            xi = alpha[t][:, None] * transition * (emission[t + 1] * beta[t + 1])[None, :]
            denom = max(float(xi.sum()), 1e-300)
            xi_sum += xi / denom
        return gamma, xi_sum

    def fit(self, returns: list[float] | np.ndarray) -> "GaussianVolatilityHMM":
        x = np.asarray(returns, dtype=float)
        if x.ndim != 1 or x.size < 50 or not np.all(np.isfinite(x)):
            raise ValueError("HMM needs at least 50 finite one-dimensional training returns")
        global_var = max(float(np.var(x)), self.variance_floor)
        means = np.quantile(x, [0.3, 0.7]).astype(float)
        variances = np.array([global_var, global_var], dtype=float)
        transition = np.array([[0.95, 0.05], [0.05, 0.95]], dtype=float)
        initial = np.array([0.5, 0.5], dtype=float)
        previous_ll: float | None = None
        for iteration in range(1, self.n_iter + 1):
            emission = self._emission(x, means, variances)
            alpha, scales, likelihood = self._forward(emission, transition, initial)
            gamma, xi_sum = self._smooth(emission, transition, alpha, scales)
            initial = np.maximum(gamma[0], 1e-8)
            initial /= initial.sum()
            transition = xi_sum + 1e-6
            transition /= transition.sum(axis=1, keepdims=True)
            weights = np.maximum(gamma.sum(axis=0), 1e-8)
            means = (gamma.T @ x) / weights
            variances = np.array([
                max(float(np.sum(gamma[:, k] * (x - means[k]) ** 2) / weights[k]), self.variance_floor)
                for k in range(2)
            ])
            self.n_iter_ = iteration
            if previous_ll is not None and abs(likelihood - previous_ll) <= self.tolerance * (1 + abs(previous_ll)):
                break
            previous_ll = likelihood
        # Label state 0 as lower variance and state 1 as higher variance for stable interpretation.
        order = np.argsort(variances, kind="stable")
        means, variances = means[order], variances[order]
        transition = transition[np.ix_(order, order)]
        initial = initial[order]
        final_emission = self._emission(x, means, variances)
        alpha, _, likelihood = self._forward(final_emission, transition, initial)
        self.means_, self.variances_, self.transition_, self.initial_ = means, variances, transition, initial
        self.terminal_filter_ = alpha[-1].copy()
        self.log_likelihood_ = likelihood
        return self

    def next_prior(self) -> np.ndarray:
        self._ensure_fitted()
        assert self.terminal_filter_ is not None and self.transition_ is not None
        prior = self.terminal_filter_ @ self.transition_
        return prior / prior.sum()

    def filter(self, returns: list[float] | np.ndarray,
               *, initial_prior: list[float] | np.ndarray | None = None) -> list[HMMFilteredState]:
        self._ensure_fitted()
        x = np.asarray(returns, dtype=float)
        if x.ndim != 1 or not np.all(np.isfinite(x)):
            raise ValueError("Filter inputs must be finite one-dimensional returns")
        if x.size == 0:
            return []
        assert self.means_ is not None and self.variances_ is not None and self.transition_ is not None and self.initial_ is not None
        prior = self.initial_ if initial_prior is None else np.asarray(initial_prior, dtype=float)
        if prior.shape != (2,) or np.any(prior < 0) or not np.all(np.isfinite(prior)) or prior.sum() <= 0:
            raise ValueError("initial_prior must contain two finite non-negative probabilities")
        prior = prior / prior.sum()
        emission = self._emission(x, self.means_, self.variances_)
        alpha, _, _ = self._forward(emission, self.transition_, prior)
        out: list[HMMFilteredState] = []
        for index, p in enumerate(alpha):
            out.append(HMMFilteredState(index, int(np.argmax(p)), float(p[0]), float(p[1])))
        return out

    def _ensure_fitted(self) -> None:
        if any(v is None for v in (self.means_, self.variances_, self.transition_, self.initial_, self.terminal_filter_)):
            raise RuntimeError("HMM must be fitted on a training window before filtering")
