# modules/system/panel/__init__.py
# QQLinker 管理面板 — 模块化 Web UI
from __future__ import annotations
import logging, os, time
from typing import Any, Optional

try:
    from ...core.module import Module
except ImportError:
    Module = object  # fallback for standalone testing

from .auth import AuthManager
from .config_api import ConfigAPI
from .dashboard import DashboardAPI
from .module_api import ModuleAPI
from .server import PanelServer

_log = logging.getLogger(__name__)

__all__ = [
    'PanelModule',
    'PanelServer',
    'AuthManager',
    'ConfigAPI',
    'ModuleAPI',
    'DashboardAPI',
]


# ═══════════════════════════════════════════════
# PanelModule
# ═══════════════════════════════════════════════
class PanelModule(Module):
    """Web 管理面板模块。"""
    name = "webpanel"
    mid = 300
    tier = 300  # TIER_APP
    version = (2, 0, 0)
    background = True  # must preload: runs HTTP server in on_init, has no commands/triggers
    default_config = {"管理面板": {"端口": 8381, "地址": "127.0.0.1"}}

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        # API 组件
        self._auth_mgr: Optional[AuthManager] = None
        self._dashboard = DashboardAPI(services)
        self._config = ConfigAPI(services)
        self._modules = ModuleAPI(services)
        # 服务器
        self._server: Optional[PanelServer] = None

    async def on_init(self):
        # 用户数据库
        udir = self.data_dir
        os.makedirs(udir, exist_ok=True)
        self._auth_mgr = AuthManager(os.path.join(udir, "users.json"))

        port = self.config.get("管理面板.端口", 8381)
        host = self.config.get("管理面板.地址", "127.0.0.1")

        start_ts = time.time()
        self._dashboard.set_start_time(start_ts)

        self._server = PanelServer(host, port, self)
        try:
            self._server.start()
            _log.info("📊 管理面板: http://%s:%d", host, port)
        except OSError as e:
            _log.error("面板启动失败 (端口%d可能被占用): %s", port, e)

    async def on_stop(self):
        if self._server:
            self._server.stop()

    # ═══ 用户管理（需要 auth_mgr） ═══
    def _user_list(self) -> dict:
        if not self._auth_mgr:
            return {"ok": True, "users": []}
        us = []
        for u in self._auth_mgr.users.ls():
            us.append({
                "name": u,
                "created": str(self._auth_mgr.users._u.get(u, {}).get("ts", "?")),
            })
        return {"ok": True, "users": us}

    def _user_add(self, body: dict) -> dict:
        u = body.get("username", "").strip()
        p = body.get("password", "")
        if not u or not p:
            return {"ok": False, "error": "用户名和密码不能为空"}
        if not self._auth_mgr:
            return {"ok": False, "error": "用户系统未初始化"}
        if self._auth_mgr.users.add(u, p):
            return {"ok": True}
        return {"ok": False, "error": "用户名已存在"}

    def _user_delete(self, body: dict) -> dict:
        u = body.get("username", "").strip()
        if not u:
            return {"ok": False, "error": "请输入用户名"}
        if not self._auth_mgr:
            return {"ok": False, "error": "用户系统未初始化"}
        if self._auth_mgr.users.rm(u):
            return {"ok": True}
        return {"ok": False, "error": "用户不存在"}
