"""
交易成本模型 — CostModel

計算每筆交易的手續費、期交稅、滑價成本（元）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostConfig:
    slippage_points: float = 1.0    # 每筆滑價點數
    commission_per_lot: float = 50.0 # 每口手續費（元）
    futures_tax_rate: float = 0.00002 # 期交稅率


class CostModel:
    def __init__(self, cfg: CostConfig, multiplier: int) -> None:
        self._cfg = cfg
        self._multiplier = multiplier

    def total_cost(self, trade_price: float, quantity: int) -> float:
        """回傳單筆交易的總成本（元）"""
        slippage = self._cfg.slippage_points * self._multiplier * quantity
        commission = self._cfg.commission_per_lot * quantity
        tax = trade_price * self._multiplier * quantity * self._cfg.futures_tax_rate
        return slippage + commission + tax

    def adjusted_buy_price(self, price: float) -> float:
        """買入實際成本價（含滑價）"""
        return price + self._cfg.slippage_points

    def adjusted_sell_price(self, price: float) -> float:
        """賣出實際成交價（含滑價）"""
        return price - self._cfg.slippage_points
