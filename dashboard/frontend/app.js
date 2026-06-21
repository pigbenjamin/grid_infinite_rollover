// WebSocket 連線與即時渲染

const ws = new WebSocket(`ws://${location.host}/ws`);
const connStatus = document.getElementById('conn-status');

ws.onopen = () => {
  connStatus.textContent = '已連線';
  connStatus.className = 'badge badge-green';
};

ws.onclose = () => {
  connStatus.textContent = '已斷線';
  connStatus.className = 'badge badge-red';
  setTimeout(() => location.reload(), 3000);
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.margin)   renderMargin(data.margin);
  if (data.position) renderPosition(data.position);
  if (data.orders)   renderOrders(data.orders);
  if (data.logs)     renderLogs(data.logs);
};

function renderMargin(m) {
  setText('total-equity',   fmt(m.total_equity));
  setText('avail-margin',   fmt(m.avail_margin));
  setText('unrealized-pnl', fmt(m.unrealized_pnl));
  setText('leverage',       (m.real_leverage || 0).toFixed(2) + 'x');
  const ind = document.getElementById('leverage-indicator');
  const lv = (m.leverage_level || 'SAFE').toUpperCase();
  ind.textContent = lv;
  ind.className = `level-${lv.toLowerCase()}`;
}

function renderPosition(p) {
  if (!p) return;
  setText('pos-symbol', p.symbol || '--');
  setText('pos-qty',    p.quantity ?? '--');
  setText('pos-cost',   p.avg_cost ? p.avg_cost.toFixed(0) : '--');
  setText('pos-price',  p.latest_price ? p.latest_price.toFixed(0) : '--');
  setText('pos-pnl',    fmt(p.unrealized_pnl));
}

function renderOrders(orders) {
  const tbody = document.getElementById('orders-body');
  tbody.innerHTML = orders.map(o =>
    `<tr>
       <td class="${o.direction === 'BUY' ? 'log-info' : 'log-critical'}">${o.direction}</td>
       <td>${o.price}</td>
       <td>${o.quantity}</td>
       <td>${o.created_at?.slice(11, 19) || '--'}</td>
     </tr>`
  ).join('');
}

function renderLogs(logs) {
  const ul = document.getElementById('log-list');
  ul.innerHTML = logs.slice(0, 50).map(l => {
    const cls = l.level === 'CRITICAL' ? 'log-critical' :
                l.level === 'WARNING'  ? 'log-warning'  : 'log-info';
    return `<li class="${cls}">[${l.logged_at?.slice(11, 19)}] ${l.module}: ${l.message}</li>`;
  }).join('');
}

// 控制面板
async function emergencyStop() {
  if (!confirm('確定要緊急停止所有交易並撤銷掛單？')) return;
  await fetch('/api/emergency_stop', { method: 'POST' });
}

async function resumeTrading() {
  await fetch('/api/resume', { method: 'POST' });
}

// 工具函式
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function fmt(val) {
  if (val == null) return '--';
  return val >= 0
    ? '+' + val.toLocaleString('zh-TW', { maximumFractionDigits: 0 })
    : val.toLocaleString('zh-TW', { maximumFractionDigits: 0 });
}
