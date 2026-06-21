"""
交易核心引擎 — TradingEngine

主引擎：整合網格策略、風控、換倉、避險模組，
透過 AbstractBroker 的事件驅動回調執行所有交易邏輯。

系統狀態機：
  INIT → RUNNING ↔ PAUSED → ROLLOVER → RUNNING
                          ↘ EMERGENCY（人工介入解除）
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Optional

import yaml

from broker.base import AbstractBroker
from core.grid_strategy import GridConfig, GridStrategy
from core.options_hedger import OptionsHedgeConfig, OptionsHedger
from core.risk_manager import LeverageLevel, RiskConfig, RiskManager
from core.rollover import RolloverManager
from db import models
from db.connection import init_schema
from notification.notifier import AlertLevel, Notifier

logger = logging.getLogger(__name__)


class SystemState(str, Enum):
    INIT = "INIT"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ROLLOVER = "ROLLOVER"
    EMERGENCY = "EMERGENCY"


class TradingEngine:
    def __init__(self, broker: AbstractBroker, config_path: str = "config.yaml") -> None:
        with open(config_path, encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f)

        self._broker = broker
        self._db_path = self._cfg["data"]["db_path"]
        self._symbol = self._cfg["contract"]["symbol"]
        self._multiplier = self._cfg["contract"]["multiplier"]
        self._state = SystemState.INIT

        grid_cfg = GridConfig(
            min_position=self._cfg["grid"]["min_position"],
            max_position=self._cfg["grid"]["max_position"],
            tiers=[tuple(t) for t in self._cfg["grid"]["tiers"]],
            sell_step_pct=self._cfg["grid"]["sell_step_pct"],
            intraday_drop_pct=self._cfg["grid"]["intraday_drop_pct"],
            intraday_cooldown_min=self._cfg["grid"]["intraday_cooldown_min"],
        )
        self._grid = GridStrategy(grid_cfg)

        risk_cfg = RiskConfig(
            leverage_warn=self._cfg["risk"]["leverage_warn"],
            leverage_reduce=self._cfg["risk"]["leverage_reduce"],
            leverage_critical=self._cfg["risk"]["leverage_critical"],
            min_position=self._cfg["grid"]["min_position"],
        )
        self._risk = RiskManager(risk_cfg)

        hedge_cfg = OptionsHedgeConfig(
            max_position=self._cfg["grid"]["max_position"],
            trigger_loss_pct=self._cfg["options_hedge"]["trigger_loss_pct"],
            days_since_last_sell=self._cfg["options_hedge"]["days_since_last_sell"],
        )
        self._hedger = OptionsHedger(hedge_cfg)

        self._rollover_mgr = RolloverManager(
            broker=broker,
            db_path=self._db_path,
            multiplier=self._multiplier,
            dte_threshold=self._cfg["rollover"]["dte_threshold"],
        )
        self._rollover_mgr.set_callbacks(
            on_complete=self._on_rollover_complete,
            on_failed=self._on_rollover_failed,
        )

        self._notifier = Notifier(self._cfg.get("notification", {}))
        self._snapshot_interval = self._cfg["dashboard"]["snapshot_interval_sec"]
        self._snapshot_thread: Optional[threading.Thread] = None
        self._days_no_sell: int = 0

    def start(self) -> None:
        init_schema(self._db_path)
        self._recover_state()
        self._broker.login()
        self._broker.subscribe_market_data(self._symbol, self._on_tick)
        self._state = SystemState.RUNNING
        self._snapshot_thread = threading.Thread(target=self._snapshot_loop, daemon=True)
        self._snapshot_thread.start()
        self._notifier.send(AlertLevel.INFO, "TradingEngine", "交易系統啟動完成")
        logger.info("TradingEngine started, state=RUNNING")

    def stop(self) -> None:
        self._state = SystemState.PAUSED
        self._broker.unsubscribe_market_data(self._symbol)
        self._broker.logout()
        self._notifier.send(AlertLevel.INFO, "TradingEngine", "交易系統正常關閉")
        logger.info("TradingEngine stopped")

    def emergency_stop(self) -> None:
        self._state = SystemState.EMERGENCY
        self._cancel_all_orders()
        self._notifier.send(AlertLevel.CRITICAL, "TradingEngine", "緊急停止已觸發，所有掛單已撤銷")
        logger.critical("Emergency stop triggered")

    def resume(self) -> None:
        if self._state != SystemState.EMERGENCY:
            return
        self._state = SystemState.RUNNING
        self._notifier.send(AlertLevel.INFO, "TradingEngine", "系統已人工確認恢復運作")

    # ── 事件驅動入口（每 Tick 呼叫）─────────────────────────────────────────

    def _on_tick(self, tick: dict) -> None:
        if self._state != SystemState.RUNNING:
            return

        price = tick["price"]
        now = datetime.now()

        self._grid.update_intraday_high(price)
        self._update_db(price)
        self._check_risk(price)

        if self._state != SystemState.RUNNING:
            return

        positions = self._broker.get_positions()
        qty = sum(p["quantity"] for p in positions)

        self._check_grid_sell(price, qty)
        self._check_grid_buy(price, qty, now)
        self._check_options_hedge(price, qty, positions)

    # ── 網格邏輯 ──────────────────────────────────────────────────────────────

    def _check_grid_buy(self, price: float, qty: int, now: datetime) -> None:
        if qty >= self._cfg["grid"]["max_position"]:
            return

        next_buy = self._grid.next_buy_price(price, qty)
        if next_buy and price <= next_buy:
            self._place_buy(1, price)

        if self._grid.should_intercept_intraday(price, now):
            self._place_buy(1, price)
            self._grid.trigger_intercept_cooldown(now)

    def _check_grid_sell(self, price: float, qty: int) -> None:
        if qty <= self._cfg["grid"]["min_position"]:
            return
        next_sell = self._grid.next_sell_price(price, qty)
        if next_sell and price >= next_sell:
            self._place_sell(1, price)
            self._days_no_sell = 0

    def _place_buy(self, qty: int, price: float) -> None:
        local_id = models.create_pending_order(
            self._db_path, self._symbol, price, qty, "BUY", "MARKET"
        )
        broker_id = self._broker.place_order("MARKET", None, qty, "BUY")
        models.confirm_pending_order(self._db_path, local_id, broker_id)
        logger.info("BUY %d @ %s  order=%s", qty, price, broker_id)

    def _place_sell(self, qty: int, price: float) -> None:
        local_id = models.create_pending_order(
            self._db_path, self._symbol, price, qty, "SELL", "MARKET"
        )
        broker_id = self._broker.place_order("MARKET", None, qty, "SELL")
        models.confirm_pending_order(self._db_path, local_id, broker_id)
        logger.info("SELL %d @ %s  order=%s", qty, price, broker_id)

    # ── 風控 ──────────────────────────────────────────────────────────────────

    def _check_risk(self, price: float) -> None:
        margin = self._broker.get_margin_status()
        spec = self._broker.get_contract_spec(self._symbol)
        positions = self._broker.get_positions()
        qty = sum(p["quantity"] for p in positions)

        contract_value = price * spec["multiplier"]
        leverage = self._risk.calc_leverage(qty, contract_value, margin["total_equity"])
        level = self._risk.assess(leverage)

        if level == LeverageLevel.CRITICAL:
            reduce_qty = self._risk.calc_reduce_qty(qty, level)
            if reduce_qty > 0:
                self._place_sell(reduce_qty, price)
            self._notifier.send(AlertLevel.CRITICAL, "RiskManager",
                                f"槓桿 {leverage:.2f}x，已觸發最大風控減倉")
            self._state = SystemState.PAUSED

        elif level == LeverageLevel.REDUCE:
            reduce_qty = self._risk.calc_reduce_qty(qty, level)
            if reduce_qty > 0:
                self._place_sell(reduce_qty, price)
            self._notifier.send(AlertLevel.WARNING, "RiskManager",
                                f"槓桿 {leverage:.2f}x，已自動減倉 25%")

        elif level == LeverageLevel.WARN:
            self._notifier.send(AlertLevel.WARNING, "RiskManager",
                                f"槓桿 {leverage:.2f}x，暫停加倉")

    # ── 選擇權避險 ────────────────────────────────────────────────────────────

    def _check_options_hedge(self, price: float, qty: int, positions: list) -> None:
        if not positions:
            return
        avg_cost = positions[0].get("avg_cost", price)
        if self._hedger.should_hedge(qty, avg_cost, price, self._days_no_sell):
            sc = self._hedger.suggest_sc_strike(price)
            bp = self._hedger.suggest_bp_strike(price)
            self._notifier.send(
                AlertLevel.WARNING, "OptionsHedger",
                f"建議啟動 Collar 避險：SC@{sc} + BP@{bp}（需人工確認）"
            )

    # ── 換倉回調 ──────────────────────────────────────────────────────────────

    def _on_rollover_complete(self, new_symbol: str) -> None:
        self._symbol = new_symbol
        self._state = SystemState.RUNNING
        self._notifier.send(AlertLevel.INFO, "Rollover", f"換倉完成，新合約：{new_symbol}")

    def _on_rollover_failed(self, reason: str) -> None:
        self._state = SystemState.EMERGENCY
        self._notifier.send(AlertLevel.CRITICAL, "Rollover", f"換倉失敗：{reason}")

    # ── 崩潰恢復 ──────────────────────────────────────────────────────────────

    def _recover_state(self) -> None:
        unconfirmed = models.get_unconfirmed_orders(self._db_path)
        for order in unconfirmed:
            try:
                status = self._broker.get_order_status(order["broker_order_id"] or "")
                if status.get("status") in ("FILLED", "CANCELLED", "REJECTED"):
                    models.confirm_pending_order(
                        self._db_path, order["local_order_id"],
                        order.get("broker_order_id", "")
                    )
            except Exception:
                pass

        local_pos = models.get_position(self._db_path)
        broker_positions = self._broker.get_positions()
        broker_qty = sum(p["quantity"] for p in broker_positions)
        local_qty = local_pos["quantity"] if local_pos else 0

        if local_qty != broker_qty:
            self._state = SystemState.EMERGENCY
            self._notifier.send(
                AlertLevel.CRITICAL, "Recovery",
                f"持倉不一致：本地={local_qty}，券商={broker_qty}，請人工確認"
            )

    # ── 資料庫更新 ────────────────────────────────────────────────────────────

    def _update_db(self, price: float) -> None:
        margin = self._broker.get_margin_status()
        positions = self._broker.get_positions()
        qty = sum(p["quantity"] for p in positions)
        spec = self._broker.get_contract_spec(self._symbol)

        leverage = self._risk.calc_leverage(qty, price * spec["multiplier"], margin["total_equity"])
        level = self._risk.assess(leverage)

        models.upsert_margin_status(self._db_path, {
            **margin,
            "real_leverage": leverage,
            "leverage_level": level.value,
        })

        if positions:
            p = positions[0]
            pnl = (p["latest_price"] - p["avg_cost"]) * p["quantity"] * self._multiplier
            models.upsert_position(self._db_path, {
                "symbol": self._symbol,
                "quantity": p["quantity"],
                "avg_cost": p["avg_cost"],
                "latest_price": price,
                "unrealized_pnl": pnl,
            })

    def _cancel_all_orders(self) -> None:
        for order in models.get_all_open_orders(self._db_path):
            try:
                self._broker.cancel_order(order["order_id"])
                models.delete_open_order(self._db_path, order["order_id"])
            except Exception:
                pass

    def _snapshot_loop(self) -> None:
        while self._state not in (SystemState.INIT,):
            try:
                margin = self._broker.get_margin_status()
                positions = self._broker.get_positions()
                qty = sum(p["quantity"] for p in positions)
                spec = self._broker.get_contract_spec(self._symbol)
                price = positions[0]["latest_price"] if positions else 0.0
                leverage = self._risk.calc_leverage(
                    qty, price * spec["multiplier"], margin["total_equity"]
                )
                models.insert_snapshot(
                    self._db_path, margin["total_equity"], qty, leverage, self._state.value
                )
            except Exception:
                pass
            time.sleep(self._snapshot_interval)
