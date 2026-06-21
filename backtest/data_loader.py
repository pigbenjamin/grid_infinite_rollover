"""
歷史資料載入與清洗 — BacktestDataLoader

支援 Parquet（Tick / K 線）與 CSV 格式。
所有資料以 timestamp 嚴格排序，確保無前視偏差。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import pandas as pd

logger = logging.getLogger(__name__)

TICK_GAP_WARN_MIN = 5  # 相鄰 Tick 差超過此分鐘數記警告


def load_tick(path: str) -> pd.DataFrame:
    """載入 Tick Parquet 檔，回傳以 timestamp 升序排列的 DataFrame"""
    df = _read_file(path)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = _clean_ticks(df)
    return df


def load_kline(path: str) -> pd.DataFrame:
    """載入 K 線資料（1分鐘或日線）"""
    df = _read_file(path)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def load_rollover_spread(path: str) -> pd.DataFrame:
    """載入換倉點差 CSV：date, contract_sold, contract_bought, spread_points"""
    return pd.read_csv(path, parse_dates=["date"])


def load_trading_calendar(path: str) -> set[str]:
    """載入交易日行事曆，回傳有效交易日集合（'YYYY-MM-DD'）"""
    df = pd.read_csv(path)
    return set(df["date"].astype(str).tolist())


def iter_ticks(df: pd.DataFrame) -> Iterator[dict]:
    """逐筆產出 Tick dict，供回測引擎使用"""
    for row in df.itertuples(index=False):
        yield row._asdict()


def _read_file(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    if p.suffix == ".csv":
        return pd.read_csv(p, parse_dates=["timestamp"])
    raise ValueError(f"不支援的資料格式：{p.suffix}")


def _clean_ticks(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    gaps = df["timestamp"].diff().dt.total_seconds() / 60
    large_gaps = gaps[gaps > TICK_GAP_WARN_MIN]
    for idx in large_gaps.index:
        logger.warning("Tick 缺漏：%s 前後間隔 %.1f 分鐘，以前值填充",
                       df.at[idx, "timestamp"], gaps[idx])

    df["price"] = df["price"].ffill()
    return df
