"""
儀表板後端伺服器 — FastAPI + WebSocket

提供：
- REST API（控制面板指令：緊急停止、恢復、手動換倉）
- WebSocket 端點（推送即時狀態至前端）
- 靜態檔案服務（frontend/）
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import models

logger = logging.getLogger(__name__)

app = FastAPI(title="GridBot Dashboard")

_config: dict = {}
_db_path: str = ""
_ws_clients: list[WebSocket] = []
_engine_ref = None  # 由 main.py 注入 TradingEngine 實例


def init(config_path: str = "config.yaml", engine=None) -> None:
    global _config, _db_path, _engine_ref
    with open(config_path, encoding="utf-8") as f:
        _config = yaml.safe_load(f)
    _db_path = _config["data"]["db_path"]
    _engine_ref = engine


# ── 靜態前端 ──────────────────────────────────────────────────────────────────

frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/")
def index():
    return FileResponse(str(frontend_dir / "index.html"))


# ── REST API（控制面板） ────────────────────────────────────────────────────────

@app.post("/api/emergency_stop")
def emergency_stop():
    if _engine_ref:
        _engine_ref.emergency_stop()
    return {"status": "ok", "action": "emergency_stop"}


@app.post("/api/resume")
def resume():
    if _engine_ref:
        _engine_ref.resume()
    return {"status": "ok", "action": "resume"}


@app.get("/api/logs")
def get_logs(limit: int = 50):
    return models.get_recent_logs(_db_path, limit)


@app.get("/api/margin")
def get_margin():
    return models.get_latest_margin_status(_db_path)


@app.get("/api/position")
def get_position():
    return models.get_position(_db_path)


@app.get("/api/orders")
def get_orders():
    return models.get_all_open_orders(_db_path)


# ── WebSocket（即時推送） ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        _ws_clients.remove(ws)


async def broadcast(data: dict) -> None:
    """由交易核心每 Tick 後呼叫，推送最新狀態至所有連線中的前端"""
    msg = json.dumps(data, ensure_ascii=False)
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)
