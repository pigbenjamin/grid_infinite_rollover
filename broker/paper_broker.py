"""
模擬實盤 Broker — PaperBroker

實作 AbstractBroker 介面，以虛擬帳戶在本地模擬撮合與保證金計算。
回測引擎與模擬實盤系統均使用此類別，不需連接任何真實券商 API。
"""
from __future__ import annotations

import uuid
from typing import Callable, Optional

import yaml

from broker.base import (
    AbstractBroker,
    InsufficientMarginError,
    OrderRejectedError,
)


class PaperBroker(AbstractBroker):
    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self._symbol = cfg["contract"]["symbol"]
        self._multiplier = cfg["contract"]["multiplier"]
        self._orig_margin = cfg["contract"]["original_margin"]
        self._maint_margin = cfg["contract"]["maintenance_margin"]
        self._initial_capital = cfg["account"]["initial_capital"]

        self._cash: float = self._initial_capital
        self._positions: list[dict] = []
        self._orders: dict[str, dict] = {}
        self._subscribers: dict[str, list[Callable]] = {}

    # ── 連線管理 ──────────────────────────────────────────────────────────────

    def login(self) -> None:
        pass

    def logout(self) -> None:
        pass

    # ── 市場資料 ──────────────────────────────────────────────────────────────

    def subscribe_market_data(self, symbol: str, callback: Callable[[dict], None]) -> None:
        self._subscribers.setdefault(symbol, []).append(callback)

    def unsubscribe_market_data(self, symbol: str) -> None:
        self._subscribers.pop(symbol, None)

    def push_tick(self, tick: dict) -> None:
        """回測引擎或模擬資料 Feed 呼叫此方法推送 Tick，觸發所有訂閱回調"""
        for cb in self._subscribers.get(tick["symbol"], []):
            cb(tick)

    # ── 帳戶與合約資訊 ────────────────────────────────────────────────────────

    def get_account_info(self) -> dict:
        return {"account_id": "PAPER-001", "broker_name": "PaperBroker", "currency": "TWD"}

    def get_margin_status(self) -> dict:
        qty = sum(p["quantity"] for p in self._positions)
        used_orig = qty * self._orig_margin
        used_maint = qty * self._maint_margin
        return {
            "daily_balance": self._cash,
            "original_margin": used_orig,
            "maint_margin": used_maint,
            "avail_margin": self._cash - used_orig,
            "unrealized_pnl": self._calc_unrealized_pnl(),
            "realized_pnl": 0.0,
            "total_equity": self._cash + self._calc_unrealized_pnl(),
        }

    def get_contract_spec(self, symbol: str) -> dict:
        return {
            "symbol": self._symbol,
            "multiplier": self._multiplier,
            "tick_size": 1.0,
            "original_margin": self._orig_margin,
            "maintenance_margin": self._maint_margin,
            "expiry_date": "",
        }

    # ── 持倉管理 ──────────────────────────────────────────────────────────────

    def get_positions(self) -> list[dict]:
        return list(self._positions)

    # ── 訂單管理 ──────────────────────────────────────────────────────────────

    def place_order(self, order_type: str, price: Optional[float],
                    quantity: int, direction: str) -> str:
        if order_type == "MARKET":
            self._fill_market_order(direction, quantity, price or 0.0)

        order_id = str(uuid.uuid4())
        self._orders[order_id] = {
            "order_id": order_id,
            "order_type": order_type,
            "price": price,
            "quantity": quantity,
            "direction": direction,
            "status": "FILLED" if order_type == "MARKET" else "PENDING",
            "filled_qty": quantity if order_type == "MARKET" else 0,
            "filled_price": price or 0.0,
        }
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order["status"] == "PENDING":
            order["status"] = "CANCELLED"
            return True
        return False

    def get_order_status(self, order_id: str) -> dict:
        return self._orders.get(order_id, {"status": "NOT_FOUND"})

    # ── 內部撮合邏輯 ──────────────────────────────────────────────────────────

    def try_fill_limit_orders(self, current_price: float) -> list[str]:
        """由回測引擎每 Tick 呼叫，嘗試撮合所有待成交限價單"""
        filled_ids = []
        for order_id, order in self._orders.items():
            if order["status"] != "PENDING":
                continue
            triggered = (
                (order["direction"] == "BUY" and current_price <= order["price"]) or
                (order["direction"] == "SELL" and current_price >= order["price"])
            )
            if triggered:
                self._fill_market_order(order["direction"], order["quantity"], order["price"])
                order["status"] = "FILLED"
                order["filled_qty"] = order["quantity"]
                order["filled_price"] = order["price"]
                filled_ids.append(order_id)
        return filled_ids

    def _fill_market_order(self, direction: str, quantity: int, price: float) -> None:
        if direction == "BUY":
            cost = quantity * self._orig_margin
            if self._cash < cost:
                raise InsufficientMarginError(f"保證金不足：需 {cost}，有 {self._cash}")
            if self._positions:
                existing = self._positions[0]
                total_qty = existing["quantity"] + quantity
                existing["avg_cost"] = (
                    (existing["avg_cost"] * existing["quantity"] + price * quantity) / total_qty
                )
                existing["quantity"] = total_qty
            else:
                self._positions.append({
                    "symbol": self._symbol,
                    "quantity": quantity,
                    "avg_cost": price,
                    "latest_price": price,
                })
        elif direction == "SELL":
            if not self._positions or self._positions[0]["quantity"] < quantity:
                raise OrderRejectedError("賣出口數超過現有持倉")
            pos = self._positions[0]
            realized = (price - pos["avg_cost"]) * quantity * self._multiplier
            self._cash += realized + quantity * self._orig_margin
            pos["quantity"] -= quantity
            if pos["quantity"] == 0:
                self._positions.clear()

    def _calc_unrealized_pnl(self) -> float:
        if not self._positions:
            return 0.0
        pos = self._positions[0]
        return (pos["latest_price"] - pos["avg_cost"]) * pos["quantity"] * self._multiplier

    def update_latest_price(self, price: float) -> None:
        """由 Feed 每 Tick 呼叫，更新持倉最新價"""
        if self._positions:
            self._positions[0]["latest_price"] = price
