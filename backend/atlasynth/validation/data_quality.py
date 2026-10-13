"""Validate raw candle series before research consumption."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
from atlasynth.core.models import Candle
from atlasynth.data.binance_spot import interval_milliseconds


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    valid: bool
    observations: int
    duplicate_timestamps: int
    out_of_order_pairs: int
    incomplete_candles: int
    gaps: int
    non_finite_values: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def assess_candles(candles: list[Candle], interval: str) -> DataQualityReport:
    interval_ms = interval_milliseconds(interval)
    opens = [c.open_time_ms for c in candles]
    duplicate_count = len(opens) - len(set(opens))
    out_of_order = sum(1 for a, b in zip(opens, opens[1:]) if b <= a)
    incomplete = sum(1 for c in candles if not c.is_closed)
    non_finite = 0
    for c in candles:
        values = [c.open, c.high, c.low, c.close, c.volume]
        non_finite += sum(not math.isfinite(x) for x in values)
    gaps = sum(1 for a, b in zip(opens, opens[1:]) if b - a > interval_ms * 1.5)
    warnings: list[str] = []
    if not candles:
        warnings.append("No candles supplied")
    if duplicate_count:
        warnings.append(f"{duplicate_count} duplicate timestamp(s)")
    if out_of_order:
        warnings.append(f"{out_of_order} non-increasing timestamp transition(s)")
    if incomplete:
        warnings.append(f"{incomplete} incomplete candle(s)")
    if gaps:
        warnings.append(f"{gaps} interval gap(s); rolling features may span missing time")
    if non_finite:
        warnings.append(f"{non_finite} non-finite OHLCV field(s)")
    valid = bool(candles) and duplicate_count == 0 and out_of_order == 0 and incomplete == 0 and non_finite == 0
    return DataQualityReport(valid, len(candles), duplicate_count, out_of_order, incomplete,
                             gaps, non_finite, tuple(warnings))
