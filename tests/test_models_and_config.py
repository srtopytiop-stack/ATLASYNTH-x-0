import pytest
from atlasynth.core.config import ConfigurationError, Settings
from atlasynth.core.models import Candle, ResearchDisposition, ResearchReport, MarketRegime


def test_candle_rejects_inconsistent_ohlc():
    with pytest.raises(ValueError):
        Candle(open_time_ms=1, close_time_ms=2, open=10, high=9, low=8, close=9, volume=1, is_closed=True)


def test_safe_settings_default_to_no_trading(monkeypatch):
    monkeypatch.delenv("TRADING_ENABLED", raising=False)
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    cfg = Settings.from_env()
    summary = cfg.safe_summary()
    assert summary["trading_enabled"] is False
    assert summary["live_trading_enabled"] is False
    assert summary["public_market_data_only"] is True


def test_live_trading_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("TRADING_ENABLED", "false")
    with pytest.raises(ConfigurationError):
        Settings.from_env()
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)


def test_research_score_cannot_claim_probability():
    with pytest.raises(ValueError):
        ResearchReport(symbol="ETHUSDT", interval="1h", generated_at_ms=1, score_is_probability=True,
                       disposition=ResearchDisposition.WATCH, regime=MarketRegime.UNKNOWN, evidence_score=50,
                       strategy_signals=(), human_review_required=True)
