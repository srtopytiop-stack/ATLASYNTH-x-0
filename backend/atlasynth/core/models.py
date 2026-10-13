"""Immutable domain contracts shared between data, research, and API layers."""
from __future__ import annotations

from enum import Enum
import math
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MarketRegime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


class ResearchDisposition(str, Enum):
    WATCH = "WATCH"
    CANDIDATE = "CANDIDATE"
    REJECTED = "REJECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Candle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    open_time_ms: int = Field(ge=0)
    close_time_ms: int = Field(ge=0)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    quote_volume: float | None = Field(default=None, ge=0)
    trades: int | None = Field(default=None, ge=0)
    is_closed: bool

    @model_validator(mode="after")
    def check_ohlcv(self) -> "Candle":
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("OHLCV values must be finite")
        if self.close_time_ms < self.open_time_ms:
            raise ValueError("close_time_ms precedes open_time_ms")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is inconsistent with OHLC")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low is inconsistent with OHLC")
        if self.quote_volume is not None and not math.isfinite(self.quote_volume):
            raise ValueError("quote volume must be finite")
        return self


class UniverseAsset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    base_asset: str
    quote_asset: str
    last_price: float = Field(gt=0)
    quote_volume_24h: float = Field(ge=0)
    change_pct_24h: float
    trades_24h: int = Field(ge=0)


class StrategySignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    strategy_id: str
    symbol: str
    interval: str
    disposition: ResearchDisposition
    market_regime: MarketRegime
    evidence_score: float = Field(ge=0, le=100)
    score_is_probability: bool = False
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    as_of_ms: int
    data_points: int = Field(ge=0)

    @model_validator(mode="after")
    def prevent_probability_claim(self) -> "StrategySignal":
        if self.score_is_probability:
            raise ValueError("An evidence score must never be represented as a win probability")
        return self


class ResearchReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    interval: str
    generated_at_ms: int
    provenance_hash: str | None = None
    disposition: ResearchDisposition
    regime: MarketRegime
    evidence_score: float = Field(ge=0, le=100)
    score_is_probability: bool = False
    live_trading_enabled: bool = False
    order_execution_enabled: bool = False
    price: float | None = Field(default=None, gt=0)
    strategy_signals: tuple[StrategySignal, ...]
    data_warnings: tuple[str, ...] = ()
    validation_warnings: tuple[str, ...] = ()
    risk_notes: tuple[str, ...] = ()
    human_review_required: bool = True

    @model_validator(mode="after")
    def enforce_report_conventions(self) -> "ResearchReport":
        if self.score_is_probability:
            raise ValueError("Evidence score is not a calibrated probability")
        if not self.human_review_required:
            raise ValueError("Research report always requires human review")
        if self.live_trading_enabled or self.order_execution_enabled:
            raise ValueError("This research agent cannot enable live or simulated exchange order endpoints")
        return self
