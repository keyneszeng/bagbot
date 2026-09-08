// BagBot dashboard — minimal vanilla JS, polls /api/state every 10s.

const $ = (id) => document.getElementById(id);

async function fetchState() {
  try {
    const r = await fetch('/api/state');
    if (!r.ok) return;
    const s = await r.json();
    if (s.status === 'no_tick_yet') return;
    renderState(s);
  } catch (e) { console.error(e); }
}

function renderState(s) {
  $('bal-unclaimed').textContent = '$' + s.balance.unclaimed_usd.toFixed(2);
  $('bal-earned').textContent    = '$' + (s.balance.accrued_usd ?? s.balance.earned_usd ?? 0).toFixed(2);
  $('bal-claimed').textContent   = '$' + s.balance.spent_usd?.toFixed(2) ?? '$0.00';

  if (s.key && s.key.has_key) {
    $('key-id').textContent = s.key.prefix || '—';
    $('key-remaining').textContent = '账户余额即额度';
    $('key-used').textContent = s.key.last_used_at
      ? '上次使用 ' + new Date(s.key.last_used_at * 1000).toLocaleString('zh-CN')
      : '尚未使用';
  } else {
    $('key-id').textContent = '无 key';
    $('key-remaining').textContent = '—';
    $('key-used').textContent = '—';
  }

  $('action').textContent = s.action;
  $('action').className = 'action-' + s.action;
  $('reason').textContent = s.reason;
  $('ts').textContent = new Date(s.ts * 1000).toLocaleString('zh-CN');
}

async function fetchEvents() {
  try {
    const r = await fetch('/api/events?limit=20');
    const ev = await r.json();
    const body = $('events-body');
    body.innerHTML = ev.map(e => `
      <tr>
        <td>${new Date(e.ts * 1000).toLocaleString('zh-CN')}</td>
        <td class="lvl-${e.level}">${e.level}</td>
        <td>${e.kind}</td>
        <td>${e.message}</td>
      </tr>
    `).join('');
  } catch (e) { console.error(e); }
}

async function fetchBalancesAndDraw() {
  try {
    const r = await fetch('/api/balances?limit=120');
    const data = await r.json();
    drawChart(data.reverse());
  } catch (e) { console.error(e); }
}

function drawChart(data) {
  const c = $('balance-chart');
  if (!c) return;
  const ctx = c.getContext('2d');
  const w = c.width, h = c.height;
  ctx.clearRect(0, 0, w, h);

  if (data.length < 2) {
    ctx.fillStyle = '#8a91a3';
    ctx.font = '14px sans-serif';
    ctx.fillText('数据采集中…', 20, h / 2);
    return;
  }

  const xs = data.map(d => d.ts);
  const ys = data.map(d => d.unclaimed_usd);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = 0, maxY = Math.max(...ys, 1);

  const padL = 50, padR = 20, padT = 20, padB = 30;
  const x = (v) => padL + (v - minX) / (maxX - minX) * (w - padL - padR);
  const y = (v) => h - padB - (v - minY) / (maxY - minY) * (h - padT - padB);

  // grid
  ctx.strokeStyle = '#2a2e38';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const yy = padT + i * (h - padT - padB) / 4;
    ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(w - padR, yy); ctx.stroke();
    ctx.fillStyle = '#8a91a3';
    ctx.font = '11px sans-serif';
    ctx.fillText('$' + (maxY * (1 - i / 4)).toFixed(2), 4, yy + 4);
  }

  // line
  ctx.strokeStyle = '#7B61FF';
  ctx.lineWidth = 2;
  ctx.beginPath();
  data.forEach((d, i) => {
    const px = x(d.ts), py = y(d.unclaimed_usd);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
  ctx.stroke();

  // fill
  ctx.lineTo(x(data[data.length - 1].ts), h - padB);
  ctx.lineTo(x(data[0].ts), h - padB);
  ctx.closePath();
  ctx.fillStyle = 'rgba(123, 97, 255, 0.15)';
  ctx.fill();
}

function getDashboardToken() {
  // Prefer localStorage; fall back to a one-time prompt.
  let t = localStorage.getItem('bagbot_dashboard_token') || '';
  if (!t) {
    t = prompt('请输入 DASHBOARD_TOKEN（将保存在本机 localStorage）') || '';
    if (t) localStorage.setItem('bagbot_dashboard_token', t);
  }
  return t;
}

function authHeaders(extra) {
  const h = Object.assign({}, extra || {});
  const t = getDashboardToken();
  if (t) h['X-Dashboard-Token'] = t;
  return h;
}

async function manualCreate() {
  const r = await fetch('/api/create', { method: 'POST', headers: authHeaders() });
  const body = await r.json().catch(() => ({}));
  $('action-result').textContent = r.ok
    ? '✓ 已' + (body.replaced ? '轮换' : '创建') + ' key ' + (body.prefix || '')
    : '✗ 失败：' + (body.detail || r.status);
  setTimeout(fetchState, 1500);
}
async function manualRevoke() {
  if (!confirm('确定撤销当前 key？撤销后需重新创建。')) return;
  const r = await fetch('/api/revoke', { method: 'POST', headers: authHeaders() });
  const body = await r.json().catch(() => ({}));
  $('action-result').textContent = r.ok
    ? (body.revoked ? '✓ 已撤销 key' : '· 本来就没有 key')
    : '✗ 失败：' + (body.detail || r.status);
  setTimeout(fetchState, 1500);
}

fetchState();
fetchEvents();
fetchBalancesAndDraw();
setInterval(fetchState, 10000);
setInterval(fetchEvents, 15000);
setInterval(fetchBalancesAndDraw, 60000);
