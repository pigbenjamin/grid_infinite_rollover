# 期貨無限換倉＋網格自動化交易系統

以微台指期（MXTF）為主要標的的自動化量化交易系統，結合不對稱網格策略、期貨動態換倉機制與三級槓桿風控，並具備完整回測引擎與即時監控儀表板。系統設計為完全離線可運行，部署於 Ubuntu Linux 環境。

---

## 策略核心概念

本策略為「改良型反向正二策略」：下跌加倉、上漲減倉，利用超額保證金壓低槓桿，在震盪慢牛行情中透過網格差價累積獲利。

| 行情類型 | 策略行為 |
|---|---|
| 緩步下跌 | 依持倉分級加倉（1% → 2% → 4% 步長）|
| 反彈上漲 | 漲 2% 執行減倉，積累網格差價 |
| 單邊暴漲 | 保留最低 2 口底倉，不空手 |
| 滿倉低迷 | 觸發 Collar 選擇權避險（SC + BP）|
| 合約到期 | DTE ≤ 5 日自動換倉至次月合約 |

---

## 系統架構

```
main.py
  ├── TradingEngine（交易核心）
  │     ├── GridStrategy   ← 網格加減倉邏輯
  │     ├── RiskManager    ← 三級槓桿閥值監控
  │     ├── RolloverManager← 換倉執行流程
  │     └── OptionsHedger  ← Collar 避險觸發判斷
  │
  ├── AbstractBroker（API 抽象層）
  │     └── PaperBroker   ← 模擬券商（回測/模擬實盤用）
  │         FutureBroker  ← 未來真實券商 API（預留）
  │
  ├── BacktestEngine（回測引擎）
  │     ├── DataLoader    ← Parquet/CSV 歷史資料載入
  │     ├── CostModel     ← 手續費、期交稅、滑價
  │     ├── Reporter      ← Sharpe、MDD、報酬率報告
  │     └── WalkForward   ← 滾動視窗驗證
  │
  ├── SQLite DB（WAL 模式）
  │     └── 7 張資料表（持倉、保證金、訂單、快照…）
  │
  └── Dashboard（FastAPI + WebSocket）
        ├── 即時監控介面（A~F 六個區塊）
        └── 控制面板（緊急停止、換倉、恢復）
```

---

## 主要功能

### 策略
- **不對稱網格**：跌 1%/2%/4% 加倉（依持倉分級），漲 2% 減倉
- **盤中回跌攔截**：自當日高點跌 2% 觸發加倉，附 30 分鐘 Cooldown 防雙重觸發
- **最低底倉保護**：持倉不低於 2 口，確保多頭波段不空手
- **DTE 換倉**：剩餘 ≤ 5 交易日自動平倉舊合約、建倉新合約並記錄點差成本

### 風控
- **三級槓桿閥值**：5x 暫停加倉 / 7x 減倉 25% / 9x 緊急最大減倉
- **耐震度設計**：8 口滿倉需 ≥ 150 萬入金，可承受 15% 極端下跌不被強平
- **崩潰恢復**：冪等訂單機制 + 60 秒狀態快照，重啟後自動核對持倉

### 儀表板
- WebSocket 即時推送，零輪詢延遲
- 六區塊監控（保證金、持倉、委託單、淨值曲線、日誌、控制面板）
- 緊急停止、手動換倉、恢復按鈕

---

## 環境需求

- **Python** 3.11+
- **OS**：Ubuntu 22.04 LTS（部署）/ Windows（開發）
- **離線**：所有運行時依賴均可離線安裝，無需外部連線

---

## 安裝

```bash
# 1. 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 安裝套件
pip install -r requirements.txt

# 3. 初始化資料庫
sqlite3 storage/trading.db < db/schema.sql
```

---

## 設定

所有策略參數集中於 [config.yaml](config.yaml)，**不寫死於程式碼**：

