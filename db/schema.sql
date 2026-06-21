-- 期貨無限換倉＋網格自動化交易系統 — SQLite 資料庫 Schema
-- 初始化指令：sqlite3 storage/trading.db < db/schema.sql
-- 所有連線啟動時須執行：PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;

PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;

-- 保證金與帳戶狀態（每 Tick 更新）
CREATE TABLE IF NOT EXISTS margin_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
    daily_balance   REAL NOT NULL,       -- 今日餘額（元）
    original_margin REAL NOT NULL,       -- 佔用原始保證金（元）
    maint_margin    REAL NOT NULL,       -- 佔用維持保證金（元）
    avail_margin    REAL NOT NULL,       -- 可用保證金（元）
    unrealized_pnl  REAL NOT NULL,       -- 浮動損益（元）
    realized_pnl    REAL NOT NULL,       -- 已實現損益（元，當日）
    total_equity    REAL NOT NULL,       -- 帳戶總權益（元）
    real_leverage   REAL NOT NULL,       -- 真實槓桿倍數
    leverage_level  TEXT NOT NULL        -- 槓桿等級：SAFE / WARN / REDUCE / CRITICAL
);

-- 目前持倉明細
CREATE TABLE IF NOT EXISTS position_details (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
    symbol          TEXT NOT NULL,       -- 合約代碼
    quantity        INTEGER NOT NULL,    -- 持倉口數（多單為正）
    avg_cost        REAL NOT NULL,       -- 平均成本（點）
    latest_price    REAL NOT NULL,       -- 最新成交價（點）
    unrealized_pnl  REAL NOT NULL        -- 未實現損益（元）
);

-- 未成交網格限價委託單
CREATE TABLE IF NOT EXISTS open_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
    order_id        TEXT NOT NULL UNIQUE, -- 券商訂單號
    symbol          TEXT NOT NULL,
    price           REAL NOT NULL,       -- 委託價（點）
    quantity        INTEGER NOT NULL,    -- 口數
    direction       TEXT NOT NULL        -- BUY / SELL
);

-- 下次預期觸發的網格目標價
CREATE TABLE IF NOT EXISTS next_trade_targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
    next_buy_price  REAL,                -- 下一個買入觸發價（點）
    next_buy_qty    INTEGER,
    next_sell_price REAL,                -- 下一個賣出觸發價（點）
    next_sell_qty   INTEGER,
    symbol          TEXT NOT NULL
);

-- 換倉歷史記錄（成本統計用）
CREATE TABLE IF NOT EXISTS rollover_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rolled_at       DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
    old_symbol      TEXT NOT NULL,       -- 舊合約代碼
    new_symbol      TEXT NOT NULL,       -- 新合約代碼
    old_close_price REAL NOT NULL,       -- 舊合約平倉成交價（點）
    new_open_price  REAL NOT NULL,       -- 新合約建倉成交價（點）
    spread_points   REAL NOT NULL,       -- 換倉點差（新 - 舊，正值代表成本）
    quantity        INTEGER NOT NULL,    -- 換倉口數
    cost_ntd        REAL NOT NULL        -- 換倉成本（元）= spread × multiplier × qty
);

-- 待確認訂單（冪等機制，防崩潰重複下單）
CREATE TABLE IF NOT EXISTS pending_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
    local_order_id  TEXT NOT NULL UNIQUE, -- 本地生成的冪等 ID（UUID）
    broker_order_id TEXT,                -- 券商回傳訂單號（確認後填入）
    symbol          TEXT NOT NULL,
    price           REAL,
    quantity        INTEGER NOT NULL,
    direction       TEXT NOT NULL,
    order_type      TEXT NOT NULL,       -- LIMIT / MARKET
    status          TEXT NOT NULL        -- PENDING / CONFIRMED / CANCELLED / REJECTED
);

-- 帳戶狀態快照（崩潰恢復用，每 60 秒寫入）
CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at     DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
    total_equity    REAL NOT NULL,
    position_qty    INTEGER NOT NULL,
    real_leverage   REAL NOT NULL,
    system_state    TEXT NOT NULL        -- RUNNING / PAUSED / ROLLOVER / EMERGENCY
);

-- 系統日誌（儀表板區塊 F 用）
CREATE TABLE IF NOT EXISTS system_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at       DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
    level           TEXT NOT NULL,       -- INFO / WARNING / ERROR / CRITICAL
    module          TEXT NOT NULL,       -- 模組名稱
    message         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_margin_status_time ON margin_status(updated_at);
CREATE INDEX IF NOT EXISTS idx_rollover_log_time  ON rollover_log(rolled_at);
CREATE INDEX IF NOT EXISTS idx_system_logs_time   ON system_logs(logged_at);
CREATE INDEX IF NOT EXISTS idx_pending_local_id   ON pending_orders(local_order_id);
