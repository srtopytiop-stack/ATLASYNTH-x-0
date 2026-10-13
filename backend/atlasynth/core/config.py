"""Validated runtime settings and non-negotiable safety defaults."""
from __future__ import annotations

from dataclasses import dataclass
import os


class ConfigurationError(RuntimeError):
    pass


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value")


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = default if raw is None or not raw.strip() else int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    try:
        value = default if raw is None or not raw.strip() else float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str = "development"
    log_level: str = "INFO"
    exchange: str = "binance"
    trading_type: str = "spot"
    trading_enabled: bool = False
    live_trading_enabled: bool = False
    public_market_data_only: bool = True
    quote_asset: str = "USDT"
    max_scan_assets: int = 25
    min_quote_volume_24h: float = 1_000_000.0
    request_timeout_seconds: float = 10.0
    max_candles_per_request: int = 1000
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        # These are policy constraints rather than user-configurable trading modes.
        trading_enabled = _bool_env("TRADING_ENABLED", False)
        live_enabled = _bool_env("LIVE_TRADING_ENABLED", False)
        public_only = _bool_env("PUBLIC_MARKET_DATA_ONLY", True)
        exchange = (os.getenv("EXCHANGE", "binance") or "binance").strip().lower()
        trading_type = (os.getenv("TRADING_TYPE", "spot") or "spot").strip().lower()
        if trading_enabled or live_enabled:
            raise ConfigurationError(
                "ATLASYNTH is analysis-only: TRADING_ENABLED and LIVE_TRADING_ENABLED must remain false"
            )
        if not public_only or exchange != "binance" or trading_type != "spot":
            raise ConfigurationError(
                "Only public Binance Spot market data is supported in this build"
            )
        origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        origins = tuple(x.strip() for x in origins_raw.split(",") if x.strip())
        telegram_enabled = _bool_env("TELEGRAM_ENABLED", False)
        token = os.getenv("TELEGRAM_BOT_TOKEN") or None
        chat_id = os.getenv("TELEGRAM_CHAT_ID") or None
        if telegram_enabled and not (token and chat_id):
            raise ConfigurationError("Telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return cls(
            app_env=os.getenv("EVA_ENV", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            exchange=exchange,
            trading_type=trading_type,
            trading_enabled=trading_enabled,
            live_trading_enabled=live_enabled,
            public_market_data_only=public_only,
            quote_asset=(os.getenv("QUOTE_ASSET", "USDT") or "USDT").upper(),
            max_scan_assets=_int_env("MAX_SCAN_ASSETS", 25, 1, 100),
            min_quote_volume_24h=_float_env("MIN_QUOTE_VOLUME_24H", 1_000_000.0, 0.0, 1e15),
            request_timeout_seconds=_float_env("REQUEST_TIMEOUT_SECONDS", 10.0, 1.0, 60.0),
            max_candles_per_request=_int_env("MAX_CANDLES_PER_REQUEST", 1000, 100, 1000),
            cors_origins=origins or ("http://localhost:5173",),
            telegram_enabled=telegram_enabled,
            telegram_bot_token=token,
            telegram_chat_id=chat_id,
        )

    def safe_summary(self) -> dict[str, object]:
        """Return configuration safe to expose publicly; never expose secrets."""
        return {
            "environment": self.app_env,
            "exchange": self.exchange,
            "trading_type": self.trading_type,
            "trading_enabled": False,
            "live_trading_enabled": False,
            "public_market_data_only": True,
            "quote_asset": self.quote_asset,
            "telegram_enabled": self.telegram_enabled,
        }
