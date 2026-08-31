/* ═══════════════════════════════════════════════
   QQLinker 管理面板 — 客户端逻辑
   ═══════════════════════════════════════════════ */

let tk = localStorage.getItem('q_tk') || '',
  ct = 'db';

/* ── 通用工具 ── */
function api(p, b, m) {
  const o = { headers: {} };
  if (b) { o.method = 'POST'; o.body = JSON.stringify(b); o.headers['Content-Type'] = 'application/json'; }
  else if (m) o.method = m;
  if (tk) o.headers['X-Token'] = tk;
  return fetch('/api' + p, o).then(async r => {
    const d = await r.json();
    if (r.status === 401) { tk = ''; localStorage.removeItem('q_tk'); sh(); throw new Error('session expired'); }
    if (!d.ok && d.error) throw new Error(d.error);
    return d;
  });
}

function es(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function ej(s) { return String(s || '').replace(/'/g, "\\'").replace(/\\/g, "\\\\"); }

/* ── 登录/注册 ── */
function st(t) {
  document.getElementById('tL').className = t === 'login' ? 'ac' : '';
  document.getElementById('tR').className = t === 'reg' ? 'ac' : '';
  document.getElementById('fL').style.display = t === 'login' ? 'block' : 'none';
  document.getElementById('fR').style.display = t === 'reg' ? 'block' : 'none';
  document.getElementById('ae').textContent = '';
}

async function lg() {
  const u = document.getElementById('lU').value.trim(),
    p = document.getElementById('lP').value;
  if (!u || !p) { ae('请输入用户名和密码'); return; }
  try {
    const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, password: p }) });
    const d = await r.json();
    if (!d.ok) { ae(d.error || '登录失败'); return; }
    tk = d.token; localStorage.setItem('q_tk', tk); sa();
  } catch (e) { ae(e.message); }
}

