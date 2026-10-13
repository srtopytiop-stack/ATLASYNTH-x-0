from __future__ import annotations
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from atlasynth.core.models import Candle, UniverseAsset  # noqa: E402


def make_candles(n: int = 240, *, start_ms: int = 1_700_000_000_000, interval_ms: int = 3_600_000) -> list[Candle]:
    candles: list[Candle] = []
    previous = 100.0
    for i in range(n):
        # Deterministic, non-constant series with alternating local movement.
        close = 100.0 + i * 0.04 + 1.8 * math.sin(i / 7.0) + 0.4 * math.sin(i / 2.3)
        open_price = previous
        high = max(open_price, close) + 0.35 + 0.05 * (i % 3)
        low = min(open_price, close) - 0.32 - 0.04 * (i % 4)
        candles.append(Candle(
            open_time_ms=start_ms + i * interval_ms,
            close_time_ms=start_ms + (i + 1) * interval_ms - 1,
            open=open_price, high=high, low=low, close=close,
            volume=1000.0 + 20.0 * math.sin(i / 3.0) + i,
            quote_volume=(1000.0 + i) * close, trades=100 + i, is_closed=True,
        ))
        previous = close
    return candles


class FakeMarketClient:
    def __init__(self, candles=None):
        self._candles = candles or make_candles()

    def universe(self, *, limit=None):
        items = [UniverseAsset(symbol="ETHUSDT", base_asset="ETH", quote_asset="USDT", last_price=2000,
                               quote_volume_24h=5_000_000, change_pct_24h=1.2, trades_24h=5000)]
        return items[:limit]

    def candles(self, symbol, interval="1h", limit=500, *, closed_only=True, now_ms=None):
        result = self._candles[-limit:]
        return [c for c in result if not closed_only or c.is_closed]
