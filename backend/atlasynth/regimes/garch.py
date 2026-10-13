"""A transparent GARCH(1,1) conditional-volatility recursion.

This module does not estimate parameters or claim predictive validity by itself.
Parameters must be fitted using training data only and evaluated out-of-sample.
"""
from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GARCH11Parameters:
    omega: float
    alpha: float
    beta: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.omega) or self.omega <= 0:
            raise ValueError("omega must be finite and positive")
        if not math.isfinite(self.alpha) or not math.isfinite(self.beta):
            raise ValueError("alpha and beta must be finite")
        if self.alpha < 0 or self.beta < 0 or self.alpha + self.beta >= 1:
            raise ValueError("Require alpha >= 0, beta >= 0, alpha + beta < 1")


def garch11_variance(returns: list[float], params: GARCH11Parameters) -> list[float]:
    if len(returns) < 2:
        raise ValueError("At least two returns are required")
    if any(not math.isfinite(x) for x in returns):
        raise ValueError("Returns must be finite")
    long_run = params.omega / (1 - params.alpha - params.beta)
    variance = max(long_run, 1e-16)
    out: list[float] = []
    for i, r in enumerate(returns):
        if i:
            prev = returns[i - 1]
            variance = params.omega + params.alpha * prev * prev + params.beta * variance
        out.append(variance)
    return out