async function rg() {
  const u = document.getElementById('rU').value.trim(),
    p = document.getElementById('rP').value,
    p2 = document.getElementById('rP2').value;
  if (u.length < 3 || u.length > 32) { ae('用户名需 3-32 字符'); return; }
  if (p.length < 6) { ae('密码至少 6 位'); return; }
  if (p !== p2) { ae('两次密码不一致'); return; }
  try {
    const r = await fetch('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, password: p }) });
    const d = await r.json();
    if (!d.ok) { ae(d.error || '注册失败'); return; }
    nf('注册成功，请登录', 'ok');
    document.getElementById('rU').value = ''; document.getElementById('rP').value = ''; document.getElementById('rP2').value = '';
    st('login'); document.getElementById('lU').value = u;
  } catch (e) { ae(e.message); }
}

function ae(m) { document.getElementById('ae').textContent = m || ''; }
function sa() { document.getElementById('lo').style.display = 'none'; document.getElementById('ap').classList.add('on'); document.getElementById('ud').textContent = '🔒 已登录'; ra(); }
function sh() { document.getElementById('lo').style.display = 'flex'; document.getElementById('ap').classList.remove('on'); document.getElementById('ae').textContent = '会话已过期'; }

function lo() {
  if (tk) api('/auth/logout', null, 'POST').catch(() => {});
  tk = ''; localStorage.removeItem('q_tk'); sh();
}

function nf(m, t) {
  const e = document.getElementById('to');
  e.textContent = m; e.className = 'to ' + t + ' on';
  setTimeout(() => e.classList.remove('on'), 2500);
}

/* ── 标签页切换 ── */
function sw(t) {
  ct = t;
  ['db', 'cf', 'md', 'us'].forEach(x => {
    document.getElementById('tb-' + x).className = x === t ? 'ac' : '';
    document.getElementById('pn-' + x).style.display = x === t ? 'block' : 'none';
  });
  ra();
}

function ra() {
  if (ct === 'db') rd();
  else if (ct === 'cf') rc();
  else if (ct === 'md') rm();
  else if (ct === 'us') ru();
}

/* ═══ DASHBOARD ═══ */
async function rd() {
  try {
    const d = await api('/dashboard'),
      s = d.stats || {};
    document.getElementById('pn-db').innerHTML =
      '<div class="sg">' +
      '<div class="st"><div class="v">' + es(s.uptime || '--') + '</div><div class="l">运行时间</div></div>' +
      '<div class="st"><div class="v">' + (s.module_count || 0) + '</div><div class="l">已加载模块</div></div>' +
      '<div class="st"><div class="v">' + (s.service_count || 0) + '</div><div class="l">已注册服务</div></div>' +
      '<div class="st"><div class="v">' + (s.ai_sessions || 0) + '</div><div class="l">AI 活跃会话</div></div>' +
      '<div class="st"><div class="v">' + (s.ban_count || 0) + '</div><div class="l">当前封禁</div></div>' +
      '<div class="st"><div class="v">' + (s.ws_connected ? '🟢' : '🔴') + '</div><div class="l">WebSocket</div></div>' +
      '</div>' +
      '<div class="cd"><h2><span class="dt"></span>模块列表</h2>' +
      (d.modules && d.modules.length ?
        '<table><tr><th>模块</th><th>版本</th><th>UID</th><th>命令</th><th>状态</th></tr>' +
        d.modules.map(m => '<tr><td><strong>' + es(m.name) + '</strong></td><td>' + es(m.version || '?') + '</td><td>' + ut(m.uid) + '</td><td>' + (m.commands || 0) + '</td><td>' + (m.active ? '🟢 运行' : '⚪ 停用') + '</td></tr>').join('') + '</table>'
        : '<p style="color:var(--muted)">暂无模块</p>') +
      '</div>' +
      '<div class="cd"><h2><span class="dt"></span>已注册服务</h2>' +
      (d.services && d.services.length ?
        '<table><tr><th>服务</th><th>UID</th><th>类型</th></tr>' +
        d.services.map(s => '<tr><td><strong>' + es(s.name) + '</strong></td><td>' + ut(s.uid) + '</td><td style="color:var(--muted);font-size:.78rem">' + es(s.kind || '') + '</td></tr>').join('') + '</table>'
        : '<p style="color:var(--muted)">暂无服务</p>') + '</div>';
  } catch (e) { document.getElementById('pn-db').innerHTML = '<div class="cd">❌ ' + es(e.message) + '</div>'; }
}

function ut(uid) {
  if (uid === 0) return '<span style="background:#e0556a33;color:#d05060;padding:1px 8px;border-radius:10px;font-size:.7rem">root</span>';
  if (uid <= 100) return '<span style="background:#e0904033;color:#e09040;padding:1px 8px;border-radius:10px;font-size:.7rem">daemon/' + uid + '</span>';
  if (uid <= 200) return '<span style="background:#5b8cff33;color:#5b8cff;padding:1px 8px;border-radius:10px;font-size:.7rem">service/' + uid + '</span>';
  if (uid <= 300) return '<span style="background:#40a07033;color:#40a070;padding:1px 8px;border-radius:10px;font-size:.7rem">app/' + uid + '</span>';
  return '<span style="background:#70708833;color:#707088;padding:1px 8px;border-radius:10px;font-size:.7rem">nobody</span>';
}

/* ═══ CONFIG ═══ */
let cfg = {},
  cfile = '',
  ch = {};

async function rc() {
  try {
    const d = await api('/config');
    cfg = d.config || {}; cfile = d.file || '';
    let h = '<div class="cd"><h2>⚙️ 配置文件: <code style="font-weight:400;color:var(--muted);font-size:.84rem">' + es(cfile) + '</code></h2>' +
      '<div class="sr"><input id="cs" placeholder="🔍 搜索配置项..." oninput="fc()"><span></span></div>' +
      '<div id="ct">' + rt(cfg, '') + '</div>' +
      '<div class="fa">' +
      '<button onclick="sv()" style="background:var(--accent);color:#fff;border:none;padding:8px 20px;border-radius:5px;cursor:pointer;font-weight:600">💾 保存全部</button>' +
      '<button onclick="rl()" style="background:var(--card);border:1px solid var(--bdr);color:var(--fg);padding:8px 20px;border-radius:5px;cursor:pointer">🔄 从文件重载</button>' +
      '</div></div>';
    document.getElementById('pn-cf').innerHTML = h;
  } catch (e) { document.getElementById('pn-cf').innerHTML = '<div class="cd">❌ ' + es(e.message) + '</div>'; }
}

function rt(obj, p) {
  let h = '';
  for (const [k, v] of Object.entries(obj)) {
    const fp = p ? p + '.' + k : k;
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      h += '<details open><summary style="cursor:pointer;padding:4px 0;font-weight:600;color:var(--accent)">' + es(k) + '</summary>';
      h += '<div style="margin-left:16px;border-left:2px solid var(--bdr);padding-left:12px">' + rt(v, fp) + '</div></details>';
    } else {
      h += rf(k, fp, v);
    }
  }
  return h;
}

