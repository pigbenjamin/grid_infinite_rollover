"""
選擇權避險模組 — OptionsHedger

觸發條件（三項同時成立）：
1. 持倉口數 ≥ max_position
2. 均價虧損幅度 ≥ trigger_loss_pct
3. 距上次賣出減倉 ≥ days_since_last_sell 個交易日

合成策略：SC（Sell Call）+ BP（Buy Put）Collar 結構
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class OptionsHedgeConfig:
    max_position: int = 8
    trigger_loss_pct: float = 5.0
    days_since_last_sell: int = 3
    sc_delta_target: float = -0.28
    bp_cost_ratio: float = 0.30
    option_dte_min: int = 14
    option_dte_max: int = 21


class OptionsHedger:
    def __init__(self, cfg: OptionsHedgeConfig) -> None:
        self._cfg = cfg

    def should_hedge(self, position_qty: int, avg_cost: float,
                     current_price: float, days_no_sell: int) -> bool:
        """判斷是否符合觸發條件"""
        if position_qty < self._cfg.max_position:
            return False
        if avg_cost <= 0:
            return False
        loss_pct = (avg_cost - current_price) / avg_cost * 100
        if loss_pct < self._cfg.trigger_loss_pct:
            return False
        if days_no_sell < self._cfg.days_since_last_sell:
            return False
        return True

    def suggest_sc_strike(self, current_price: float, step_up_pct: float = 2.5) -> float:
        """建議 SC 履約價（簡化：現價 × (1 + step)，對應 Delta ≈ -0.28）"""
        return round(current_price * (1 + step_up_pct / 100) / 50) * 50

    def suggest_bp_strike(self, current_price: float, step_down_pct: float = 5.0) -> float:
        """建議 BP 履約價（現價 × (1 - step)，深度價外）"""
        return round(current_price * (1 - step_down_pct / 100) / 50) * 50

    def is_valid_dte(self, dte_calendar_days: int) -> bool:
        return self._cfg.option_dte_min <= dte_calendar_days <= self._cfg.option_dte_max
