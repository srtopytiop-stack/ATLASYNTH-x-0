"""Combinatorially Symmetric Cross-Validation estimate of Probability of Backtest Overfitting.

Input is an aligned matrix [strategy trial, time observation] of net periodic returns.
This implements the rank-based CSCV idea, not a generic average-of-blocks heuristic.
It remains a research diagnostic, not a guarantee of future performance.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from itertools import combinations
import math
import numpy as np


@dataclass(frozen=True, slots=True)
class PBOResult:
    computed: bool
    strategy_count: int
    observations: int
    splits_requested: int
    combinations_evaluated: int
    pbo_probability: float | None
    median_oos_rank_pct: float | None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sharpe(x: np.ndarray) -> float:
    if x.size < 2:
        return float("nan")
    std = float(np.std(x, ddof=1))
    if std <= 0 or not math.isfinite(std):
        return float("nan")
    return float(np.mean(x) / std)


def _average_rank(values: np.ndarray, index: int) -> float:
    target = values[index]
    less = int(np.sum(values < target))
    equal = int(np.sum(values == target))
    return less + (equal + 1) / 2


def cscv_probability_of_backtest_overfitting(returns_by_strategy: list[list[float]] | np.ndarray,
                                              *, n_splits: int = 10,
                                              max_combinations: int = 20000) -> PBOResult:
    matrix = np.asarray(returns_by_strategy, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("returns_by_strategy must be [strategies, observations]")
    strategies, n_obs = matrix.shape
    if not np.all(np.isfinite(matrix)):
        raise ValueError("returns matrix contains NaN or infinity")
    if n_splits < 4 or n_splits % 2 != 0:
        raise ValueError("n_splits must be even and >= 4")
    if strategies < 2 or n_obs < 2 * n_splits:
        return PBOResult(False, strategies, n_obs, n_splits, 0, None, None,
                         "Need >= 2 strategy trials and at least two observations per split block")
    n_combos = math.comb(n_splits, n_splits // 2)
    if n_combos > max_combinations:
        return PBOResult(False, strategies, n_obs, n_splits, 0, None, None,
                         f"Requested CSCV has {n_combos} combinations, above configured cap {max_combinations}")
    blocks = np.array_split(np.arange(n_obs), n_splits)
    if any(len(b) == 0 for b in blocks):
        return PBOResult(False, strategies, n_obs, n_splits, 0, None, None, "Empty CSCV block")
    below_median = 0
    ranks_pct: list[float] = []
    evaluated = 0
    all_block_ids = set(range(n_splits))
    for in_ids_tuple in combinations(range(n_splits), n_splits // 2):
        in_ids = set(in_ids_tuple)
        out_ids = sorted(all_block_ids - in_ids)
        train_idx = np.concatenate([blocks[i] for i in sorted(in_ids)])
        test_idx = np.concatenate([blocks[i] for i in out_ids])
        train_scores = np.array([_sharpe(row[train_idx]) for row in matrix])
        valid = np.isfinite(train_scores)
        if not valid.any():
            continue
        # Stable argmax ensures deterministic tie behaviour.
        selected = int(np.nanargmax(np.where(valid, train_scores, np.nan)))
        oos_scores = np.array([_sharpe(row[test_idx]) for row in matrix])
        if not math.isfinite(float(oos_scores[selected])) or not np.all(np.isfinite(oos_scores)):
            continue
        rank = _average_rank(oos_scores, selected)
        omega = rank / (strategies + 1.0)
        ranks_pct.append(omega * 100)
        if omega < 0.5:
            below_median += 1
        evaluated += 1
    if evaluated == 0:
        return PBOResult(False, strategies, n_obs, n_splits, 0, None, None,
                         "No valid train/OOS split had finite Sharpe values")
    return PBOResult(True, strategies, n_obs, n_splits, evaluated,
                     below_median / evaluated, float(np.median(ranks_pct)),
                     "PBO is a historical selection-bias diagnostic; it does not estimate a guaranteed probability of future losses")
