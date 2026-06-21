"""
狀態比對與修復 — Reconciler

模擬斷線重連後，自動比對本地 DB 狀態與券商（或 PaperBroker）的實際狀態，
差異時記錄日誌並觸發警報。
"""
from __future__ import annotations

import logging

from broker.base import AbstractBroker
from db import models
from notification.notifier import AlertLevel, Notifier

logger = logging.getLogger(__name__)


class Reconciler:
    def __init__(self, broker: AbstractBroker, db_path: str, notifier: Notifier) -> None:
        self._broker = broker
        self._db_path = db_path
        self._notifier = notifier

    def reconcile_positions(self) -> bool:
        """
        比對持倉口數是否一致。
        一致回傳 True，不一致回傳 False 並觸發 CRITICAL 警報。
        """
        local = models.get_position(self._db_path)
        broker_positions = self._broker.get_positions()
        broker_qty = sum(p["quantity"] for p in broker_positions)
        local_qty = local["quantity"] if local else 0

        if local_qty != broker_qty:
            msg = f"持倉不一致：本地={local_qty}，券商={broker_qty}"
            logger.critical(msg)
            self._notifier.send(AlertLevel.CRITICAL, "Reconciler", msg)
            return False

        logger.info("持倉核對通過：%d 口", local_qty)
        return True

    def reconcile_pending_orders(self) -> None:
        """
        掃描所有 PENDING 訂單，向券商查詢實際狀態後補全。
        """
        unconfirmed = models.get_unconfirmed_orders(self._db_path)
        for order in unconfirmed:
            broker_id = order.get("broker_order_id")
            if not broker_id:
                continue
            try:
                status = self._broker.get_order_status(broker_id)
                if status.get("status") in ("FILLED", "CANCELLED", "REJECTED"):
                    models.confirm_pending_order(
                        self._db_path, order["local_order_id"], broker_id
                    )
                    logger.info("補全訂單 %s 狀態：%s", broker_id, status["status"])
            except Exception as e:
                logger.warning("查詢訂單 %s 失敗：%s", broker_id, e)