function rf(key, fp, val) {
  let inp = '';
  const t = typeof val;
  if (t === 'boolean')
    inp = '<select onchange="fcv(this,\'' + ej(fp) + '\')"><option value="true" ' + (val ? 'selected' : '') + '>✅ true</option><option value="false" ' + (!val ? 'selected' : '') + '>❌ false</option></select>';
  else if (t === 'number')
    inp = '<input type="number" value="' + val + '" step="any" onchange="fcv(this,\'' + ej(fp) + '\')">';
  else if (Array.isArray(val))
    inp = '<textarea rows="2" onchange="fcv(this,\'' + ej(fp) + '\')">' + es(JSON.stringify(val)) + '</textarea><div class="ht">JSON 数组格式</div>';
  else
    inp = '<input type="text" value="' + es(String(val)) + '" onchange="fcv(this,\'' + ej(fp) + '\')">';

  return '<div class="ff" data-p="' + es(fp) + '"><label>' + es(key) + ' <span style="color:var(--muted);font-weight:400">(' + t + ')</span></label>' + inp + '</div>';
}

function fcv(el, p) {
  let r = el.value, v;
  if (el.type === 'number') v = parseFloat(r);
  else if (el.tagName === 'SELECT') v = r === 'true';
  else if (el.tagName === 'TEXTAREA') { try { v = JSON.parse(r); } catch (e) { v = r; } }
  else v = r;
  ch[p] = v;
}

async function sv() {
  if (!Object.keys(ch).length) { nf('没有更改', 'err'); return; }
  try {
    await api('/config/save', { changes: ch });
    ch = {}; nf('配置已保存', 'ok'); rc();
  } catch (e) { nf('保存失败: ' + e.message, 'err'); }
}

async function rl() {
  try { await api('/config/reload', null, 'POST'); ch = {}; nf('已重新加载', 'ok'); rc(); }
  catch (e) { nf('重载失败: ' + e.message, 'err'); }
}

function fc() {
  const q = (document.getElementById('cs')?.value || '').toLowerCase();
  document.querySelectorAll('.ff[data-p]').forEach(el => {
    const p = el.getAttribute('data-p') || '';
    const k = el.querySelector('label')?.textContent?.toLowerCase() || '';
    el.style.display = (!q || p.toLowerCase().includes(q) || k.includes(q)) ? '' : 'none';
  });
  document.querySelectorAll('details').forEach(el => {
    const v = el.querySelector('.ff:not([style*="display: none"])');
    el.style.display = (!v && q) ? 'none' : '';
  });
}

