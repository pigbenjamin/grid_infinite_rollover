import sqlite3
import threading
from pathlib import Path
from typing import Optional

_local = threading.local()


def get_connection(db_path: str) -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _open(db_path)
    return _local.conn


def _open(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(db_path: str, schema_sql_path: str = "db/schema.sql") -> None:
    conn = _open(db_path)
    sql = Path(schema_sql_path).read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.close()


def close_connection() -> None:
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None
