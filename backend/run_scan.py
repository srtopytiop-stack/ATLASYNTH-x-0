"""Run one command-line analysis scan; data-only and human review only."""
from __future__ import annotations
import argparse
import json

from atlasynth.agents.research_agent import analyze_closed_candles
from atlasynth.core.config import Settings
from atlasynth.data.binance_spot import BinanceSpotPublicClient, MarketDataConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="ATLASYNTH read-only Spot research scan")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    settings = Settings.from_env()
    client = BinanceSpotPublicClient(MarketDataConfig(
        timeout_seconds=settings.request_timeout_seconds,
        quote_asset=settings.quote_asset,
        min_quote_volume_24h=settings.min_quote_volume_24h,
        max_assets=settings.max_scan_assets,
    ))
    candles = client.candles(args.symbol, args.interval, args.limit, closed_only=True)
    result = analyze_closed_candles(symbol=args.symbol, interval=args.interval, candles=candles)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
