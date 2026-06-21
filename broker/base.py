"""
API 抽象層 — AbstractBroker 介面 + 統一 Exception 階層

核心策略邏輯只能呼叫 AbstractBroker 定義的方法，
不得直接呼叫任何券商 SDK，以確保可無縫切換券商。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional


# ── Exception 階層 ────────────────────────────────────────────────────────────

class BrokerError(Exception):
    """所有券商相關錯誤的基底類別"""

class BrokerConnectionError(BrokerError):
    """連線建立失敗或連線中斷"""

class OrderRejectedError(BrokerError):
    """委託單被拒絕（保證金不足以外的原因）"""

class InsufficientMarginError(BrokerError):
    """保證金不足，委託單被拒絕"""

class ContractExpiredError(BrokerError):
    """合約已到期，無法繼續操作"""


# ── 資料結構（TypedDict 替代品，純 dict 操作）────────────────────────────────
# 各方法回傳的 dict 欄位規範：
#
# get_account_info() -> {
#     "account_id": str, "broker_name": str, "currency": str
# }
#
# get_margin_status() -> {
#     "daily_balance": float, "original_margin": float, "maint_margin": float,
#     "avail_margin": float, "unrealized_pnl": float, "realized_pnl": float,
#     "total_equity": float
# }
#
# get_contract_spec(symbol) -> {
#     "symbol": str, "multiplier": int, "tick_size": float,
#     "original_margin": float, "maintenance_margin": float,
#     "expiry_date": str  # "YYYY-MM-DD"
# }
#
# get_positions() -> list of {
#     "symbol": str, "quantity": int, "avg_cost": float, "latest_price": float
# }
#
# place_order() -> str  (broker_order_id)
#
# get_order_status(order_id) -> {
#     "order_id": str, "status": str,  # PENDING/FILLED/CANCELLED/REJECTED
#     "filled_qty": int, "filled_price": float
# }


class AbstractBroker(ABC):

    # ── 連線管理 ──────────────────────────────────────────────────────────────

    @abstractmethod
    def login(self) -> None:
        """建立與券商的連線並完成身份驗證"""

    @abstractmethod
    def logout(self) -> None:
        """正常斷開連線"""

    # ── 市場資料（事件驅動，非輪詢）──────────────────────────────────────────

    @abstractmethod
    def subscribe_market_data(self, symbol: str, callback: Callable[[dict], None]) -> None:
        """
        訂閱指定合約的即時 Tick 資料。
        每筆新 Tick 到達時呼叫 callback(tick)，
        tick = {"symbol": str, "price": float, "volume": int, "timestamp": str}
        """

    @abstractmethod
    def unsubscribe_market_data(self, symbol: str) -> None:
        """取消訂閱"""

    # ── 帳戶與合約資訊 ────────────────────────────────────────────────────────

    @abstractmethod
    def get_account_info(self) -> dict:
        """取得帳戶基本資訊"""

    @abstractmethod
    def get_margin_status(self) -> dict:
        """取得目前保證金狀態（即時）"""

    @abstractmethod
    def get_contract_spec(self, symbol: str) -> dict:
        """取得合約規格：乘數、跳動單位、保證金比率、到期日"""

    # ── 持倉管理 ──────────────────────────────────────────────────────────────

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """取得當前所有持倉"""

    # ── 訂單管理 ──────────────────────────────────────────────────────────────

    @abstractmethod
    def place_order(self, order_type: str, price: Optional[float],
                    quantity: int, direction: str) -> str:
        """
        送出委託單，回傳券商訂單號。
        order_type: "LIMIT" | "MARKET"
        direction:  "BUY" | "SELL"
        price:      限價單填入點數，市價單傳 None
        """

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤銷委託單，成功回傳 True"""

    @abstractmethod
    def get_order_status(self, order_id: str) -> dict:
        """查詢單一委託單的最新狀態"""
