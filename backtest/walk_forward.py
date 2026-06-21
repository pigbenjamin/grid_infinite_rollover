"""
Walk-Forward 驗證框架

以滾動視窗驗證策略穩健性，防止過度擬合。
訓練視窗：6 個月 / 測試視窗：2 個月（可透過 config.yaml 調整）
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterator

import pandas as pd
import yaml

from backtest.engine import BacktestEngine


def run_walk_forward(tick_path: str, config_path: str = "config.yaml") -> list[dict]:
    """
    執行 Walk-Forward 驗證，回傳每個測試視窗的回測報告清單。
    """
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    train_months = cfg["backtest"]["walk_forward_train_months"]
    test_months = cfg["backtest"]["walk_forward_test_months"]

    ticks = pd.read_parquet(tick_path) if tick_path.endswith(".parquet") else pd.read_csv(tick_path)
    ticks["timestamp"] = pd.to_datetime(ticks["timestamp"])
    date_range = pd.date_range(ticks["timestamp"].min(), ticks["timestamp"].max(), freq="MS")

    results = []
    for i in range(0, len(date_range) - train_months - test_months + 1, test_months):
        train_start = date_range[i]
        train_end = date_range[i + train_months] - pd.Timedelta(days=1)
        test_start = date_range[i + train_months]
        test_end = date_range[min(i + train_months + test_months, len(date_range) - 1)]

        engine = BacktestEngine(config_path)
        report = engine.run(
            tick_path,
            test_start.strftime("%Y-%m-%d"),
            test_end.strftime("%Y-%m-%d"),
        )
        report["period"] = f"{test_start.date()} ~ {test_end.date()}"
        report["train_period"] = f"{train_start.date()} ~ {train_end.date()}"
        results.append(report)

    return results
