"""
回測引擎 — BacktestEngine

時序回放歷史 Tick，驅動 PaperBroker 撮合，記錄每日淨值曲線。
所有訊號僅能使用當下已完成 Tick，嚴格禁止前視偏差。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import yaml

from backtest.cost_model import CostConfig, CostModel
from backtest.data_loader import (
    iter_ticks, load_rollover_spread, load_tick, load_trading_calendar,
)
from backtest.reporter import BacktestReporter
from broker.paper_broker import PaperBroker
from core.engine import TradingEngine

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path, encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f)

        self._broker = PaperBroker(config_path)
        self._engine = TradingEngine(self._broker, config_path)

        cost_cfg = CostConfig(
            slippage_points=self._cfg["backtest"]["slippage_points"],
            commission_per_lot=self._cfg["backtest"]["commission_per_lot"],
            futures_tax_rate=self._cfg["backtest"]["futures_tax_rate"],
        )
        self._cost_model = CostModel(cost_cfg, self._cfg["contract"]["multiplier"])

        self._spread_df: Optional[pd.DataFrame] = None
        self._calendar: Optional[set] = None
        self._equity_curve: list[dict] = []

    def run(self, tick_path: str, start_date: str, end_date: str) -> dict:
        spread_path = self._cfg["data"]["rollover_spread_csv"]
        calendar_path = self._cfg["data"]["trading_calendar_csv"]

        self._spread_df = load_rollover_spread(spread_path)
        self._calendar = load_trading_calendar(calendar_path)

        ticks = load_tick(tick_path)
        ticks = ticks[
            (ticks["timestamp"] >= start_date) & (ticks["timestamp"] <= end_date)
        ]

        self._engine.start()
        current_date = None

        for tick in iter_ticks(ticks):
            ts = pd.Timestamp(tick["timestamp"])
            date_str = ts.strftime("%Y-%m-%d")

            if date_str not in self._calendar:
                continue

            if date_str != current_date:
                if current_date:
                    self._record_daily_equity(current_date)
                current_date = date_str
                self._engine._grid.reset_intraday_high()
                self._check_rollover(date_str)

            self._broker.update_latest_price(tick["price"])
            self._broker.push_tick(tick)

        if current_date:
            self._record_daily_equity(current_date)

        self._engine.stop()

        reporter = BacktestReporter(self._equity_curve, self._cfg["contract"]["multiplier"])
        return reporter.generate()

    def _check_rollover(self, date_str: str) -> None:
        if self._spread_df is None:
            return
        row = self._spread_df[self._spread_df["date"] == date_str]
        if row.empty:
            return
        dte = int(row.iloc[0].get("dte", 99))
        if dte <= self._cfg["rollover"]["dte_threshold"]:
            old_sym = row.iloc[0]["contract_sold"]
            new_sym = row.iloc[0]["contract_bought"]
            logger.info("換倉觸發：%s → %s（DTE=%d）", old_sym, new_sym, dte)
            self._engine._rollover_mgr.check_and_rollover(old_sym, new_sym, dte)

    def _record_daily_equity(self, date_str: str) -> None:
        margin = self._broker.get_margin_status()
        positions = self._broker.get_positions()
        qty = sum(p["quantity"] for p in positions)
        self._equity_curve.append({
            "date": date_str,
            "equity": margin["total_equity"],
            "position_qty": qty,
            "leverage": margin["total_equity"],
        })
