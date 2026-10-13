"""Chronological expanding-window walk-forward split generator with embargo."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold: int
    train_start: int
    train_end_exclusive: int
    test_start: int
    test_end_exclusive: int


def expanding_walk_forward_splits(n_observations: int, *, min_train_size: int,
                                  test_size: int, step: int | None = None,
                                  embargo: int = 0) -> list[WalkForwardFold]:
    if n_observations <= 0 or min_train_size < 2 or test_size < 1 or embargo < 0:
        raise ValueError("Invalid walk-forward dimensions")
    step_size = step or test_size
    if step_size < 1:
        raise ValueError("step must be positive")
    folds: list[WalkForwardFold] = []
    test_start = min_train_size + embargo
    fold_num = 1
    while test_start < n_observations:
        train_end = test_start - embargo
        test_end = min(test_start + test_size, n_observations)
        if train_end >= min_train_size and test_end > test_start:
            folds.append(WalkForwardFold(fold_num, 0, train_end, test_start, test_end))
            fold_num += 1
        test_start += step_size
    return folds
