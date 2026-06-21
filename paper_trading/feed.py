"""
市場資料流 — MarketFeed

支援兩種模式：
1. 即時模式：接收外部即時 Tick（由真實 Broker 驅動）
2. 模擬模式：從歷史 Parquet 檔回放，可設定延遲秒數模擬延遲資料流
"""
from __future__ import annotations

import time
from typing import Callable

import pandas as pd


class SimulatedFeed:
    """以歷史 Tick 模擬即時資料流（用於模擬實盤測試）"""

    def __init__(self, tick_path: str, delay_sec: float = 0.01) -> None:
        if tick_path.endswith(".parquet"):
            self._df = pd.read_parquet(tick_path)
        else:
            self._df = pd.read_csv(tick_path, parse_dates=["timestamp"])
        self._df = self._df.sort_values("timestamp").reset_index(drop=True)
        self._delay_sec = delay_sec
        self._running = False

    def start(self, callback: Callable[[dict], None]) -> None:
        self._running = True
        for row in self._df.itertuples(index=False):
            if not self._running:
                break
            callback(row._asdict())
            time.sleep(self._delay_sec)

    def stop(self) -> None:
        self._running = False
