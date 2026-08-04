import logging
import os
import time

from ..channel_host import Library

_log = logging.getLogger(__name__)


class RecoveryEngine:
    """递归重启防护。"""

    def __init__(self, data_path: str, max_restarts: int = 3, window_seconds: float = 60.0):
        self._blocked_path = os.path.join(data_path, ".restart_blocked")
        self._max = max_restarts
        self._window = window_seconds

    def check_restart_guard(self) -> bool:
        """检查是否应该阻止启动。返回 True 表示允许。"""
        if os.path.isfile(self._blocked_path):
            return False
        return True

    def get_blocked_path(self) -> str:
        return self._blocked_path


class RecoveryLibrary(Library):
    """恢复引擎库。"""

    name = "recovery"
    version = "1.6.0"
    dependencies = ["config_store"]

    async def mount(self) -> None:
        data_path = self.services.get("_data_path")
        engine = RecoveryEngine(data_path)
        if not engine.check_restart_guard():
            _log.critical("递归重启防护已激活")
        self.services.register("recovery", engine, mid=100)

    async def unmount(self) -> None:
        pass
