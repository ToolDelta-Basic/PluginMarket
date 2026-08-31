# modules/system/panel/module_api.py
# QQLinker 管理面板 — 模块安装/卸载 API
from __future__ import annotations
import logging
from typing import Any

_log = logging.getLogger(__name__)


class ModuleAPI:
    """外部模块的查询、安装和卸载。"""

    def __init__(self, services: Any):
        self._services = services

    def list_modules(self) -> dict:
        """列出已安装的外部模块。"""
        try:
            from ...core.drivers.autodiscover import list_external_modules
            cfg = self._services.get("config")
            mods = list_external_modules(cfg.data_dir)
            return {"ok": True, "modules": mods}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def install_module(self, url: str) -> dict:
        """从 URL 下载并安装模块。"""
        if not url:
            return {"ok": False, "error": "请输入 URL"}
        try:
            from ...core.drivers.autodiscover import download_module
            cfg = self._services.get("config")
            r = download_module(url, cfg.data_dir)
            if r:
                return {"ok": True, "name": r}
            return {"ok": False, "error": "下载失败，请检查 URL"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def uninstall_module(self, name: str) -> dict:
        """卸载指定模块。"""
        if not name:
            return {"ok": False, "error": "请输入模块名"}
        try:
            from ...core.drivers.autodiscover import remove_external_module
            cfg = self._services.get("config")
            r = remove_external_module(name, cfg.data_dir)
            if r:
                return {"ok": True}
            return {"ok": False, "error": "模块不存在"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
