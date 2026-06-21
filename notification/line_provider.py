from __future__ import annotations

import httpx

LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"


class LineProvider:
    def __init__(self, token: str) -> None:
        self._headers = {"Authorization": f"Bearer {token}"}

    def send(self, text: str) -> None:
        httpx.post(LINE_NOTIFY_URL, headers=self._headers, data={"message": text}, timeout=10)