```yaml
contract:
  symbol: "MXTF"        # 微台期（台指期改為 TXFF，multiplier 改為 200）
  multiplier: 50

grid:
  max_position: 8       # 最大口數上限
  tiers:
    - [4, 1.0]          # 0–4 口：跌 1% 加倉
    - [6, 2.0]          # 5–6 口：跌 2% 加倉
    - [8, 4.0]          # 7–8 口：跌 4% 加倉

risk:
  leverage_warn: 5.0    # 暫停加倉
  leverage_reduce: 7.0  # 自動減倉 25%
  leverage_critical: 9.0

account:
  initial_capital: 1500000   # 建議入金：150–180 萬
```

切換台指 ↔ 微台只需修改 `contract` 區塊，其他邏輯不變。

---

## 執行方式

### 模擬實盤

```bash
python main.py --mode paper
```

瀏覽器開啟 `http://localhost:8080` 查看儀表板。

### 回測

```bash
python main.py --mode backtest \
  --tick data/historical/tick/MXTF_202401.parquet \
  --start 2023-01-01 \
  --end 2023-12-31
```

### Walk-Forward 驗證

```python
from backtest.walk_forward import run_walk_forward
results = run_walk_forward("data/historical/tick/MXTF_2023.parquet")
```

### 執行測試

```bash
pytest tests/unit/ -v
```

---

## 歷史資料格式

**Tick Parquet**（存放於 `data/historical/tick/`）：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `timestamp` | datetime | 成交時間 |
| `symbol` | str | 合約代碼 |
| `price` | float | 成交價（點）|
| `volume` | int | 成交量（口）|

**換倉點差 CSV**（`data/rollover_spread/rollover_spread.csv`）：

| 欄位 | 說明 |
|---|---|
| `date` | 換倉日期（YYYY-MM-DD）|
| `contract_sold` | 平倉合約代碼 |
| `contract_bought` | 建倉合約代碼 |
| `spread_points` | 換倉點差（點）|
| `dte` | 換倉當日 DTE |

---

## Linux 部署

```bash
# 1. 複製服務設定
sudo cp deploy/trading-core.service      /etc/systemd/system/
sudo cp deploy/trading-dashboard.service /etc/systemd/system/
sudo cp deploy/logrotate.conf            /etc/logrotate.d/gridbot

# 2. 啟用並啟動
sudo systemctl daemon-reload
sudo systemctl enable trading-core trading-dashboard
sudo systemctl start  trading-core trading-dashboard

# 3. 確認狀態
sudo systemctl status trading-core
journalctl -u trading-core -f
```

---

## 資料庫資料表

| 資料表 | 用途 |
|---|---|
| `margin_status` | 即時保證金狀態（每 Tick 更新）|
| `position_details` | 目前持倉明細 |
| `open_orders` | 未成交網格限價委託單 |
| `next_trade_targets` | 下一個買入/賣出觸發價 |
| `rollover_log` | 換倉歷史（點差成本統計）|
| `pending_orders` | 冪等訂單（防崩潰重複下單）|
| `snapshots` | 60 秒帳戶快照（崩潰恢復用）|

---

## 接入真實券商

目前系統使用 `PaperBroker` 模擬。接入真實券商時：

1. 繼承 [broker/base.py](broker/base.py) 的 `AbstractBroker`
2. 實作所有 `@abstractmethod`（login、subscribe_market_data、place_order 等 10 個方法）
3. 在 `main.py` 將 `PaperBroker()` 替換為新 Broker 實例

核心策略邏輯**不需修改任何一行**。

---

## 告警通知設定

編輯 `config.yaml` 的 `notification` 區塊：

```yaml
notification:
  provider: "telegram"       # 或 "line"
  token: "YOUR_BOT_TOKEN"
  chat_id: "YOUR_CHAT_ID"    # LINE Notify 不需要此欄
```

| 等級 | 觸發時機 |
|---|---|
| INFO | 換倉完成、減倉成功、程序啟動/關閉 |
| WARNING | 槓桿超 5x、DTE 進入換倉準備 |
| CRITICAL | 槓桿超 9x、建倉失敗、持倉不一致、程序崩潰 |

---

## 專案文件

- [strategy.md](strategy.md) — 完整需求規格書（SRS），含策略詳細描述、風控數學驗算、各系統需求
