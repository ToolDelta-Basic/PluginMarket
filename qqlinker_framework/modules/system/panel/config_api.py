# modules/system/panel/config_api.py
# QQLinker 管理面板 — 配置管理 API
from __future__ import annotations
import logging
from typing import Any

_log = logging.getLogger(__name__)


class ConfigAPI:
    """配置文件的读取、保存和重载。"""

    def __init__(self, services: Any):
        self._services = services

    def get_config(self) -> dict:
        """获取当前配置数据。"""
        try:
            cfg = self._services.get("config")
            d = getattr(cfg, '_data', {})
            return {"ok": True, "config": dict(d), "file": getattr(cfg, '_file_path', '?')}
        except Exception:
            return {"ok": True, "config": {}, "file": '?'}

    def save_config(self, changes: dict) -> dict:
        """保存配置项更改。"""
        if not changes:
            return {"ok": False, "error": "无更改"}
        try:
            cfg = self._services.get("config")
            for k, v in changes.items():
                cfg.set(k, v)
            cfg.save()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reload_config(self) -> dict:
        """从磁盘重新加载配置。"""
        try:
            cfg = self._services.get("config")
            cfg.reload()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
