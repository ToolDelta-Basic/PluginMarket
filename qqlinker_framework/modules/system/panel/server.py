# modules/system/panel/server.py
# QQLinker 管理面板 — HTTP 服务器与请求路由
from __future__ import annotations
import http.server, json, logging, mimetypes, os, threading
from typing import Any, Optional
from urllib.parse import urlparse

_log = logging.getLogger(__name__)

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_MIME: dict = mimetypes.types_map.copy()


class PanelRequestHandler(http.server.BaseHTTPRequestHandler):
    """Web 面板 HTTP 请求处理器。"""

    module: Any = None  # set by PanelServer (PanelModule instance)

    def log_message(self, f, *a):
        _log.debug("panel %s %s", self.command, f % a)

    # ── 响应工具 ──
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
        if self.module:
            return self.module._auth_mgr.sessions.ok(t)
        return None

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        if n < 1:
            return {}
        try:
            return json.loads(self.rfile.read(min(n, 65536)).decode())
        except Exception:
            return {}

    # ── 静态文件 ──
    def _serve_static(self, path: str):
        """安全地提供 static/ 目录下的静态文件。"""
        fname = os.path.basename(os.path.normpath(path))
        fpath = os.path.join(_STATIC_DIR, fname)
        if not os.path.isfile(fpath):
            self.send_error(404)
            return
        ext = os.path.splitext(fname)[1].lower()
        mime = _MIME.get(ext, "application/octet-stream")
        with open(fpath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    # ── 路由 ──
    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            return self._serve_static("index.html")
        if p.startswith("/static/"):
            return self._serve_static(p[8:])
        if p.startswith("/api/"):
            return self._api_get(p[5:])
        self.send_error(404)

    def do_POST(self):
        p = urlparse(self.path).path
        if p.startswith("/api/"):
            return self._api_post(p[5:])
        self.send_error(404)

    # ── API GET ──
    def _api_get(self, p: str):
        if p == "dashboard":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._dashboard.get_data())
        if p == "config":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._config.get_config())
        if p == "modules/list":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._modules.list_modules())
        if p == "users/list":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._user_list())
        if p == "auth/check":
            u = self._auth()
            if u:
                return self._ok({"ok": True, "username": u})
            return self._ok({"ok": False}, 401)
        self.send_error(404)

    # ── API POST ──
    def _api_post(self, p: str):
        body = self._body()
        if p == "auth/login":
            return self._handle_login(body)
        if p == "auth/register":
            return self._handle_register(body)
        if p == "auth/logout":
            t = self.headers.get("X-Token", "")
            if self.module:
                self.module._auth_mgr.sessions.rm(t)
            return self._ok({"ok": True})
        if p == "config/save":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._config.save_config(body.get("changes", {})))
        if p == "config/reload":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._config.reload_config())
        if p == "modules/install":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._modules.install_module(body.get("url", "").strip()))
        if p == "modules/uninstall":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._modules.uninstall_module(body.get("name", "").strip()))
        if p == "users/add":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._user_add(body))
        if p == "users/delete":
            u = self._auth()
            if not u:
                return self._ok({"ok": False, "error": "unauthorized"}, 401)
            return self._ok(self.module._user_delete(body))
        self.send_error(404)

    # ── 登录/注册 ──
    def _handle_login(self, body: dict):
        u = body.get("username", "").strip()
        p = body.get("password", "")
        ip = self.headers.get(
            'X-Forwarded-For',
            self.headers.get('X-Real-IP', '0.0.0.0')
        ).split(',')[0].strip()
        if not u or not p:
            return self._ok({"ok": False, "error": "请输入用户名和密码"})
        auth = self.module._auth_mgr
        if auth.sessions._check_bruteforce(ip):
            return self._ok({"ok": False, "error": "登录失败次数过多，请 15 分钟后重试"})
        if not auth.users.chk(u, p):
            auth.sessions._record_fail(ip)
            return self._ok({"ok": False, "error": "用户名或密码错误"})
        auth.sessions._clear_fails(ip)
        t = auth.sessions.mk(u)
        return self._ok({"ok": True, "token": t})

    def _handle_register(self, body: dict):
        u = body.get("username", "").strip()
        p = body.get("password", "")
        if len(u) < 3 or len(u) > 32:
            return self._ok({"ok": False, "error": "用户名需 3-32 字符"})
        if len(p) < 6:
            return self._ok({"ok": False, "error": "密码至少 6 位"})
        if not self.module._auth_mgr.users.add(u, p):
            return self._ok({"ok": False, "error": "用户名已存在"})
        return self._ok({"ok": True})


# ═══════════════════════════════════════════════
# PanelServer
# ═══════════════════════════════════════════════
class PanelServer:
    """管理面板 HTTP 服务器封装。"""

    def __init__(self, host: str, port: int, module: Any):
        PanelRequestHandler.module = module
        self._httpd = http.server.HTTPServer((host, port), PanelRequestHandler)
        self._thread: Optional[threading.Thread] = None

    @property
    def httpd(self):
        return self._httpd

    def start(self):
        """在后台线程中启动服务器。"""
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        """关闭服务器。"""
        if self._httpd:
            self._httpd.shutdown()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
