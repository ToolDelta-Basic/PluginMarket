import logging
import os
import time
from enum import IntEnum
from typing import Any, Optional

from ..channel_host import Library

_log = logging.getLogger("audit")


class AuditLevel(IntEnum):
    """审计级别。"""
    DEBUG = 0
    INFO = 1
    WARNING = 2
    CRITICAL = 3


class AuditService:
    """审计日志服务。"""

    def __init__(self, log_dir: str):
        self._log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._logger = logging.getLogger("audit")

        # 确保文件 handler
        log_file = os.path.join(log_dir, "audit.log")
        if not any(
            isinstance(h, logging.FileHandler)
            and getattr(h, 'baseFilename', '') == os.path.abspath(log_file)
            for h in self._logger.handlers
        ):
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._logger.addHandler(fh)
        self._logger.setLevel(logging.DEBUG)

    def log(self, message: str, *,
            level: AuditLevel = AuditLevel.INFO,
            module: str = "",
            user_id: int = 0,
            extra: Optional[dict] = None) -> None:
        """记录审计日志。"""
        prefix = f"[{module}]" if module else ""
        user_tag = f" user={user_id}" if user_id else ""
        text = f"{prefix}{user_tag} {message}"
        if extra:
            text += f" | {extra}"
        self._logger.log(level * 10 + 10, text)

    def log_exec(self, module: str, method: str, user_id: int = 0,
                 args: str = "", result: str = "") -> None:
        """记录命令执行审计。"""
        self.log(
            f"EXEC {module}.{method}({args}) → {result[:200]}",
            level=AuditLevel.INFO,
            module=module,
            user_id=user_id,
        )

    # ── 兼容旧接口 ──
    AuditLevel = AuditLevel


class AuditLibrary(Library):
    """审计日志库。"""

    name = "audit"
    version = "1.6.0"
    dependencies = ["config_store"]

    async def mount(self) -> None:
        data_path = self.services.get("_data_path")
        log_dir = os.path.join(data_path, "日志")
        svc = AuditService(log_dir)
        self.services.register("audit", svc, mid=400)  # 所有模块可访问

    async def unmount(self) -> None:
        pass