/* ═══ MODULES ═══ */
async function rm() {
  try {
    const d = await api('/modules/list'),
      mods = d.modules || [];
    let h = '<div class="cd"><h2>📦 已安装模块 (' + mods.length + ')</h2>' +
      '<div class="sr"><input id="ms" placeholder="🔍 搜索..." oninput="fm()"><button onclick="im()">+ 安装</button></div>' +
      '<div id="ml"><table><tr><th>模块</th><th>类型</th><th>操作</th></tr>';
    if (!mods.length) h += '<tr><td colspan="3" style="color:var(--muted)">暂无</td></tr>';
    else mods.forEach(m => {
      h += '<tr data-m="' + es(m.name) + '"><td><strong>' + es(m.name) + '</strong></td><td style="color:var(--muted)">' + es(m.type || '?') + '</td><td>' +
        '<button class="sm gr" onclick="vm(\'' + ej(m.name) + '\')">查看</button>' +
        '<button class="sm dg" onclick="um(\'' + ej(m.name) + '\')">卸载</button>' +
        '</td></tr>';
    });
    h += '</table></div></div>';
    document.getElementById('pn-md').innerHTML = h;
  } catch (e) { document.getElementById('pn-md').innerHTML = '<div class="cd">❌ ' + es(e.message) + '</div>'; }
}

function fm() {
  const q = (document.getElementById('ms')?.value || '').toLowerCase();
  document.querySelectorAll('#ml tr[data-m]').forEach(tr => {
    tr.style.display = tr.getAttribute('data-m')?.toLowerCase().includes(q) ? '' : 'none';
  });
}

function im() {
  const u = prompt('模块下载 URL 或名称：');
  if (!u) return;
  nf('安装中...', 'ok');
  api('/modules/install', { url: u }).then(r => {
    nf(r.ok ? '安装成功！请重载模块' : '错误: ' + (r.error || '?'), r.ok ? 'ok' : 'err');
    if (r.ok) rm();
  }).catch(e => nf(e.message, 'err'));
}

function vm(name) {
  alert('模块: ' + name + '\n\n请使用控制台 qqdeps module info ' + name + ' 查看详情。');
}

async function um(name) {
  if (!confirm('确认卸载模块 "' + name + '"？此操作不可恢复。')) return;
  try {
    const r = await api('/modules/uninstall', { name: name });
    nf(r.ok ? '模块已卸载' : '错误: ' + (r.error || '?'), r.ok ? 'ok' : 'err');
    if (r.ok) rm();
  } catch (e) { nf(e.message, 'err'); }
}

/* ═══ USERS ═══ */
async function ru() {
  try {
    const d = await api('/users/list'),
      us = d.users || [];
    let h = '<div class="cd"><h2>👤 管理用户 (' + us.length + ')</h2>' +
      '<div class="sr"><span></span><button onclick="au()">+ 添加用户</button></div>' +
      '<table><tr><th>用户名</th><th>创建时间</th><th>操作</th></tr>';
    if (!us.length) h += '<tr><td colspan="3" style="color:var(--muted)">暂无用户</td></tr>';
    else us.forEach(u => {
      h += '<tr><td><strong>' + es(u.name) + '</strong></td><td style="color:var(--muted)">' + es(u.created || '?') + '</td><td>' +
        '<button class="sm dg" onclick="du(\'' + ej(u.name) + '\')">删除</button></td></tr>';
    });
    h += '</table></div>';
    document.getElementById('pn-us').innerHTML = h;
  } catch (e) { document.getElementById('pn-us').innerHTML = '<div class="cd">❌ ' + es(e.message) + '</div>'; }
}

function au() {
  const u = prompt('用户名：'); if (!u) return;
  const p = prompt('密码：'); if (!p) return;
  api('/users/add', { username: u, password: p }).then(r => {
    nf(r.ok ? '用户已添加' : '错误: ' + (r.error || '?'), r.ok ? 'ok' : 'err');
    if (r.ok) ru();
  }).catch(e => nf(e.message, 'err'));
}

async function du(name) {
  if (!confirm('确认删除用户 "' + name + '"？此操作不可恢复。')) return;
  try { const r = await api('/users/delete', { username: name }); nf(r.ok ? '已删除' : '错误: ' + (r.error || '?'), r.ok ? 'ok' : 'err'); if (r.ok) ru(); }
  catch (e) { nf(e.message, 'err'); }
}

/* ═══ INIT ═══ */
if (tk) { api('/auth/check').then(d => { if (d.ok) sa(); else sh(); }).catch(() => sh()); }
else sh();
setInterval(() => { if (document.getElementById('ap').classList.contains('on')) ra(); }, 15000);
