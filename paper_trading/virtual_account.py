"""
虛擬帳戶管理 — VirtualAccount

負責在本地資料庫中維護完整的虛擬帳戶狀態：
保證金計算、盈虧更新、強平檢核。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VirtualAccount:
    initial_capital: float
    multiplier: int
    original_margin: float
    maintenance_margin: float

    _cash: float = field(init=False)
    _positions: list[dict] = field(default_factory=list, init=False)
    _realized_pnl: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self._cash = self.initial_capital

    @property
    def total_equity(self) -> float:
        return self._cash + self.unrealized_pnl

    @property
    def unrealized_pnl(self) -> float:
        if not self._positions:
            return 0.0
        p = self._positions[0]
        return (p["latest_price"] - p["avg_cost"]) * p["quantity"] * self.multiplier

    @property
    def used_original_margin(self) -> float:
        qty = self._positions[0]["quantity"] if self._positions else 0
        return qty * self.original_margin

    @property
    def used_maint_margin(self) -> float:
        qty = self._positions[0]["quantity"] if self._positions else 0
        return qty * self.maintenance_margin

    @property
    def avail_margin(self) -> float:
        return self._cash - self.used_original_margin

    def get_position_qty(self) -> int:
        return self._positions[0]["quantity"] if self._positions else 0

    def get_avg_cost(self) -> float:
        return self._positions[0]["avg_cost"] if self._positions else 0.0

    def update_price(self, price: float) -> None:
        if self._positions:
            self._positions[0]["latest_price"] = price

    def buy(self, qty: int, price: float) -> None:
        if self.avail_margin < qty * self.original_margin:
            raise ValueError(f"保證金不足：可用 {self.avail_margin:.0f}")
        if self._positions:
            pos = self._positions[0]
            total = pos["quantity"] + qty
            pos["avg_cost"] = (pos["avg_cost"] * pos["quantity"] + price * qty) / total
            pos["quantity"] = total
            pos["latest_price"] = price
        else:
            self._positions = [{"quantity": qty, "avg_cost": price, "latest_price": price}]

    def sell(self, qty: int, price: float) -> float:
        if not self._positions or self._positions[0]["quantity"] < qty:
            raise ValueError("賣出口數超過持倉")
        pos = self._positions[0]
        realized = (price - pos["avg_cost"]) * qty * self.multiplier
        self._cash += realized + qty * self.original_margin
        self._realized_pnl += realized
        pos["quantity"] -= qty
        if pos["quantity"] == 0:
            self._positions.clear()
        return realized

    def is_margin_call(self) -> bool:
        """判斷是否低於維持保證金（模擬強平條件）"""
        return self.total_equity < self.used_maint_margin

    def to_status_dict(self) -> dict:
        return {
            "daily_balance": self._cash,
            "original_margin": self.used_original_margin,
            "maint_margin": self.used_maint_margin,
            "avail_margin": self.avail_margin,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self._realized_pnl,
            "total_equity": self.total_equity,
        }
