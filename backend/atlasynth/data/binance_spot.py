"""Read-only Binance Spot public-market-data adapter.

There are intentionally no account, signing, order, cancel, or withdrawal methods.
Public market-data-only endpoint: https://data-api.binance.vision
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Protocol

import requests

from atlasynth.core.models import Candle, UniverseAsset


class MarketDataError(RuntimeError):
    pass


class SessionLike(Protocol):
    def get(self, url: str, *, params: dict[str, Any] | None = None, timeout: float = 10) -> Any: ...


@dataclass(frozen=True, slots=True)
class MarketDataConfig:
    timeout_seconds: float = 10.0
    max_retries: int = 2
    quote_asset: str = "USDT"
    min_quote_volume_24h: float = 1_000_000.0
    max_assets: int = 25


_INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000,
    "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000,
    "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000,
    "1w": 604_800_000,
}

# Avoid common leveraged-token products being mistaken for ordinary spot assets.
_LEVERAGED_SUFFIXES = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")


class BinanceSpotPublicClient:
    BASE_URL = "https://data-api.binance.vision"

    def __init__(self, config: MarketDataConfig | None = None, session: SessionLike | None = None):
        self.config = config or MarketDataConfig()
        self.session = session or requests.Session()

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.BASE_URL}{path}"
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.config.timeout_seconds)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    time.sleep(min(0.25 * (2 ** attempt), 1.0))
        raise MarketDataError(f"Public market-data request failed for {path}: {last_error}") from last_error

    def server_time_ms(self) -> int:
        payload = self._get_json("/api/v3/time")
        try:
            return int(payload["serverTime"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketDataError("Malformed Binance server-time response") from exc

    def universe(self, *, limit: int | None = None) -> list[UniverseAsset]:
        """Return a deterministic top-N universe of eligible quote-asset spot pairs."""
        info = self._get_json("/api/v3/exchangeInfo")
        tickers = self._get_json("/api/v3/ticker/24hr")
        if not isinstance(info, dict) or not isinstance(info.get("symbols"), list):
            raise MarketDataError("Malformed exchangeInfo response")
        if not isinstance(tickers, list):
            raise MarketDataError("Malformed 24h ticker response")
        allowed: dict[str, tuple[str, str]] = {}
        for item in info["symbols"]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", ""))
            if (item.get("status") == "TRADING"
                and item.get("isSpotTradingAllowed", True) is True
                and item.get("quoteAsset") == self.config.quote_asset
                and symbol
                and not symbol.endswith(_LEVERAGED_SUFFIXES)):
                allowed[symbol] = (str(item.get("baseAsset", "")), str(item.get("quoteAsset", "")))
        candidates: list[UniverseAsset] = []
        for item in tickers:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            if symbol not in allowed:
                continue
            try:
                price = float(item["lastPrice"])
                quote_volume = float(item["quoteVolume"])
                change = float(item["priceChangePercent"])
                trades = int(item["count"])
            except (KeyError, TypeError, ValueError):
                continue
            if not all(__import__("math").isfinite(v) for v in (price, quote_volume, change)):
                continue
            if price <= 0 or quote_volume < self.config.min_quote_volume_24h or trades < 0:
                continue
            base, quote = allowed[symbol]
            candidates.append(UniverseAsset(
                symbol=symbol, base_asset=base, quote_asset=quote, last_price=price,
                quote_volume_24h=quote_volume, change_pct_24h=change, trades_24h=trades,
            ))
        candidates.sort(key=lambda a: (-a.quote_volume_24h, a.symbol))
        n = self.config.max_assets if limit is None else max(1, min(int(limit), 100))
        return candidates[:n]

    def candles(self, symbol: str, interval: str = "1h", limit: int = 500,
                *, closed_only: bool = True, now_ms: int | None = None) -> list[Candle]:
        symbol = symbol.strip().upper()
        if not symbol or not symbol.isalnum():
            raise MarketDataError("symbol must contain only letters and numbers")
        if interval not in _INTERVAL_MS:
            raise MarketDataError(f"Unsupported interval: {interval}")
        if not 1 <= int(limit) <= 1000:
            raise MarketDataError("limit must be between 1 and 1000")
        payload = self._get_json("/api/v3/klines", {
            "symbol": symbol, "interval": interval, "limit": int(limit),
        })
        if not isinstance(payload, list):
            raise MarketDataError("Malformed kline response")
        clock = now_ms if now_ms is not None else self.server_time_ms()
        candles: list[Candle] = []
        last_open = -1
        interval_ms = _INTERVAL_MS[interval]
        for row in payload:
            if not isinstance(row, list) or len(row) < 11:
                raise MarketDataError("Malformed kline row")
            try:
                open_time, close_time = int(row[0]), int(row[6])
                if open_time <= last_open:
                    raise MarketDataError("Kline timestamps are duplicated or out of order")
                if close_time < open_time or close_time - open_time >= interval_ms:
                    raise MarketDataError("Kline duration is invalid for interval")
                candle = Candle(
                    open_time_ms=open_time, close_time_ms=close_time,
                    open=float(row[1]), high=float(row[2]), low=float(row[3]),
                    close=float(row[4]), volume=float(row[5]),
                    quote_volume=float(row[7]), trades=int(row[8]),
                    is_closed=close_time < clock,
                )
                last_open = open_time
            except (TypeError, ValueError) as exc:
                if isinstance(exc, MarketDataError):
                    raise
                raise MarketDataError("Kline contains invalid numeric data") from exc
            if not closed_only or candle.is_closed:
                candles.append(candle)
        return candles


def interval_milliseconds(interval: str) -> int:
    try:
        return _INTERVAL_MS[interval]
    except KeyError as exc:
        raise MarketDataError(f"Unsupported interval: {interval}") from exc
