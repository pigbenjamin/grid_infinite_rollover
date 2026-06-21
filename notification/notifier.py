"""
告警通知系統 — Notifier

統一介面，依 config.yaml 設定選擇 Telegram 或 LINE Notify。
CRITICAL 等級須在 30 秒內送出，不得被非致命例外阻塞。
"""
from __future__ import annotations

import logging
import threading
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Notifier:
    def __init__(self, cfg: dict) -> None:
        provider = cfg.get("provider", "").lower()
        token = cfg.get("token", "")
        chat_id = cfg.get("chat_id", "")

        if provider == "telegram" and token:
            from notification.telegram_provider import TelegramProvider
            self._provider = TelegramProvider(token, chat_id)
        elif provider == "line" and token:
            from notification.line_provider import LineProvider
            self._provider = LineProvider(token)
        else:
            self._provider = None
            logger.info("通知系統未設定（僅記錄日誌）")

    def send(self, level: AlertLevel, module: str, message: str) -> None:
        text = f"[{level.value}] [{module}] {message}"
        logger.log(
            logging.CRITICAL if level == AlertLevel.CRITICAL else
            logging.WARNING if level == AlertLevel.WARNING else
            logging.INFO,
            text,
        )
        if self._provider:
            t = threading.Thread(target=self._safe_send, args=(text,), daemon=True)
            t.start()
            if level == AlertLevel.CRITICAL:
                t.join(timeout=30)

    def _safe_send(self, text: str) -> None:
        try:
            self._provider.send(text)
        except Exception as e:
            logger.error("通知送出失敗：%s", e)
