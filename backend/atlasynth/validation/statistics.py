"""Statistical metrics with explicit failure states instead of fake defaults.

All Sharpe calculations here are at the native frequency of the supplied returns.
Annualization is a presentation concern and must not be mixed into PSR/DSR inputs.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
from statistics import NormalDist
import numpy as np


@dataclass(frozen=True, slots=True)
class SharpeInference:
    computed: bool
    observations: int
    periodic_sharpe: float | None
    benchmark_sharpe: float
    probability_sharpe_exceeds_benchmark: float | None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DSRInference:
    computed: bool
    observations: int
    trials_considered: int
    periodic_sharpe: float | None
    estimated_max_sharpe_benchmark: float | None
    deflated_sharpe_probability: float | None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _valid_returns(returns: list[float] | np.ndarray) -> np.ndarray:
    arr = np.asarray(returns, dtype=float)
    if arr.ndim != 1:
        raise ValueError("returns must be a one-dimensional sequence")
    if not np.all(np.isfinite(arr)):
        raise ValueError("returns contain NaN or infinity")
    return arr


def _distribution(arr: np.ndarray) -> tuple[float, float, float, float] | None:
    if arr.size < 3:
        return None
    mean = float(np.mean(arr))
    # Treat numerically constant series as zero variance rather than returning an absurd Sharpe.
    if float(np.ptp(arr)) <= max(1e-15, float(np.max(np.abs(arr))) * 1e-12):
        return None
    std = float(np.std(arr, ddof=1))
    if not math.isfinite(std) or std <= max(1e-15, abs(mean) * 1e-12):
        return None
    centered = arr - mean
    m2 = float(np.mean(centered ** 2))
    if m2 <= 0:
        return None
    skew = float(np.mean(centered ** 3) / (m2 ** 1.5))
    kurtosis_non_excess = float(np.mean(centered ** 4) / (m2 ** 2))
    return mean, std, skew, kurtosis_non_excess


def probabilistic_sharpe_ratio(returns: list[float] | np.ndarray,
                               benchmark_sharpe: float = 0.0) -> SharpeInference:
    arr = _valid_returns(returns)
    if not math.isfinite(benchmark_sharpe):
        raise ValueError("benchmark_sharpe must be finite and at the same periodicity")
    dist = _distribution(arr)
    if dist is None:
        return SharpeInference(False, int(arr.size), None, benchmark_sharpe, None,
                               "At least three returns with non-zero variance are required")
    mean, std, skew, kurtosis = dist
    sr = mean / std
    denominator_sq = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    if denominator_sq <= 0 or not math.isfinite(denominator_sq):
        return SharpeInference(False, int(arr.size), sr, benchmark_sharpe, None,
                               "PSR denominator is not positive; inference is undefined")
    z = (sr - benchmark_sharpe) * math.sqrt(arr.size - 1) / math.sqrt(denominator_sq)
    probability = NormalDist().cdf(z)
    return SharpeInference(True, int(arr.size), sr, benchmark_sharpe,
                           min(1.0, max(0.0, probability)))


def deflated_sharpe_ratio(returns: list[float] | np.ndarray, trials_considered: int) -> DSRInference:
    arr = _valid_returns(returns)
    if trials_considered < 1:
        raise ValueError("trials_considered must be >= 1")
    dist = _distribution(arr)
    if dist is None:
        return DSRInference(False, int(arr.size), trials_considered, None, None, None,
                            "At least three returns with non-zero variance are required")
    mean, std, skew, kurtosis = dist
    sr = mean / std
    # Approximate sampling standard error of the periodic Sharpe estimator.
    variance_factor = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    if variance_factor <= 0:
        return DSRInference(False, int(arr.size), trials_considered, sr, None, None,
                            "Sharpe estimator variance is not positive")
    sigma_sr = math.sqrt(variance_factor / max(1, arr.size - 1))
    if trials_considered == 1:
        expected_max = 0.0
    else:
        nd = NormalDist()
        n = float(trials_considered)
        # Blom-like extreme-value approximation used for expected maximum of N normal trials.
        p1 = min(1 - 1e-12, max(1e-12, 1 - 1 / n))
        p2 = min(1 - 1e-12, max(1e-12, 1 - 1 / (n * math.e)))
        gamma = 0.5772156649015329
        expected_max = sigma_sr * ((1 - gamma) * nd.inv_cdf(p1) + gamma * nd.inv_cdf(p2))
    inferred = probabilistic_sharpe_ratio(arr, expected_max)
    if not inferred.computed:
        return DSRInference(False, int(arr.size), trials_considered, sr, expected_max, None, inferred.reason)
    return DSRInference(True, int(arr.size), trials_considered, sr, expected_max,
                        inferred.probability_sharpe_exceeds_benchmark,
                        "Expected-max Sharpe is an approximation; record all trials and use an independent OOS test")
