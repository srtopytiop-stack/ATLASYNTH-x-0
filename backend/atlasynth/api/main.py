"""FastAPI surface for the ATLASYNTH read-only quant research service.

API scope is intentionally limited to health, public market data, research,
backtesting, and hypothetical risk sizing. No order placement endpoints exist.
"""
from __future__ import annotations
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from atlasynth import __version__
from atlasynth.agents.research_agent import ResearchPipelineError, analyze_closed_candles
from atlasynth.backtesting.engine import BacktestConfig, run_backtest
from atlasynth.core.config import Settings, ConfigurationError
from atlasynth.data.binance_spot import BinanceSpotPublicClient, MarketDataConfig, MarketDataError
from atlasynth.features.indicators import FeatureError, compute_features
from atlasynth.risk.sizing import estimate_spot_position
from atlasynth.notifications.telegram import TelegramResearchNotifier, NotificationError
from atlasynth.core.models import ResearchDisposition
from atlasynth.strategies.baselines import STRATEGIES, run_strategy


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=5, max_length=24, pattern=r"^[A-Za-z0-9]+$")
    interval: str = Field(default="1h", max_length=4)
    strategy_id: str = Field(default="trend_pullback", pattern=r"^(trend_pullback|mean_reversion|breakout)$")
    candle_limit: int = Field(default=500, ge=100, le=1000)
    starting_cash: float = Field(default=1000.0, gt=0, le=1_000_000_000)
    fee_rate: float = Field(default=0.001, ge=0, le=0.02)
    slippage_bps: float = Field(default=5.0, ge=0, le=500)
    risk_per_trade: float = Field(default=0.01, gt=0, le=0.05)
    max_exposure_fraction: float = Field(default=0.9, gt=0, le=1)
    atr_stop_multiple: float = Field(default=2.0, gt=0, le=20)
    reward_risk_ratio: float = Field(default=2.0, gt=0, le=20)


class TelegramResearchRequest(BaseModel):
    symbol: str = Field(min_length=5, max_length=24, pattern=r"^[A-Za-z0-9]+$")
    interval: str = Field(default="1h", max_length=4)
    candle_limit: int = Field(default=300, ge=80, le=1000)


class RiskEstimateRequest(BaseModel):
    account_equity: float = Field(gt=0, le=1_000_000_000)
    entry_price: float = Field(gt=0)
    stop_price: float = Field(gt=0)
    risk_fraction: float = Field(default=0.01, gt=0, le=0.05)
    max_exposure_fraction: float = Field(default=0.25, gt=0, le=1)
    fee_rate: float = Field(default=0.001, ge=0, le=0.02)
    slippage_fraction: float = Field(default=0.0005, ge=0, le=0.05)


