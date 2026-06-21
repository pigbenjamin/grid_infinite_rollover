"""
網格策略模組 — GridStrategy

負責：
- 依持倉口數計算當前加倉步長
- 計算下一個買入/賣出觸發價
- 盤中回跌攔截與 Cooldown 管理
- 最低持倉限制
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class GridConfig:
    min_position: int = 2
    max_position: int = 8
    tiers: list = field(default_factory=lambda: [(4, 1.0), (6, 2.0), (8, 4.0)])
    sell_step_pct: float = 2.0
    intraday_drop_pct: float = 2.0
    intraday_cooldown_min: int = 30


class GridStrategy:
    def __init__(self, cfg: GridConfig) -> None:
        self._cfg = cfg
        self._intraday_high: float = 0.0
        self._cooldown_until: Optional[datetime] = None
        self._last_buy_price: float = 0.0
        self._last_sell_price: float = 0.0

    def get_buy_step_pct(self, current_qty: int) -> Optional[float]:
        """依持倉口數取得加倉步長，None 表示暫停加倉"""
        if current_qty >= self._cfg.max_position:
            return None
        for qty_limit, step in self._cfg.tiers:
            if current_qty < qty_limit:
                return step
        return None

    def next_buy_price(self, reference_price: float, current_qty: int) -> Optional[float]:
        """計算下一個加倉觸發價"""
        step = self.get_buy_step_pct(current_qty)
        if step is None:
            return None
        return round(reference_price * (1 - step / 100), 0)

    def next_sell_price(self, reference_price: float, current_qty: int) -> Optional[float]:
        """計算下一個減倉觸發價"""
        if current_qty <= self._cfg.min_position:
            return None
        return round(reference_price * (1 + self._cfg.sell_step_pct / 100), 0)

    def update_intraday_high(self, price: float) -> None:
        if price > self._intraday_high:
            self._intraday_high = price

    def reset_intraday_high(self) -> None:
        """每日盤前呼叫，重置當日高點"""
        self._intraday_high = 0.0

    def should_intercept_intraday(self, current_price: float, now: datetime) -> bool:
        """盤中回跌攔截：自高點跌 N%，且不在 Cooldown 期間"""
        if self._cooldown_until and now < self._cooldown_until:
            return False
        if self._intraday_high <= 0:
            return False
        drop_pct = (self._intraday_high - current_price) / self._intraday_high * 100
        return drop_pct >= self._cfg.intraday_drop_pct

    def trigger_intercept_cooldown(self, now: datetime) -> None:
        self._cooldown_until = now + timedelta(minutes=self._cfg.intraday_cooldown_min)

    def is_in_cooldown(self, now: datetime) -> bool:
        return self._cooldown_until is not None and now < self._cooldown_until
