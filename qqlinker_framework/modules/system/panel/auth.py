# modules/system/panel/auth.py
# QQLinker 管理面板 — 认证与会话管理
from __future__ import annotations
import hashlib, hmac, json, os, secrets, threading, time
from typing import Dict, List, Optional

# ═══════════════════════════════════════════════
# 密码哈希
# ═══════════════════════════════════════════════
_ITERS = 200000
_HLEN = 32
_SLEN = 16


def hash_password(pw: str) -> str:
    """PBKDF2-SHA256 密码哈希。"""
    s = secrets.token_hex(_SLEN)
    d = hashlib.pbkdf2_hmac('sha256', pw.encode(), s.encode(), _ITERS, _HLEN)
    return f"$pbkdf2${_ITERS}${s}${d.hex()}"


def check_password(pw: str, stored: str) -> bool:
    """校验密码。"""
    try:
        _, _, n, s, h = stored.split('$', 4)
        d = hashlib.pbkdf2_hmac('sha256', pw.encode(), s.encode(), int(n), _HLEN)
        return hmac.compare_digest(d.hex(), h)
    except Exception:
        return False


# ═══════════════════════════════════════════════
# 会话管理器（含爆破保护）
# ═══════════════════════════════════════════════
class Sessions:
    """会话管理器，含爆破保护。"""

    def __init__(self):
        self._m: Dict[str, dict] = {}
        self._ttl = 86400
        self._login_fails: Dict[str, List[float]] = {}  # ip → [ts, ts, ...]
        self._max_fails = 5
        self._fail_window = 900  # 15 分钟

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
        """创建新会话令牌。"""
        self._gc()
        t = secrets.token_hex(32)
        self._m[t] = {"u": u, "ts": time.time()}
        return t

    def ok(self, t: str) -> Optional[str]:
        """验证会话令牌，返回用户名或 None。"""
        self._gc()
        s = self._m.get(t)
        if not s or time.time() - s["ts"] > self._ttl:
            return None
        return s["u"]

    def rm(self, t: str):
        """删除会话令牌。"""
        self._m.pop(t, None)

    def _gc(self):
        n = time.time()
        for t in [t for t, s in self._m.items() if n - s["ts"] > self._ttl]:
            del self._m[t]


# ═══════════════════════════════════════════════
# 用户数据库
# ═══════════════════════════════════════════════
class Users:
    """用户数据库管理器。"""

    def __init__(self, fp: str):
        self._p = fp
        self._u: dict = {}
        self._lk = threading.Lock()
        if os.path.exists(fp):
            try:
                with open(fp) as f:
                    self._u = json.load(f)
            except Exception:
                self._u = {}

    def _sv(self):
        os.makedirs(os.path.dirname(self._p) or '.', exist_ok=True)
        t = self._p + '.tmp'
        with open(t, 'w') as f:
            json.dump(self._u, f, ensure_ascii=False, indent=2)
        os.replace(t, self._p)

    def add(self, u: str, p: str) -> bool:
        """添加用户。"""
        with self._lk:
            if u in self._u:
                return False
            self._u[u] = {"pw": hash_password(p), "ts": time.time()}
            self._sv()
            return True

    def chk(self, u: str, p: str) -> bool:
        """校验用户密码。"""
        with self._lk:
            if u not in self._u:
                return False
            return check_password(p, self._u[u].get("pw", ""))

    def ls(self) -> List[str]:
        """列出所有用户名。"""
        with self._lk:
            return sorted(self._u.keys())

    def rm(self, u: str) -> bool:
        """删除用户。"""
        with self._lk:
            if u not in self._u:
                return False
            del self._u[u]
            self._sv()
            return True


# ═══════════════════════════════════════════════
# AuthManager — 聚合 Sessions + Users
# ═══════════════════════════════════════════════
class AuthManager:
    """认证管理器，聚合会话和用户管理。"""

    def __init__(self, users_db_path: str):
        self.sessions = Sessions()
        self.users = Users(users_db_path)
