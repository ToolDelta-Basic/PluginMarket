# modules/system/panel/dashboard.py
# QQLinker 管理面板 — 仪表盘 API
from __future__ import annotations
import logging, time
from typing import Any, Dict, List

_log = logging.getLogger(__name__)


class DashboardAPI:
    """仪表盘数据采集 API。"""

    def __init__(self, services: Any):
        self._services = services
        self._start: float = 0.0

    def set_start_time(self, ts: float):
        self._start = ts

    def get_data(self) -> dict:
        """返回完整的仪表盘数据。"""
        s: Dict[str, Any] = {
            "uptime": self._uptime(),
            "module_count": 0,
            "service_count": 0,
            "ai_sessions": 0,
            "ban_count": 0,
            "ws_connected": False,
        }
        mods: List[dict] = []
        svcs: List[dict] = []
        try:
            # 模块
            host = self._find_host()
            if host:
                for m in getattr(host, '_modules', []):
                    mods.append({
                        "name": getattr(m, 'name', '?'),
                        "uid": getattr(m, 'uid', 400),
                        "version": '.'.join(str(v) for v in getattr(m, 'version', (0, 0, 1))),
                        "active": getattr(m, 'enabled', True),
                        "commands": len(getattr(m, '_commands', {})),
                    })
                s["module_count"] = len(mods)
            # 服务
            for sn, su in self._services.list_accessible().items():
                try:
                    o = self._services.try_get(sn)
                    svcs.append({"name": sn, "uid": su, "kind": type(o).__name__ if o else ''})
                except Exception:
                    svcs.append({"name": sn, "uid": su, "kind": '?'})
            s["service_count"] = len(svcs)
            # AI
            ai = self._services.try_get("ai_core")
            if ai:
                s["ai_sessions"] = len(getattr(ai, 'conversations', {}))
            # 封禁
            orion = self._services.try_get("orion_bridge")
            if orion:
                st = getattr(orion, '_store', None)
                if st:
                    s["ban_count"] = len(st.list_all())
            # WS
            ws = self._services.try_get("ws_client")
            if ws:
                s["ws_connected"] = getattr(ws, 'available', False)
        except Exception as e:
            _log.debug("面板数据采集: %s", e)
        return {"ok": True, "stats": s, "modules": mods, "services": svcs}

    def _uptime(self) -> str:
        s = int(time.time() - self._start) if self._start else 0
        return f"{s // 3600}h {(s % 3600) // 60}m"

    def _find_host(self):
        try:
            a = self._services.get("adapter")
            return getattr(a, '_host', None)
        except Exception:
            return None
