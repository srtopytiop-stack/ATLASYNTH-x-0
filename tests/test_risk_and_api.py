from fastapi.testclient import TestClient
from atlasynth.api.main import create_app
from atlasynth.core.config import Settings
from atlasynth.risk.sizing import estimate_spot_position
from conftest import FakeMarketClient


def test_risk_sizing_is_pure_and_never_places_orders():
    result = estimate_spot_position(account_equity=1000, entry_price=100, stop_price=95)
    assert result.estimated_quantity > 0
    assert result.estimated_loss_at_stop_quote <= result.risk_budget_quote * 1.01
    assert result.live_order_placed is False


def test_api_health_and_safety_contract():
    app = create_app(settings=Settings(), market_client=FakeMarketClient())
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    safety = client.get("/api/v1/system/safety").json()
    assert safety["order_placement_endpoint_available"] is False
    assert safety["live_trading_enabled"] is False
    assert client.get("/api/v1/strategies").status_code == 200


def test_api_research_report_has_human_review_and_non_probability_score():
    app = create_app(settings=Settings(), market_client=FakeMarketClient())
    client = TestClient(app)
    response = client.get("/api/v1/research/analyze/ETHUSDT?interval=1h&limit=220")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["human_review_required"] is True
    assert report["score_is_probability"] is False
    assert report["live_trading_enabled"] is False
    assert report["order_execution_enabled"] is False
    assert report["provenance_hash"]


def test_api_multi_asset_scan_preserves_per_symbol_research_results():
    app = create_app(settings=Settings(), market_client=FakeMarketClient())
    client = TestClient(app)
    response = client.get("/api/v1/research/scan?assets_to_scan=1&interval=1h&candle_limit=220")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["assets_analyzed"] == 1
    assert data["live_trading_enabled"] is False
    assert "not expected return" in data["ranked_by"]
