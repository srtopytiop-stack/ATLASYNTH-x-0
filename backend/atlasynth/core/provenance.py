"""Stable research-run fingerprints; hashes are for traceability, not authenticity."""
from __future__ import annotations
import hashlib
import json
from typing import Any
from atlasynth.core.models import Candle


def fingerprint_run(*, symbol: str, interval: str, candles: list[Candle], parameters: dict[str, Any]) -> str:
    payload = {
        "schema": "atlasynth-run-v1", "symbol": symbol.upper(), "interval": interval,
        "candles": [c.model_dump(mode="json") for c in candles],
        "parameters": parameters,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
