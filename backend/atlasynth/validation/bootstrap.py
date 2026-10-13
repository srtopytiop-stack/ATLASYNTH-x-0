"""Circular moving-block bootstrap for a mean-return confidence interval."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import numpy as np


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    computed: bool
    observations: int
    replications: int
    block_length: int
    mean_return: float | None
    lower_confidence_bound: float | None
    upper_confidence_bound: float | None
    probability_mean_positive: float | None
    seed: int
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def moving_block_bootstrap_mean(returns: list[float] | np.ndarray, *, replications: int = 2000,
                                block_length: int | None = None, confidence: float = 0.95,
                                seed: int = 20261013) -> BootstrapResult:
    arr = np.asarray(returns, dtype=float)
    if arr.ndim != 1 or not np.all(np.isfinite(arr)):
        raise ValueError("returns must be a finite one-dimensional sequence")
    if replications < 100:
        raise ValueError("replications must be >= 100")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    n = len(arr)
    block = block_length or max(1, int(round(n ** (1 / 3))))
    if block < 1 or block > max(1, n // 2):
        if n >= 2:
            raise ValueError("block_length must be between 1 and half the observations")
    if n < max(20, block * 3):
        return BootstrapResult(False, n, replications, block, None, None, None, None, seed,
                               "Insufficient observations for the configured block bootstrap")
    rng = np.random.default_rng(seed)
    samples = np.empty(replications, dtype=float)
    starts_needed = math.ceil(n / block)
    offsets = np.arange(block)
    for b in range(replications):
        starts = rng.integers(0, n, size=starts_needed)
        indices = ((starts[:, None] + offsets[None, :]) % n).ravel()[:n]
        samples[b] = float(np.mean(arr[indices]))
    alpha = (1 - confidence) / 2
    lower, upper = np.quantile(samples, [alpha, 1 - alpha])
    return BootstrapResult(True, n, replications, block, float(np.mean(arr)), float(lower), float(upper),
                           float(np.mean(samples > 0)), seed,
                           "Seeded circular moving-block bootstrap; results depend on block length and stationarity assumptions")
