"""QQLinker 管理面板 — Web UI 后台（内置模块）

═══════════════════════════════════════════════════════════════════════════
格式转换声明:
  本模块受 ToolDelta 框架插件市场上传限制（仅接受 .py / .md / .txt 格式）,
  无法直接上传 .html 文件。因此我们采用 Python 脚本格式上传,将完整的
  Web UI 前端（HTML/CSS/JS）内嵌在 Python 字符串中,于运行时动态提供
  HTTP 服务。此转换仅因市场格式限制而采取的必要技术手段,非规避行为。
═══════════════════════════════════════════════════════════════════════════

功能: 用户注册/登录 | 配置文件可视化编辑 | 模块安装/卸载 | 实时仪表盘
安全: 默认 127.0.0.1:8381 | PBKDF2-SHA256 密码 | Token 24h 过期
"""
from __future__ import annotations
import hashlib, hmac, http.server, json, logging, os, re, secrets, threading, time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse
try:
    from ...core.module import Module
except ImportError:
    Module = object

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
# 密码
# ═══════════════════════════════════════════════
_ITERS = 200000; _HLEN = 32; _SLEN = 16

def _hash_pw(pw: str) -> str:
    s = secrets.token_hex(_SLEN)
    d = hashlib.pbkdf2_hmac('sha256', pw.encode(), s.encode(), _ITERS, _HLEN)
    return f"$pbkdf2${_ITERS}${s}${d.hex()}"

def _check_pw(pw: str, st: str) -> bool:
    try:
        _, _, n, s, h = st.split('$', 4)
        d = hashlib.pbkdf2_hmac('sha256', pw.encode(), s.encode(), int(n), _HLEN)
        return hmac.compare_digest(d.hex(), h)
    except Exception:
        return False

# ═══════════════════════════════════════════════
# 会话
# ═══════════════════════════════════════════════
class Sessions:
    def __init__(self):
        self._m = {}
        self._ttl = 86400
        self._login_fails = {}        # ip → [ts, ts, ...]
        self._max_fails = 5
        self._fail_window = 900         # 15 分钟

    def _check_bruteforce(self, ip: str) -> bool:
        """检查是否触发爆破保护。返回 True 表示被锁定。"""
        now = time.time()
        fails = self._login_fails.get(ip, [])
        fails = [t for t in fails if now - t < self._fail_window]
        self._login_fails[ip] = fails
        return len(fails) >= self._max_fails

    def _record_fail(self, ip: str):
        now = time.time()
        fails = self._login_fails.setdefault(ip, [])
        fails = [t for t in fails if now - t < self._fail_window]
        fails.append(now)
        self._login_fails[ip] = fails

    def _clear_fails(self, ip: str):
        self._login_fails.pop(ip, None)

    def mk(self, u: str) -> str:
        self._gc(); t = secrets.token_hex(32)
        self._m[t] = {"u": u, "ts": time.time()}; return t
    def ok(self, t: str) -> Optional[str]:
        self._gc(); s = self._m.get(t)
        if not s or time.time() - s["ts"] > self._ttl: return None
        return s["u"]
    def rm(self, t: str): self._m.pop(t, None)
    def _gc(self):
        n = time.time()
        for t in [t for t, s in self._m.items() if n - s["ts"] > self._ttl]:
            del self._m[t]

# ═══════════════════════════════════════════════
# 用户
# ═══════════════════════════════════════════════
class Users:
    def __init__(self, fp: str):
        self._p = fp; self._u: dict = {}; self._lk = threading.Lock()
        if os.path.exists(fp):
            try:
                with open(fp) as f: self._u = json.load(f)
            except Exception: self._u = {}
    def _sv(self):
        os.makedirs(os.path.dirname(self._p) or '.', exist_ok=True)
        t = self._p + '.tmp'
        with open(t, 'w') as f: json.dump(self._u, f, ensure_ascii=False, indent=2)
        os.replace(t, self._p)
    def add(self, u: str, p: str) -> bool:
        with self._lk:
            if u in self._u: return False
            self._u[u] = {"pw": _hash_pw(p), "ts": time.time()}; self._sv(); return True
    def chk(self, u: str, p: str) -> bool:
        with self._lk:
            if u not in self._u: return False
            return _check_pw(p, self._u[u].get("pw", ""))
    def ls(self) -> List[str]:
        with self._lk: return sorted(self._u.keys())
    def rm(self, u: str) -> bool:
        with self._lk:
            if u not in self._u: return False
            del self._u[u]; self._sv(); return True

