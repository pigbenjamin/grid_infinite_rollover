"""
資料庫操作方法（CRUD）
所有寫入均透過此模組，不允許其他模組直接執行 SQL。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from db.connection import get_connection


# ── Margin Status ────────────────────────────────────────────────────────────

def upsert_margin_status(db_path: str, data: dict) -> None:
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO margin_status
           (daily_balance, original_margin, maint_margin, avail_margin,
            unrealized_pnl, realized_pnl, total_equity, real_leverage, leverage_level)
           VALUES (:daily_balance, :original_margin, :maint_margin, :avail_margin,
                   :unrealized_pnl, :realized_pnl, :total_equity, :real_leverage, :leverage_level)""",
        data,
    )
    conn.commit()


def get_latest_margin_status(db_path: str) -> Optional[dict]:
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM margin_status ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


# ── Positions ────────────────────────────────────────────────────────────────

def upsert_position(db_path: str, data: dict) -> None:
    conn = get_connection(db_path)
    conn.execute("DELETE FROM position_details")
    conn.execute(
        """INSERT INTO position_details
           (symbol, quantity, avg_cost, latest_price, unrealized_pnl)
           VALUES (:symbol, :quantity, :avg_cost, :latest_price, :unrealized_pnl)""",
        data,
    )
    conn.commit()


def get_position(db_path: str) -> Optional[dict]:
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM position_details ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


# ── Open Orders ──────────────────────────────────────────────────────────────

def insert_open_order(db_path: str, order_id: str, symbol: str,
                      price: float, quantity: int, direction: str) -> None:
    conn = get_connection(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO open_orders (order_id, symbol, price, quantity, direction)
           VALUES (?, ?, ?, ?, ?)""",
        (order_id, symbol, price, quantity, direction),
    )
    conn.commit()


def delete_open_order(db_path: str, order_id: str) -> None:
    conn = get_connection(db_path)
    conn.execute("DELETE FROM open_orders WHERE order_id = ?", (order_id,))
    conn.commit()


def get_all_open_orders(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM open_orders ORDER BY price").fetchall()
    return [dict(r) for r in rows]


# ── Pending Orders（冪等機制）───────────────────────────────────────────────

def create_pending_order(db_path: str, symbol: str, price: Optional[float],
                         quantity: int, direction: str, order_type: str) -> str:
    local_id = str(uuid.uuid4())
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO pending_orders
           (local_order_id, symbol, price, quantity, direction, order_type, status)
           VALUES (?, ?, ?, ?, ?, ?, 'PENDING')""",
        (local_id, symbol, price, quantity, direction, order_type),
    )
    conn.commit()
    return local_id


def confirm_pending_order(db_path: str, local_order_id: str, broker_order_id: str) -> None:
    conn = get_connection(db_path)
    conn.execute(
        """UPDATE pending_orders SET broker_order_id=?, status='CONFIRMED',
           updated_at=datetime('now','localtime') WHERE local_order_id=?""",
        (broker_order_id, local_order_id),
    )
    conn.commit()


def get_unconfirmed_orders(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM pending_orders WHERE status='PENDING'"
    ).fetchall()
    return [dict(r) for r in rows]


# ── Rollover Log ─────────────────────────────────────────────────────────────

def insert_rollover_log(db_path: str, data: dict) -> None:
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO rollover_log
           (old_symbol, new_symbol, old_close_price, new_open_price,
            spread_points, quantity, cost_ntd)
           VALUES (:old_symbol, :new_symbol, :old_close_price, :new_open_price,
                   :spread_points, :quantity, :cost_ntd)""",
        data,
    )
    conn.commit()


# ── Snapshots ────────────────────────────────────────────────────────────────

def insert_snapshot(db_path: str, total_equity: float, position_qty: int,
                    real_leverage: float, system_state: str) -> None:
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO snapshots (total_equity, position_qty, real_leverage, system_state)
           VALUES (?, ?, ?, ?)""",
        (total_equity, position_qty, real_leverage, system_state),
    )
    conn.commit()


def get_latest_snapshot(db_path: str) -> Optional[dict]:
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM snapshots ORDER BY snapshot_at DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


# ── System Logs ──────────────────────────────────────────────────────────────

def insert_log(db_path: str, level: str, module: str, message: str) -> None:
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO system_logs (level, module, message) VALUES (?, ?, ?)",
        (level, module, message),
    )
    conn.commit()


def get_recent_logs(db_path: str, limit: int = 50) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM system_logs ORDER BY logged_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
