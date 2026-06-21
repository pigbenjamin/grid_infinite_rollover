"""
風控模組 — RiskManager

負責：
- 計算真實槓桿
- 依三級閥值觸發對應動作
- 耐震度驗算輔助工具
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LeverageLevel(str, Enum):
    SAFE = "SAFE"
    WARN = "WARN"         # > warn_threshold：暫停加倉
    REDUCE = "REDUCE"     # > reduce_threshold：自動減倉 25%
    CRITICAL = "CRITICAL" # > critical_threshold：最大風控減倉


@dataclass
class RiskConfig:
    leverage_warn: float = 5.0
    leverage_reduce: float = 7.0
    leverage_critical: float = 9.0
    min_position: int = 2


class RiskManager:
    def __init__(self, cfg: RiskConfig) -> None:
        self._cfg = cfg

    def calc_leverage(self, position_qty: int, contract_value_per_lot: float,
                      total_equity: float) -> float:
        if total_equity <= 0:
            return float("inf")
        return (position_qty * contract_value_per_lot) / total_equity

    def assess(self, leverage: float) -> LeverageLevel:
        if leverage > self._cfg.leverage_critical:
            return LeverageLevel.CRITICAL
        if leverage > self._cfg.leverage_reduce:
            return LeverageLevel.REDUCE
        if leverage > self._cfg.leverage_warn:
            return LeverageLevel.WARN
        return LeverageLevel.SAFE

    def calc_reduce_qty(self, current_qty: int, level: LeverageLevel) -> int:
        """回傳應減倉的口數"""
        if level == LeverageLevel.REDUCE:
            return max(1, current_qty // 4)
        if level == LeverageLevel.CRITICAL:
            return max(0, current_qty - self._cfg.min_position)
        return 0

    @staticmethod
    def min_equity_for_drawdown(max_qty: int, contract_value: float,
                                drawdown_pct: float, maint_margin: float) -> float:
        """
        計算滿倉時承受指定跌幅不被強平所需的最低帳戶淨值。
        公式：max_qty × contract_value × drawdown_pct + max_qty × maint_margin
        """
        return max_qty * contract_value * drawdown_pct + max_qty * maint_margin