def create_app(*, settings: Settings | None = None, market_client: Any | None = None) -> FastAPI:
    try:
        cfg = settings or Settings.from_env()
    except ConfigurationError as exc:
        raise RuntimeError(str(exc)) from exc
    client = market_client or BinanceSpotPublicClient(MarketDataConfig(
        timeout_seconds=cfg.request_timeout_seconds,
        quote_asset=cfg.quote_asset,
        min_quote_volume_24h=cfg.min_quote_volume_24h,
        max_assets=cfg.max_scan_assets,
    ))
    app = FastAPI(
        title="ATLASYNTH Quant Research API",
        description="Read-only Binance Spot market analysis, backtesting, validation and risk estimates. No live trading.",
        version=__version__,
    )
    app.state.settings = cfg
    app.state.market_client = client
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins), allow_credentials=False,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "service": "atlasynth-quant-api", "version": __version__}

    @app.get("/api/v1/system/safety")
    def safety_status() -> dict[str, object]:
        return {
            **cfg.safe_summary(),
            "order_placement_endpoint_available": False,
            "exchange_credentials_required": False,
            "margin_enabled": False,
            "futures_enabled": False,
            "shorting_enabled": False,
            "manual_human_review_required": True,
        }

    @app.get("/api/v1/strategies")
    def strategies() -> list[dict[str, str]]:
        return [{"strategy_id": s.strategy_id, "description": s.description, "regime_filter": s.regime_filter}
                for s in STRATEGIES]

    @app.get("/api/v1/markets/universe")
    def universe(limit: int = Query(default=25, ge=1, le=100)) -> list[dict[str, object]]:
        try:
            assets = client.universe(limit=min(limit, cfg.max_scan_assets))
            return [asset.model_dump() for asset in assets]
        except MarketDataError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Market universe is temporarily unavailable") from exc

    @app.get("/api/v1/markets/{symbol}/candles")
    def candles(symbol: str, interval: str = Query(default="1h"),
                limit: int = Query(default=500, ge=10, le=1000)) -> list[dict[str, object]]:
        try:
            found = client.candles(symbol, interval, min(limit, cfg.max_candles_per_request), closed_only=True)
            return [c.model_dump() for c in found]
        except MarketDataError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Market candles are temporarily unavailable") from exc

    @app.get("/api/v1/research/analyze/{symbol}")
    def analyze(symbol: str, interval: str = Query(default="1h"),
                limit: int = Query(default=500, ge=80, le=1000)) -> dict[str, object]:
        if not symbol.isalnum():
            raise HTTPException(status_code=422, detail="Symbol must contain letters and numbers only")
        try:
            series = client.candles(symbol, interval, min(limit, cfg.max_candles_per_request), closed_only=True)
            report = analyze_closed_candles(symbol=symbol, interval=interval, candles=series)
            return report.model_dump(mode="json")
        except MarketDataError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except (ResearchPipelineError, FeatureError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Research analysis failed safely; inspect server diagnostics") from exc

    @app.post("/api/v1/notifications/telegram/research")
    def send_telegram_research(request: TelegramResearchRequest) -> dict[str, object]:
        """Send only a research-candidate alert to the configured chat; never an order."""
        if not cfg.telegram_enabled or not cfg.telegram_bot_token or not cfg.telegram_chat_id:
            raise HTTPException(status_code=409, detail="Telegram is disabled or not configured")
        try:
            series = client.candles(request.symbol, request.interval,
                                    min(request.candle_limit, cfg.max_candles_per_request), closed_only=True)
            report = analyze_closed_candles(symbol=request.symbol, interval=request.interval, candles=series)
            if report.disposition != ResearchDisposition.CANDIDATE:
                return {"sent": False, "reason": "The report is not a candidate; no message was sent", "disposition": report.disposition.value}
            notifier = TelegramResearchNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id, cfg.request_timeout_seconds)
            notifier.send(report)
            return {"sent": True, "symbol": report.symbol, "disposition": report.disposition.value,
                    "message_scope": "research alert only; no trade was placed", "live_trading_enabled": False}
        except MarketDataError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except NotificationError as exc:
            raise HTTPException(status_code=502, detail="Telegram notification failed; research result was not sent") from exc
        except (ResearchPipelineError, FeatureError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/research/scan")
    def scan_market(
        assets_to_scan: int = Query(default=10, ge=1, le=25),
        interval: str = Query(default="1h"),
        candle_limit: int = Query(default=300, ge=80, le=1000),
    ) -> dict[str, object]:
        """Screen a bounded top-volume universe; failures remain visible per asset."""
        try:
            universe_items = client.universe(limit=min(assets_to_scan, cfg.max_scan_assets, 25))
        except MarketDataError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        reports: list[dict[str, object]] = []
        failures: list[dict[str, str]] = []
        for asset in universe_items:
            try:
                series = client.candles(asset.symbol, interval,
                                        min(candle_limit, cfg.max_candles_per_request), closed_only=True)
                report = analyze_closed_candles(symbol=asset.symbol, interval=interval, candles=series)
                reports.append(report.model_dump(mode="json"))
            except Exception as exc:
                # The error message is deliberately bounded; server logs can contain diagnostics.
                failures.append({"symbol": asset.symbol, "error": str(exc)[:240]})
        reports.sort(key=lambda r: (
            0 if r["disposition"] == "CANDIDATE" else 1,
            -float(r["evidence_score"]), str(r["symbol"]),
        ))
        return {
            "generated_at_ms": __import__("time").time_ns() // 1_000_000,
            "requested_assets": assets_to_scan,
            "assets_selected": len(universe_items),
            "assets_analyzed": len(reports),
            "assets_failed": len(failures),
            "ranked_by": "disposition then evidence checklist score; not expected return or win probability",
            "partial_results": bool(failures),
            "reports": reports,
            "failures": failures,
            "live_trading_enabled": False,
        }

    @app.post("/api/v1/backtests/run")
    def backtest(request: BacktestRequest) -> dict[str, object]:
        try:
            series = client.candles(request.symbol, request.interval, request.candle_limit, closed_only=True)
            if len(series) < 100:
                raise HTTPException(status_code=422, detail="At least 100 completed candles are required for this baseline backtest")
            features = compute_features(series)
            signals = run_strategy(request.strategy_id, features)
            cfg_bt = BacktestConfig(
                starting_cash=request.starting_cash, fee_rate=request.fee_rate,
                slippage_bps=request.slippage_bps, risk_per_trade=request.risk_per_trade,
                max_exposure_fraction=request.max_exposure_fraction,
                atr_stop_multiple=request.atr_stop_multiple, reward_risk_ratio=request.reward_risk_ratio,
            )
            result = run_backtest(symbol=request.symbol, interval=request.interval, candles=series,
                                  signals=signals, strategy_id=request.strategy_id, config=cfg_bt)
            return result.to_dict()
        except HTTPException:
            raise
        except MarketDataError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except (ValueError, FeatureError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Backtest failed safely; inspect server diagnostics") from exc

    @app.post("/api/v1/risk/estimate")
    def risk_estimate(request: RiskEstimateRequest) -> dict[str, object]:
        try:
            return estimate_spot_position(**request.model_dump()).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


app = create_app()
