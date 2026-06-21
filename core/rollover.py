"""
換倉模組 — RolloverManager

負責：
- 每日盤後監控 DTE
- 執行換倉流程（暫停網格 → 平倉舊 → 建倉新 → 記錄成本 → 恢復網格）
- 換倉失敗應急處理
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from broker.base import AbstractBroker, ContractExpiredError, OrderRejectedError
from db import models


class RolloverManager:
    def __init__(self, broker: AbstractBroker, db_path: str,
                 multiplier: int, dte_threshold: int = 5) -> None:
        self._broker = broker
        self._db_path = db_path
        self._multiplier = multiplier
        self._dte_threshold = dte_threshold
        self._on_rollover_complete: Optional[Callable[[str], None]] = None
        self._on_rollover_failed: Optional[Callable[[str], None]] = None

    def set_callbacks(self, on_complete: Callable, on_failed: Callable) -> None:
        self._on_rollover_complete = on_complete
        self._on_rollover_failed = on_failed

    def check_and_rollover(self, current_symbol: str, next_symbol: str,
                           dte: int) -> bool:
        """
        盤後呼叫，若 DTE ≤ 閥值則執行換倉。
        回傳 True 表示換倉已執行，False 表示未觸發。
        """
        if dte > self._dte_threshold:
            return False

        positions = self._broker.get_positions()
        qty = sum(p["quantity"] for p in positions if p["symbol"] == current_symbol)
        if qty == 0:
            return False

        self._execute_rollover(current_symbol, next_symbol, qty)
        return True

    def _execute_rollover(self, old_symbol: str, new_symbol: str, qty: int) -> None:
        close_price: float = 0.0
        open_price: float = 0.0

        try:
            close_id = self._broker.place_order("MARKET", None, qty, "SELL")
            close_status = self._broker.get_order_status(close_id)
            close_price = close_status["filled_price"]
        except Exception as e:
            if self._on_rollover_failed:
                self._on_rollover_failed(f"平倉舊合約失敗：{e}")
            raise

        try:
            open_id = self._broker.place_order("MARKET", None, qty, "BUY")
            open_status = self._broker.get_order_status(open_id)
            open_price = open_status["filled_price"]
        except (OrderRejectedError, Exception) as e:
            if self._on_rollover_failed:
                self._on_rollover_failed(
                    f"舊合約已平倉，但新合約建倉失敗（{e}）。請人工介入。"
                )
            raise

        spread = open_price - close_price
        cost_ntd = spread * self._multiplier * qty

        models.insert_rollover_log(self._db_path, {
            "old_symbol": old_symbol,
            "new_symbol": new_symbol,
            "old_close_price": close_price,
            "new_open_price": open_price,
            "spread_points": spread,
            "quantity": qty,
            "cost_ntd": cost_ntd,
        })

        if self._on_rollover_complete:
            self._on_rollover_complete(new_symbol)
