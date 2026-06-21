"""
回測報告產出 — BacktestReporter

計算並輸出：總報酬率、年化報酬率、Sharpe Ratio、MDD、
換倉成本年化磨損、勝率等指標。
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd


class BacktestReporter:
    def __init__(self, equity_curve: list[dict], multiplier: int) -> None:
        self._df = pd.DataFrame(equity_curve)
        self._multiplier = multiplier

    def generate(self) -> dict:
        if self._df.empty:
            return {}

        df = self._df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        init_equity = df["equity"].iloc[0]
        final_equity = df["equity"].iloc[-1]
        total_return = (final_equity - init_equity) / init_equity

        years = (df["date"].iloc[-1] - df["date"].iloc[0]).days / 365.25
        annual_return = (1 + total_return) ** (1 / max(years, 0.01)) - 1

        daily_ret = df["equity"].pct_change().dropna()
        sharpe = (
            daily_ret.mean() / daily_ret.std() * math.sqrt(252)
            if daily_ret.std() > 0 else 0.0
        )

        rolling_max = df["equity"].cummax()
        drawdown = (df["equity"] - rolling_max) / rolling_max
        mdd = drawdown.min()

        return {
            "total_return_pct": round(total_return * 100, 2),
            "annual_return_pct": round(annual_return * 100, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(mdd * 100, 2),
            "trading_days": len(df),
            "equity_curve": df[["date", "equity", "position_qty"]].to_dict("records"),
        }
