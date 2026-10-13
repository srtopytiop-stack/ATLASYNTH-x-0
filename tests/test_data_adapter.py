from atlasynth.data.binance_spot import BinanceSpotPublicClient, MarketDataConfig


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class FakeSession:
    def get(self, url, *, params=None, timeout=10):
        if url.endswith("exchangeInfo"):
            return FakeResponse({"symbols": [
                {"symbol": "AAAUSDT", "status": "TRADING", "isSpotTradingAllowed": True, "quoteAsset": "USDT", "baseAsset": "AAA"},
                {"symbol": "BBBUPUSDT", "status": "TRADING", "isSpotTradingAllowed": True, "quoteAsset": "USDT", "baseAsset": "BBBUP"},
                {"symbol": "CCCUSDT", "status": "BREAK", "isSpotTradingAllowed": True, "quoteAsset": "USDT", "baseAsset": "CCC"},
            ]})
        if url.endswith("ticker/24hr"):
            return FakeResponse([
                {"symbol": "AAAUSDT", "lastPrice": "2", "quoteVolume": "3000000", "priceChangePercent": "1.2", "count": 50},
                {"symbol": "BBBUPUSDT", "lastPrice": "1", "quoteVolume": "5000000", "priceChangePercent": "4", "count": 100},
                {"symbol": "CCCUSDT", "lastPrice": "1", "quoteVolume": "9000000", "priceChangePercent": "4", "count": 100},
            ])
        if url.endswith("klines"):
            return FakeResponse([[0,"10","11","9","10.5","2",59999,"21",4,"1","11","0"]])
        if url.endswith("time"):
            return FakeResponse({"serverTime": 100000})
        raise AssertionError(url)


def test_universe_is_dynamic_and_filters_ineligible_products():
    client = BinanceSpotPublicClient(MarketDataConfig(min_quote_volume_24h=1, max_assets=10), FakeSession())
    assets = client.universe()
    assert [a.symbol for a in assets] == ["AAAUSDT"]


def test_kline_adapter_marks_open_candle_and_can_exclude_it():
    client = BinanceSpotPublicClient(session=FakeSession())
    all_candles = client.candles("AAAUSDT", "1m", 1, closed_only=False, now_ms=100000)
    assert all_candles[0].is_closed is True
    assert client.candles("AAAUSDT", "1m", 1, closed_only=True, now_ms=50000) == []
