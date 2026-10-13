"""Prefix-invariance diagnostic to catch common look-ahead feature leaks."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections.abc import Callable
import math
import pandas as pd
from atlasynth.core.models import Candle


@dataclass(frozen=True, slots=True)
class CausalityCheck:
    index: int
    feature: str
    full_series_value: float | None
    prefix_only_value: float | None
    passed: bool


@dataclass(frozen=True, slots=True)
class CausalityDiagnostic:
    computed: bool
    checks: int
    passed: int
    failed: int
    details: tuple[CausalityCheck, ...]
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"computed": self.computed, "checks": self.checks, "passed": self.passed,
                "failed": self.failed, "details": [asdict(x) for x in self.details], "reason": self.reason}


def prefix_invariance_diagnostic(candles: list[Candle], compute: Callable[[list[Candle]], pd.DataFrame],
                                 features: list[str], *, sample_indices: list[int] | None = None,
                                 relative_tolerance: float = 1e-9) -> CausalityDiagnostic:
    """Compare features computed on the full set with features on historical prefixes.

    This catches many global-normalization and centered-window errors. It is a
    diagnostic only: passing does not prove that a strategy has no look-ahead bias.
    """
    if relative_tolerance < 0 or not math.isfinite(relative_tolerance):
        raise ValueError("relative_tolerance must be finite and non-negative")
    if len(candles) < 3:
        return CausalityDiagnostic(False, 0, 0, 0, (), "At least three candles are required")
    full = compute(candles)
    indices = sample_indices or sorted(set([max(1, len(candles) // 3), max(2, (2 * len(candles)) // 3), len(candles) - 1]))
    details: list[CausalityCheck] = []
    for idx in indices:
        if idx < 0 or idx >= len(candles):
            raise ValueError(f"sample index {idx} is outside candle range")
        prefix = compute(candles[:idx + 1])
        for feature in features:
            if feature not in full.columns or feature not in prefix.columns:
                raise ValueError(f"Unknown feature column: {feature}")
            a, b = full.iloc[idx][feature], prefix.iloc[idx][feature]
            a_value = None if pd.isna(a) else float(a)
            b_value = None if pd.isna(b) else float(b)
            if a_value is None or b_value is None:
                passed = a_value is None and b_value is None
            else:
                passed = math.isclose(a_value, b_value, rel_tol=relative_tolerance, abs_tol=relative_tolerance)
            details.append(CausalityCheck(idx, feature, a_value, b_value, passed))
    passed_count = sum(1 for c in details if c.passed)
    return CausalityDiagnostic(True, len(details), passed_count, len(details) - passed_count, tuple(details),
                               "Passing prefix invariance is not a proof against all look-ahead paths")
