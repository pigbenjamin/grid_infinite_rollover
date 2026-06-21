"""
系統啟動入口 — main.py

執行方式：
  模擬實盤：python main.py --mode paper
  回測：    python main.py --mode backtest --tick data/historical/tick/MXTF_202401.parquet
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/trading.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


def run_paper(config_path: str) -> None:
    from broker.paper_broker import PaperBroker
    from core.engine import TradingEngine
    from paper_trading.feed import SimulatedFeed
    from dashboard.backend import server as dashboard

    broker = PaperBroker(config_path)
    engine = TradingEngine(broker, config_path)
    dashboard.init(config_path, engine)

    engine.start()

    def shutdown(sig, frame):
        logger.info("收到終止訊號，正在關閉...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    signal.pause()


def run_backtest(config_path: str, tick_path: str,
                 start_date: str, end_date: str) -> None:
    import json
    from backtest.engine import BacktestEngine

    engine = BacktestEngine(config_path)
    report = engine.run(tick_path, start_date, end_date)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GridBot 交易系統")
    parser.add_argument("--mode", choices=["paper", "backtest"], default="paper")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--tick", default="", help="回測 Tick 資料路徑")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2023-12-31")
    args = parser.parse_args()

    if args.mode == "paper":
        run_paper(args.config)
    elif args.mode == "backtest":
        run_backtest(args.config, args.tick, args.start, args.end)
