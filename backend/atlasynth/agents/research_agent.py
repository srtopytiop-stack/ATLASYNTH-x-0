"""Deterministic multi-specialist analysis pipeline built around explicit contracts.

The word 'agent' describes orchestration of bounded research roles; this module
uses no LLM, makes no broker calls, and cannot place orders.
"""
from __future__ import annotations
from datetime import datetime, timezone
import math

import pandas as pd

from atlasynth.core.models import Candle, MarketRegime, ResearchDisposition, ResearchReport, StrategySignal
from atlasynth.core.provenance import fingerprint_run
from atlasynth.data.binance_spot import interval_milliseconds
from atlasynth.features.indicators import compute_features
from atlasynth.regimes.classifier import classify_regime
from atlasynth.strategies.baselines import STRATEGIES, run_strategy


class ResearchPipelineError(RuntimeError):
    pass


def _evidence_score(features: pd.DataFrame, regime: MarketRegime, strategies: list[pd.DataFrame]) -> float:
    """Weighted evidence checklist. This is not a probability or expected return."""
    row = features.iloc[-1]
    score = 0.0
    # Mature history helps data adequacy; it is not itself evidence of alpha.
    score += 15.0 if len(features) >= 200 else 8.0 if len(features) >= 100 else 0.0
    if pd.notna(row.get("ema_fast")) and pd.notna(row.get("ema_slow")) and row.ema_fast > row.ema_slow:
        score += 15.0
    if pd.notna(row.get("rsi")) and 45 <= row.rsi <= 68:
        score += 10.0
    if pd.notna(row.get("volume_zscore")) and row.volume_zscore >= 0:
        score += 10.0
    if regime == MarketRegime.TREND_UP:
        score += 15.0
    elif regime == MarketRegime.RANGE:
        score += 10.0
    elif regime == MarketRegime.TRANSITION:
        score += 5.0
    # Moderate volatility versus recent history is preferred over an unbounded volatility target.
    vol = features["realized_volatility"].dropna().tail(100)
    if len(vol) >= 20 and float(vol.iloc[-1]) <= float(vol.median()) * 1.8:
        score += 10.0
    candidate_count = sum(bool(s.iloc[-1]["entry"]) for s in strategies)
    score += {0: 0.0, 1: 10.0, 2: 15.0, 3: 20.0}[candidate_count]
    if regime == MarketRegime.HIGH_VOLATILITY:
        score -= 20.0
    return round(max(0.0, min(100.0, score)), 2)


def analyze_closed_candles(*, symbol: str, interval: str, candles: list[Candle]) -> ResearchReport:
    if len(candles) < 3:
        raise ResearchPipelineError("At least three closed candles are required")
    if any(not c.is_closed for c in candles):
        raise ResearchPipelineError("Research requires completed candles only")
    opens = [c.open_time_ms for c in candles]
    if opens != sorted(opens) or len(opens) != len(set(opens)):
        raise ResearchPipelineError("Candles must be chronological with no duplicate open times")
    if candles[-1].close_time_ms >= int(datetime.now(timezone.utc).timestamp() * 1000):
        # May be false when exchange/server time differs slightly; data adapter remains source of truth.
        data_warnings = ["Latest candle close timestamp is not safely in the past relative to local UTC clock"]
    else:
        data_warnings = []
    interval_ms = interval_milliseconds(interval)
    gaps = sum(1 for a, b in zip(opens, opens[1:]) if b - a > interval_ms * 1.5)
    if gaps:
        data_warnings.append(f"Detected {gaps} timestamp gap(s); some indicator windows span missing intervals")
    if len(candles) < 80:
        return ResearchReport(
            symbol=symbol.upper(), interval=interval, generated_at_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
            disposition=ResearchDisposition.INSUFFICIENT_DATA, regime=MarketRegime.UNKNOWN,
            provenance_hash=fingerprint_run(symbol=symbol, interval=interval, candles=candles, parameters={"analysis_version": "0.1.0", "status": "insufficient_data"}),
            evidence_score=0, price=candles[-1].close, strategy_signals=(),
            data_warnings=tuple(data_warnings + ["At least 80 candles are required for screening; longer history is preferred"]),
            validation_warnings=("No out-of-sample backtest was performed for this snapshot",),
            risk_notes=("No trading recommendation is issued from insufficient data",), human_review_required=True,
        )
    features = compute_features(candles)
    regime, regime_reasons = classify_regime(features)
    signal_frames = [run_strategy(d.strategy_id, features) for d in STRATEGIES]
    score = _evidence_score(features, regime, signal_frames)
    signals: list[StrategySignal] = []
    for definition, frame in zip(STRATEGIES, signal_frames):
        last = frame.iloc[-1]
        candidate = bool(last["entry"])
        reasons = [str(last["reason"])]
        if regime_reasons:
            reasons.extend(regime_reasons[:1])
        if not candidate:
            reasons.append("Entry conditions are not satisfied on the latest completed candle")
        signals.append(StrategySignal(
            strategy_id=definition.strategy_id, symbol=symbol.upper(), interval=interval,
            disposition=ResearchDisposition.CANDIDATE if candidate else ResearchDisposition.WATCH,
            market_regime=regime, evidence_score=score, score_is_probability=False,
            reasons=tuple(reasons), warnings=("Screening rule only; strategy has not necessarily passed historical validation",),
            as_of_ms=candles[-1].close_time_ms, data_points=len(candles),
        ))
    candidates = sum(s.disposition == ResearchDisposition.CANDIDATE for s in signals)
    if regime in (MarketRegime.UNKNOWN, MarketRegime.HIGH_VOLATILITY) or gaps > max(2, len(candles) // 100):
        disposition = ResearchDisposition.WATCH
    elif candidates >= 2 and score >= 55:
        disposition = ResearchDisposition.CANDIDATE
    else:
        disposition = ResearchDisposition.WATCH
    validation_warnings = [
        "This is a current-market screening report, not a backtest or a calibrated probability of profit",
        "No trade should be considered validated until a separate cost-aware walk-forward process is run",
    ]
    risk_notes = [
        "Spot long-only research; no leverage, margin, futures, or shorting",
        "No order was or can be placed by this analysis pipeline",
        "Any stop, target, or position-size number produced elsewhere is hypothetical and requires human review",
    ]
    if regime == MarketRegime.HIGH_VOLATILITY:
        risk_notes.append("High-volatility regime detected; entry candidates are downgraded to WATCH")
    if candidates == 0:
        risk_notes.append("No strategy has a current entry candidate; do not force a trade")
    return ResearchReport(
        symbol=symbol.upper(), interval=interval,
        generated_at_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        provenance_hash=fingerprint_run(symbol=symbol, interval=interval, candles=candles, parameters={"analysis_version": "0.1.0", "strategies": [s.strategy_id for s in STRATEGIES]}),
        disposition=disposition, regime=regime, evidence_score=score,
        score_is_probability=False, price=candles[-1].close, strategy_signals=tuple(signals),
        data_warnings=tuple(data_warnings), validation_warnings=tuple(validation_warnings),
        risk_notes=tuple(risk_notes), human_review_required=True,
    )
