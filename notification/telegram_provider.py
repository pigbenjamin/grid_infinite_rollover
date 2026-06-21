from __future__ import annotations

import httpx


class TelegramProvider:
    def __init__(self, token: str, chat_id: str) -> None:
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id

    def send(self, text: str) -> None:
        httpx.post(self._url, json={"chat_id": self._chat_id, "text": text}, timeout=10)