# ═══════════════════════════════════════════════
# 前端 HTML
# ═══════════════════════════════════════════════
_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QQLinker 管理面板</title>
<style>
:root{--bg:#0d0d14;--card:#181825;--bdr:#282840;--fg:#c8c8d8;--muted:#707088;
--accent:#5b8cff;--green:#40a070;--red:#d05060;--orange:#e09040;--inp:#141420;--r:10px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;background:var(--bg);color:var(--fg);min-height:100vh}
#lo{position:fixed;inset:0;background:var(--bg);display:flex;align-items:center;justify-content:center;z-index:999}
.lb{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);padding:40px;width:380px;max-width:90vw}
.lb h1{text-align:center;margin-bottom:24px;font-size:1.4rem}
.lb h1 span{color:var(--accent)}
.lb input{width:100%;padding:12px;margin-bottom:10px;background:var(--inp);border:1px solid var(--bdr);border-radius:6px;color:var(--fg);font-size:.92rem;outline:none}
.lb input:focus{border-color:var(--accent)}
.lb button{width:100%;padding:12px;border:none;border-radius:6px;background:var(--accent);color:#fff;font-size:.92rem;cursor:pointer;font-weight:600;margin-top:4px}
.lb button:hover{opacity:.9}
.lt{display:flex;margin-bottom:16px}
.lt button{flex:1;background:transparent;border:none;color:var(--muted);padding:8px;cursor:pointer;border-bottom:2px solid var(--bdr);font-size:.88rem}
.lt button.ac{color:var(--accent);border-bottom-color:var(--accent)}
.er{color:var(--red);font-size:.8rem;text-align:center;margin-top:8px;min-height:20px}
.ap{display:none;max-width:1200px;margin:0 auto;padding:20px}.ap.on{display:block}
.tb{display:flex;align-items:center;justify-content:space-between;padding:12px 0 20px;border-bottom:1px solid var(--bdr);margin-bottom:20px}
.tb h1{font-size:1.3rem}.tb h1 span{color:var(--accent)}
.tb .u{display:flex;align-items:center;gap:12px}
.tb .u button{background:var(--card);border:1px solid var(--bdr);color:var(--fg);padding:5px 14px;border-radius:6px;cursor:pointer;font-size:.8rem}
.ts{display:flex;gap:4px;margin-bottom:20px;flex-wrap:wrap}
.ts button{padding:8px 20px;background:var(--card);border:1px solid var(--bdr);color:var(--muted);border-radius:6px;cursor:pointer;font-size:.85rem}
.ts button.ac{background:var(--accent);color:#fff;border-color:var(--accent)}
.cd{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);padding:20px;margin-bottom:16px}
.cd h2{font-size:.95rem;color:var(--accent);margin-bottom:12px;display:flex;align-items:center;gap:6px}
.cd h2 .dt{width:8px;height:8px;border-radius:50%;background:var(--green);display:inline-block}
.sg{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:20px}
.st{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);padding:14px;text-align:center}
.st .v{font-size:1.6rem;font-weight:700;color:var(--accent)}
.st .l{font-size:.72rem;color:var(--muted);margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:.84rem}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--bdr)}
th{color:var(--muted);font-size:.72rem;text-transform:uppercase;font-weight:600}
tr:hover{background:rgba(91,140,255,.03)}
.sm{padding:3px 10px;border-radius:4px;border:1px solid var(--bdr);background:var(--card);color:var(--fg);cursor:pointer;font-size:.75rem;margin:0 2px}
.sm:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
.sm.dg:hover{background:var(--red);border-color:var(--red)}
.sm.gr:hover{background:var(--green);border-color:var(--green)}
.ff{display:flex;flex-direction:column;margin-bottom:6px}
.ff label{font-size:.78rem;color:var(--muted);margin-bottom:3px}
.ff input,.ff textarea,.ff select{padding:8px 10px;background:var(--inp);border:1px solid var(--bdr);border-radius:5px;color:var(--fg);font-size:.84rem;font-family:inherit}
.ff input:focus,.ff textarea:focus{border-color:var(--accent);outline:none}
.ff textarea{min-height:60px;resize:vertical}
.ff .ht{font-size:.7rem;color:var(--muted)}
.fa{display:flex;gap:8px;margin-top:16px}
.mo{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:100}
.mo.on{display:flex}
.mc{background:var(--card);border:1px solid var(--bdr);border-radius:var(--r);padding:24px;width:500px;max-width:90vw;max-height:80vh;overflow-y:auto}
.mc h3{color:var(--accent);margin-bottom:12px}
.to{position:fixed;bottom:20px;right:20px;padding:12px 20px;border-radius:8px;color:#fff;font-size:.84rem;z-index:200;opacity:0;transform:translateY(10px);transition:.3s}
.to.on{opacity:1;transform:none}
.to.ok{background:var(--green)}.to.err{background:var(--red)}
.sr{display:flex;gap:10px;margin-bottom:12px}
.sr input{flex:1;padding:8px;background:var(--inp);border:1px solid var(--bdr);border-radius:5px;color:var(--fg);font-size:.84rem}
.sr button{background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:5px;cursor:pointer;font-weight:600}
.inl{display:inline-flex;align-items:center;gap:8px}
</style></head><body>

<div id="lo"><div class="lb">
<h1>⚙️ <span>QQLinker</span> 管理面板</h1>
<div class="lt"><button id="tL" class="ac" onclick="st('login')">登录</button><button id="tR" onclick="st('reg')">注册</button></div>
<div id="fL"><input id="lU" placeholder="用户名" autocomplete="username"><input id="lP" type="password" placeholder="密码"><button onclick="lg()">登 录</button></div>
<div id="fR" style="display:none"><input id="rU" placeholder="用户名（3-32字符）"><input id="rP" type="password" placeholder="密码（至少6位）"><input id="rP2" type="password" placeholder="确认密码"><button onclick="rg()">注 册</button></div>
<div class="er" id="ae"></div>
</div></div>

<div class="ap" id="ap">
<div class="tb"><h1>⚙️ <span>QQLinker</span> 管理面板</h1><div class="u"><span id="ud"></span><button onclick="lo()">退出</button></div></div>
<div class="ts">
<button class="ac" onclick="sw('db')" id="tb-db">📊 仪表盘</button>
<button onclick="sw('cf')" id="tb-cf">⚙️ 配置</button>
<button onclick="sw('md')" id="tb-md">📦 模块</button>
<button onclick="sw('us')" id="tb-us">👤 用户</button>
</div>
<div id="pn-db"></div><div id="pn-cf" style="display:none"></div>
<div id="pn-md" style="display:none"></div><div id="pn-us" style="display:none"></div>
</div>

<div class="to" id="to"></div>

<script>
let tk = localStorage.getItem('q_tk')||'', ct = 'db';

function api(p, b, m) {
  let o = {headers:{}};
  if (b) { o.method='POST'; o.body=JSON.stringify(b); o.headers['Content-Type']='application/json'; }
  else if (m) o.method = m;
  if (tk) o.headers['X-Token'] = tk;
  return fetch('/api'+p, o).then(async r => {
    const d = await r.json();
    if (r.status===401) { tk=''; localStorage.removeItem('q_tk'); sh(); throw new Error('session expired'); }
    if (!d.ok && d.error) throw new Error(d.error);
    return d;
  });
}
function es(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function ej(s) { return String(s||'').replace(/'/g,"\\'").replace(/\\/g,"\\\\"); }

function st(t) {
  document.getElementById('tL').className = t==='login'?'ac':'';
  document.getElementById('tR').className = t==='reg'?'ac':'';
  document.getElementById('fL').style.display = t==='login'?'block':'none';
  document.getElementById('fR').style.display = t==='reg'?'block':'none';
  document.getElementById('ae').textContent='';
}

async function lg() {
  const u = document.getElementById('lU').value.trim(), p = document.getElementById('lP').value;
  if (!u||!p) { ae('请输入用户名和密码'); return; }
  try {
    const r = await fetch('/api/auth/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    const d = await r.json();
    if (!d.ok) { ae(d.error||'登录失败'); return; }
    tk = d.token; localStorage.setItem('q_tk', tk); sa();
  } catch(e) { ae(e.message); }
}

async function rg() {
  const u = document.getElementById('rU').value.trim(), p = document.getElementById('rP').value, p2 = document.getElementById('rP2').value;
  if (u.length<3||u.length>32) { ae('用户名需 3-32 字符'); return; }
  if (p.length<6) { ae('密码至少 6 位'); return; }
  if (p!==p2) { ae('两次密码不一致'); return; }
  try {
    const r = await fetch('/api/auth/register', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    const d = await r.json();
    if (!d.ok) { ae(d.error||'注册失败'); return; }
    nf('注册成功，请登录','ok');
    document.getElementById('rU').value=''; document.getElementById('rP').value=''; document.getElementById('rP2').value='';
    st('login'); document.getElementById('lU').value = u;
  } catch(e) { ae(e.message); }
}

function ae(m) { document.getElementById('ae').textContent = m||''; }
function sa() { document.getElementById('lo').style.display='none'; document.getElementById('ap').classList.add('on'); document.getElementById('ud').textContent='🔒 已登录'; ra(); }
function sh() { document.getElementById('lo').style.display='flex'; document.getElementById('ap').classList.remove('on'); document.getElementById('ae').textContent='会话已过期'; }
function lo() { if(tk) api('/auth/logout',null,'POST').catch(()=>{}); tk=''; localStorage.removeItem('q_tk'); sh(); }
function nf(m,t) { const e=document.getElementById('to'); e.textContent=m; e.className='to '+t+' on'; setTimeout(()=>e.classList.remove('on'),2500); }

function sw(t) {
  ct = t;
  ['db','cf','md','us'].forEach(x => {
    document.getElementById('tb-'+x).className = x===t?'ac':'';
    document.getElementById('pn-'+x).style.display = x===t?'block':'none';
  });
  ra();
}
function ra() {
  if (ct==='db') rd(); else if (ct==='cf') rc(); else if (ct==='md') rm(); else if (ct==='us') ru();
}

// ═══ DASHBOARD ═══
async function rd() {
  try {
    const d = await api('/dashboard'), s = d.stats||{};
    document.getElementById('pn-db').innerHTML =
      `<div class="sg">
        <div class="st"><div class="v">${es(s.uptime||'--')}</div><div class="l">运行时间</div></div>
        <div class="st"><div class="v">${s.module_count||0}</div><div class="l">已加载模块</div></div>
        <div class="st"><div class="v">${s.service_count||0}</div><div class="l">已注册服务</div></div>
        <div class="st"><div class="v">${s.ai_sessions||0}</div><div class="l">AI 活跃会话</div></div>
        <div class="st"><div class="v">${s.ban_count||0}</div><div class="l">当前封禁</div></div>
        <div class="st"><div class="v">${s.ws_connected?'🟢':'🔴'}</div><div class="l">WebSocket</div></div>
      </div>
      <div class="cd"><h2><span class="dt"></span>模块列表</h2>`+
      (d.modules&&d.modules.length?
        '<table><tr><th>模块</th><th>版本</th><th>UID</th><th>命令</th><th>状态</th></tr>'+
        d.modules.map(m=>`<tr><td><strong>${es(m.name)}</strong></td><td>${es(m.version||'?')}</td><td>${ut(m.uid)}</td><td>${m.commands||0}</td><td>${m.active?'🟢 运行':'⚪ 停用'}</td></tr>`).join('')+'</table>'
        :'<p style="color:var(--muted)">暂无模块</p>')+
      `</div>
      <div class="cd"><h2><span class="dt"></span>已注册服务</h2>`+
      (d.services&&d.services.length?
        '<table><tr><th>服务</th><th>UID</th><th>类型</th></tr>'+
        d.services.map(s=>`<tr><td><strong>${es(s.name)}</strong></td><td>${ut(s.uid)}</td><td style="color:var(--muted);font-size:.78rem">${es(s.kind||'')}</td></tr>`).join('')+'</table>'
        :'<p style="color:var(--muted)">暂无服务</p>')+'</div>';
  } catch(e) { document.getElementById('pn-db').innerHTML = `<div class="cd">❌ ${es(e.message)}</div>`; }
}

function ut(uid) {
  if (uid===0) return '<span style="background:#e0556a33;color:#d05060;padding:1px 8px;border-radius:10px;font-size:.7rem">root</span>';
  if (uid<=100) return '<span style="background:#e0904033;color:#e09040;padding:1px 8px;border-radius:10px;font-size:.7rem">daemon/'+uid+'</span>';
  if (uid<=200) return '<span style="background:#5b8cff33;color:#5b8cff;padding:1px 8px;border-radius:10px;font-size:.7rem">service/'+uid+'</span>';
  if (uid<=300) return '<span style="background:#40a07033;color:#40a070;padding:1px 8px;border-radius:10px;font-size:.7rem">app/'+uid+'</span>';
  return '<span style="background:#70708833;color:#707088;padding:1px 8px;border-radius:10px;font-size:.7rem">nobody</span>';
}

// ═══ CONFIG ═══
let cfg={}, cfile='', ch={};

async function rc() {
  try {
    const d = await api('/config');
    cfg = d.config||{}; cfile = d.file||'';
    let h = `<div class="cd"><h2>⚙️ 配置文件: <code style="font-weight:400;color:var(--muted);font-size:.84rem">${es(cfile)}</code></h2>
      <div class="sr"><input id="cs" placeholder="🔍 搜索配置项..." oninput="fc()"><span></span></div>
      <div id="ct">${rt(cfg,'')}</div>
      <div class="fa">
        <button onclick="sv()" style="background:var(--accent);color:#fff;border:none;padding:8px 20px;border-radius:5px;cursor:pointer;font-weight:600">💾 保存全部</button>
        <button onclick="rl()" style="background:var(--card);border:1px solid var(--bdr);color:var(--fg);padding:8px 20px;border-radius:5px;cursor:pointer">🔄 从文件重载</button>
      </div></div>`;
    document.getElementById('pn-cf').innerHTML = h;
  } catch(e) { document.getElementById('pn-cf').innerHTML = `<div class="cd">❌ ${es(e.message)}</div>`; }
}

function rt(obj, p) {
  let h = '';
  for (const [k,v] of Object.entries(obj)) {
    const fp = p ? p+'.'+k : k;
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      h += `<details open><summary style="cursor:pointer;padding:4px 0;font-weight:600;color:var(--accent)">${es(k)}</summary>`;
      h += `<div style="margin-left:16px;border-left:2px solid var(--bdr);padding-left:12px">${rt(v, fp)}</div></details>`;
    } else {
      h += rf(k, fp, v);
    }
  }
  return h;
}

function rf(key, fp, val) {
  let inp = '';
  const t = typeof val;
  if (t==='boolean')
    inp = `<select onchange="fcv(this,'${ej(fp)}')"><option value="true" ${val?'selected':''}>✅ true</option><option value="false" ${!val?'selected':''}>❌ false</option></select>`;
  else if (t==='number')
    inp = `<input type="number" value="${val}" step="any" onchange="fcv(this,'${ej(fp)}')">`;
  else if (Array.isArray(val))
    inp = `<textarea rows="2" onchange="fcv(this,'${ej(fp)}')">${es(JSON.stringify(val))}</textarea><div class="ht">JSON 数组格式</div>`;
  else
    inp = `<input type="text" value="${es(String(val))}" onchange="fcv(this,'${ej(fp)}')">`;

  return `<div class="ff" data-p="${es(fp)}"><label>${es(key)} <span style="color:var(--muted);font-weight:400">(${t})</span></label>${inp}</div>`;
}

function fcv(el, p) {
  let r = el.value, v;
  if (el.type==='number') v = parseFloat(r);
  else if (el.tagName==='SELECT') v = r==='true';
  else if (el.tagName==='TEXTAREA') { try { v=JSON.parse(r); } catch(e) { v=r; } }
  else v = r;
  ch[p] = v;
}

async function sv() {
  if (!Object.keys(ch).length) { nf('没有更改','err'); return; }
  try {
    await api('/config/save', {changes: ch});
    ch = {}; nf('配置已保存','ok'); rc();
  } catch(e) { nf('保存失败: '+e.message,'err'); }
}

async function rl() {
  try { await api('/config/reload',null,'POST'); ch={}; nf('已重新加载','ok'); rc(); }
  catch(e) { nf('重载失败: '+e.message,'err'); }
}

function fc() {
  const q = (document.getElementById('cs')?.value||'').toLowerCase();
  document.querySelectorAll('.ff[data-p]').forEach(el => {
    const p = el.getAttribute('data-p')||'';
    const k = el.querySelector('label')?.textContent?.toLowerCase()||'';
    el.style.display = (!q || p.toLowerCase().includes(q) || k.includes(q)) ? '' : 'none';
  });
  document.querySelectorAll('details').forEach(el => {
    const v = el.querySelector('.ff:not([style*="display: none"])');
    el.style.display = (!v && q) ? 'none' : '';
  });
}

// ═══ MODULES ═══
async function rm() {
  try {
    const d = await api('/modules/list'), mods = d.modules||[];
    let h = `<div class="cd"><h2>📦 已安装模块 (${mods.length})</h2>
      <div class="sr"><input id="ms" placeholder="🔍 搜索..." oninput="fm()"><button onclick="im()">+ 安装</button></div>
      <div id="ml"><table><tr><th>模块</th><th>类型</th><th>操作</th></tr>`;
    if (!mods.length) h += '<tr><td colspan="3" style="color:var(--muted)">暂无</td></tr>';
    else mods.forEach(m => {
      h += `<tr data-m="${es(m.name)}"><td><strong>${es(m.name)}</strong></td><td style="color:var(--muted)">${es(m.type||'?')}</td><td>
        <button class="sm gr" onclick="vm('${ej(m.name)}')">查看</button>
        <button class="sm dg" onclick="um('${ej(m.name)}')">卸载</button>
      </td></tr>`;
    });
    h += '</table></div></div>';
    document.getElementById('pn-md').innerHTML = h;
  } catch(e) { document.getElementById('pn-md').innerHTML = `<div class="cd">❌ ${es(e.message)}</div>`; }
}

function fm() {
  const q = (document.getElementById('ms')?.value||'').toLowerCase();
  document.querySelectorAll('#ml tr[data-m]').forEach(tr => {
    tr.style.display = tr.getAttribute('data-m')?.toLowerCase().includes(q) ? '' : 'none';
  });
}

function im() {
  const u = prompt('模块下载 URL 或名称：');
  if (!u) return;
  nf('安装中...','ok');
  api('/modules/install', {url:u}).then(r => {
    nf(r.ok?'安装成功！请重载模块':'错误: '+(r.error||'?'), r.ok?'ok':'err');
    if (r.ok) rm();
  }).catch(e => nf(e.message,'err'));
}

function vm(name) {
  alert('模块: '+name+'\\n\\n请使用控制台 qqdeps module info '+name+' 查看详情。');
}

async function um(name) {
  if (!confirm('确认卸载模块 "'+name+'"？此操作不可恢复。')) return;
  try {
    const r = await api('/modules/uninstall', {name:name});
    nf(r.ok?'模块已卸载':'错误: '+(r.error||'?'), r.ok?'ok':'err');
    if (r.ok) rm();
  } catch(e) { nf(e.message,'err'); }
}

// ═══ USERS ═══
async function ru() {
  try {
    const d = await api('/users/list'), us = d.users||[];
    let h = `<div class="cd"><h2>👤 管理用户 (${us.length})</h2>
      <div class="sr"><span></span><button onclick="au()">+ 添加用户</button></div>
      <table><tr><th>用户名</th><th>创建时间</th><th>操作</th></tr>`;
    if (!us.length) h += '<tr><td colspan="3" style="color:var(--muted)">暂无用户</td></tr>';
    else us.forEach(u => {
      h += `<tr><td><strong>${es(u.name)}</strong></td><td style="color:var(--muted)">${es(u.created||'?')}</td><td>
        <button class="sm dg" onclick="du('${ej(u.name)}')">删除</button></td></tr>`;
    });
    h += '</table></div>';
    document.getElementById('pn-us').innerHTML = h;
  } catch(e) { document.getElementById('pn-us').innerHTML = `<div class="cd">❌ ${es(e.message)}</div>`; }
}

function au() {
  const u = prompt('用户名：'); if (!u) return;
  const p = prompt('密码：'); if (!p) return;
  api('/users/add', {username:u, password:p}).then(r => {
    nf(r.ok?'用户已添加':'错误: '+(r.error||'?'), r.ok?'ok':'err');
    if (r.ok) ru();
  }).catch(e => nf(e.message,'err'));
}

async function du(name) {
  if (!confirm('确认删除用户 "'+name+'"?此操作不可恢复。')) return;
  try { const r = await api('/users/delete', {username:name}); nf(r.ok?'已删除':'错误: '+(r.error||'?'), r.ok?'ok':'err'); if(r.ok) ru(); }
  catch(e) { nf(e.message,'err'); }
}

// ═══ INIT ═══
if (tk) { api('/auth/check').then(d => { if (d.ok) sa(); else sh(); }).catch(()=>sh()); }
else sh();
setInterval(() => { if (document.getElementById('ap').classList.contains('on')) ra(); }, 15000);
</script></body></html>"""

# ═══════════════════════════════════════════════
# HTTP 处理器
# ═══════════════════════════════════════════════
class _H(http.server.BaseHTTPRequestHandler):
    provider: Any = None  # set by module

    def log_message(self, f, *a): _log.debug("panel %s %s", self.command, f % a)

    def _ok(self, d: dict, code=200):
        b = json.dumps(d, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def _auth(self) -> Optional[str]:
        t = self.headers.get("X-Token", "")
        if self.provider:
            return self.provider._sessions.ok(t)
        return None

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        if n < 1: return {}
        try:
            return json.loads(self.rfile.read(min(n, 65536)).decode())
        except Exception:
            return {}

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(_HTML.encode()); return
        if p.startswith("/api/"):
            return self._api_get(p[5:])
        self.send_error(404)

    def do_POST(self):
        p = urlparse(self.path).path
        if p.startswith("/api/"):
            return self._api_post(p[5:])
        self.send_error(404)

    def _api_get(self, p):
        if p == "dashboard":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.provider._dashboard_data())
        if p == "config":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.provider._config_data())
        if p == "modules/list":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.provider._module_list())
        if p == "users/list":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.provider._user_list())
        if p == "auth/check":
            u = self._auth()
            if u: return self._ok({"ok": True, "username": u})
            return self._ok({"ok": False}, 401)
        self.send_error(404)

    def _api_post(self, p):
        body = self._body()
        if p == "auth/login":
            return self._handle_login(body)
        if p == "auth/register":
            return self._handle_register(body)
        if p == "auth/logout":
            t = self.headers.get("X-Token", "")
            if self.provider: self.provider._sessions.rm(t)
            return self._ok({"ok": True})
        if p == "config/save":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self.provider._config_save(body)
        if p == "config/reload":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self.provider._config_reload()
        if p == "modules/install":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self.provider._module_install(body)
        if p == "modules/uninstall":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self.provider._module_uninstall(body)
        if p == "users/add":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self.provider._user_add(body)
        if p == "users/delete":
            u = self._auth()
            if not u: return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self.provider._user_delete(body)
        self.send_error(404)

    def _handle_login(self, body):
        u = body.get("username", "").strip()
        p = body.get("password", "")
        ip = self.headers.get('X-Forwarded-For', self.headers.get('X-Real-IP', '0.0.0.0')).split(',')[0].strip()
        if not u or not p:
            return self._ok({"ok": False, "error": "请输入用户名和密码"})
        if self.provider._sessions._check_bruteforce(ip):
            return self._ok({"ok": False, "error": "登录失败次数过多，请 15 分钟后重试"})
        if not self.provider._users.chk(u, p):
            self.provider._sessions._record_fail(ip)
            return self._ok({"ok": False, "error": "用户名或密码错误"})
        self.provider._sessions._clear_fails(ip)
        t = self.provider._sessions.mk(u)
        return self._ok({"ok": True, "token": t})

    def _handle_register(self, body):
        u = body.get("username", "").strip()
        p = body.get("password", "")
        if len(u) < 3 or len(u) > 32: return self._ok({"ok": False, "error": "用户名需 3-32 字符"})
        if len(p) < 6: return self._ok({"ok": False, "error": "密码至少 6 位"})
        if not self.provider._users.add(u, p): return self._ok({"ok": False, "error": "用户名已存在"})
        return self._ok({"ok": True})


# ═══════════════════════════════════════════════
# 模块入口
# ═══════════════════════════════════════════════
class PanelModule(Module):
    name = "webpanel"; tier = 300  # TIER_APP; version = (2, 0, 0)
    default_config = {"管理面板": {"端口": 8381, "地址": "127.0.0.1"}}

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._sessions = Sessions()
        self._users: Optional[Users] = None
        self._httpd = None; self._t = None; self._start = 0.0

    async def on_init(self):
        # 用户数据库
        udir = self.data_dir
        os.makedirs(udir, exist_ok=True)
        self._users = Users(os.path.join(udir, "users.json"))
        port = self.config.get("管理面板.端口", 8381)
        host = self.config.get("管理面板.地址", "127.0.0.1")

        _H.provider = self
        self._httpd = http.server.HTTPServer((host, port), _H)
        self._t = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._start = time.time()
        try:
            self._t.start()
            _log.info("📊 管理面板: http://%s:%d", host, port)
        except OSError as e:
            _log.error("面板启动失败 (端口%d可能被占用): %s", port, e)

    async def on_stop(self):
        if self._httpd: self._httpd.shutdown()
        if self._t and self._t.is_alive(): self._t.join(timeout=3)

    # ═══ 数据接口 ═══
    def _dashboard_data(self):
        s = {"uptime": self._uptime(), "module_count": 0, "service_count": 0,
             "ai_sessions": 0, "ban_count": 0, "ws_connected": False}
        mods = []; svcs = []
        try:
            # 模块
            host = self._find_host()
            if host:
                for m in getattr(host, '_modules', []):
                    mods.append({"name": getattr(m, 'name', '?'),
                        "uid": getattr(m, 'uid', 400),
                        "version": '.'.join(str(v) for v in getattr(m, 'version', (0,0,1))),
                        "active": getattr(m, 'enabled', True),
                        "commands": len(getattr(m, '_commands', {}))})
                s["module_count"] = len(mods)
            # 服务
            for sn, su in self.services.list_accessible().items():
                try:
                    o = self.services.try_get(sn)
                    svcs.append({"name": sn, "uid": su, "kind": type(o).__name__ if o else ''})
                except Exception: svcs.append({"name": sn, "uid": su, "kind": '?'})
            s["service_count"] = len(svcs)
            # AI
            ai = self.services.try_get("ai_core")
            if ai: s["ai_sessions"] = len(getattr(ai, 'conversations', {}))
            # 封禁
            orion = self.services.try_get("orion_bridge")
            if orion:
                st = getattr(orion, '_store', None)
                if st: s["ban_count"] = len(st.list_all())
            # WS
            ws = self.services.try_get("ws_client")
            if ws: s["ws_connected"] = getattr(ws, 'available', False)
        except Exception as e:
            _log.debug("面板数据采集: %s", e)
        return {"ok": True, "stats": s, "modules": mods, "services": svcs}

    def _config_data(self):
        try:
            cfg = self.services.get("config")
            d = getattr(cfg, '_data', {})
            return {"ok": True, "config": dict(d), "file": getattr(cfg, '_file_path', '?')}
        except Exception: return {"ok": True, "config": {}, "file": '?'}

    def _config_save(self, body):
        changes = body.get("changes", {})
        if not changes: return {"ok": False, "error": "无更改"}
        try:
            cfg = self.services.get("config")
            for k, v in changes.items():
                cfg.set(k, v)
            cfg.save()
            return {"ok": True}
        except Exception as e: return {"ok": False, "error": str(e)}

    def _config_reload(self):
        try:
            cfg = self.services.get("config")
            cfg.reload()
            return {"ok": True}
        except Exception as e: return {"ok": False, "error": str(e)}

    def _module_list(self):
        from ...core.drivers.autodiscover import list_external_modules
        try:
            mods = list_external_modules(self.services.get("config").data_dir)
            return {"ok": True, "modules": mods}
        except Exception as e: return {"ok": False, "error": str(e)}

    def _module_install(self, body):
        url = body.get("url", "").strip()
        if not url: return {"ok": False, "error": "请输入 URL"}
        try:
            from ...core.drivers.autodiscover import download_module
            r = download_module(url, self.services.get("config").data_dir)
            if r: return {"ok": True, "name": r}
            return {"ok": False, "error": "下载失败，请检查 URL"}
        except Exception as e: return {"ok": False, "error": str(e)}

    def _module_uninstall(self, body):
        name = body.get("name", "").strip()
        if not name: return {"ok": False, "error": "请输入模块名"}
        try:
            from ...core.drivers.autodiscover import remove_external_module
            r = remove_external_module(name, self.services.get("config").data_dir)
            if r: return {"ok": True}
            return {"ok": False, "error": "模块不存在"}
        except Exception as e: return {"ok": False, "error": str(e)}

    def _user_list(self):
        if not self._users: return {"ok": True, "users": []}
        us = []
        for u in self._users.ls():
            us.append({"name": u, "created": str(self._users._u.get(u, {}).get("ts", "?"))})
        return {"ok": True, "users": us}

    def _user_add(self, body):
        u = body.get("username", "").strip()
        p = body.get("password", "")
        if not u or not p: return {"ok": False, "error": "用户名和密码不能为空"}
        if not self._users: return {"ok": False, "error": "用户系统未初始化"}
        if self._users.add(u, p): return {"ok": True}
        return {"ok": False, "error": "用户名已存在"}

    def _user_delete(self, body):
        u = body.get("username", "").strip()
        if not u: return {"ok": False, "error": "请输入用户名"}
        if not self._users: return {"ok": False, "error": "用户系统未初始化"}
        if self._users.rm(u): return {"ok": True}
        return {"ok": False, "error": "用户不存在"}

    def _uptime(self):
        s = int(time.time() - self._start) if self._start else 0
        return f"{s//3600}h {(s%3600)//60}m"

    def _find_host(self):
        try:
            a = self.services.get("adapter")
            return getattr(a, '_host', None)
        except Exception: return None
