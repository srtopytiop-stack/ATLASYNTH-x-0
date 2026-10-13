"""Optional Telegram research alerts; no exchange integration."""
from __future__ import annotations
import requests
from atlasynth.core.models import ResearchReport


class NotificationError(RuntimeError):
    pass


class TelegramResearchNotifier:
    def __init__(self, bot_token: str, chat_id: str, timeout_seconds: float = 10.0):
        if not bot_token.strip() or not chat_id.strip():
            raise ValueError("Telegram token and chat ID are required")
        self._token = bot_token
        self._chat_id = chat_id
        self._timeout = timeout_seconds

    def format_report(self, report: ResearchReport) -> str:
        # Avoid Markdown special formatting from symbols or external text.
        lines = [
            "ATLASYNTH research alert (analysis only)",
            f"Asset: {report.symbol}", f"Interval: {report.interval}",
            f"Disposition: {report.disposition.value}", f"Regime: {report.regime.value}",
            f"Evidence score: {report.evidence_score:.1f}/100 (NOT win probability)",
            f"Price at analysis: {report.price if report.price is not None else 'unavailable'}",
            "Strategies: " + ", ".join(f"{s.strategy_id}={s.disposition.value}" for s in report.strategy_signals),
            "Human review required. No trade was placed.",
        ]
        return "\n".join(lines)

    def send(self, report: ResearchReport) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            response = requests.post(url, json={"chat_id": self._chat_id, "text": self.format_report(report)}, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise NotificationError("Telegram research notification failed") from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise NotificationError("Telegram rejected the research notification")
