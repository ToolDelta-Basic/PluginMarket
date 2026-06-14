"""统一审计日志基础设施。

提供:
  - audit_log(): 记录关键操作到审计日志文件
  - AuditLevel: 审计严重级别

所有关键操作（封禁、解封、grant、exec、approve、sudo、配置修复、命令执行）
统一通过此模块记录。
"""
import hashlib  # noqa: F811 — sha256 used for args_hash
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, Optional

_log = logging.getLogger(__name__)

# ── 审计级别 ──────────────────────────────────────────────


class AuditLevel(IntEnum):
    """审计严重级别。"""
    INFO = 0       # 普通操作
    WARNING = 1    # 需关注的操作
    CRITICAL = 2   # 严重操作（如 grant uid=0 尝试）


_LEVEL_LABELS = {
    AuditLevel.INFO: "INFO",
    AuditLevel.WARNING: "WARNING",
    AuditLevel.CRITICAL: "CRITICAL",
}

# ── 单例审计器 ────────────────────────────────────────────


class _AuditLogger:
    """线程安全的审计日志写入器。

    内建轮转: 到达 max_lines 时自动截断保留后半部分。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._file_path: Optional[str] = None
        self._max_lines: int = 100_000
        self._cleanup_interval: int = 86400  # 默认每天检查一次
        self._last_cleanup: float = 0.0
        self._initialized: bool = False

    def configure(
        self,
        file_path: str,
        max_lines: int = 100_000,
        cleanup_interval: int = 86400,
    ) -> None:
        """配置审计日志文件路径和轮转参数。

        Args:
            file_path: 审计日志文件绝对路径。
            max_lines: 最大行数，超出后截断保留后半。
            cleanup_interval: 清理间隔秒数。
        """
        with self._lock:
            self._file_path = file_path
            self._max_lines = max(max_lines, 1000)  # 最少保留 1000 行
            self._cleanup_interval = max(cleanup_interval, 60)
            self._initialized = True
            dirname = os.path.dirname(file_path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)

    def log(
        self,
        sender: str,
        action: str,
        target: str = "",
        detail: str = "",
        level: AuditLevel = AuditLevel.INFO,
        group_id: int = 0,
    ) -> None:
        """写入一条审计日志记录。

        Args:
            sender: 操作人标识（QQ号、模块名等）。
            action: 操作类型（如 "grant"、"ban"、"exec"）。
            target: 操作目标（被操作的用户、玩家等）。
            detail: 附加详情。
            level: 审计级别。
            group_id: 来源群号。
        """
        if not self._initialized or not self._file_path:
            _log.warning("审计日志未配置，丢弃记录: %s %s", action, target)
            return

        now = time.time()
        ts = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
        try:
            sender_int = int(sender)
        except (ValueError, TypeError):
            sender_int = 0

        entry = json.dumps(
            {
                "timestamp": ts,
                "unix": int(now),
                "level": _LEVEL_LABELS.get(level, "INFO"),
                "sender": str(sender),
                "sender_int": sender_int,
                "action": str(action),
                "target": str(target),
                "detail": str(detail)[:1000],
                "group_id": int(group_id),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

        with self._lock:
            try:
                with open(self._file_path, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
            except OSError as e:
                _log.error("审计日志写入失败: %s", e)

        # 定期清理
        if now - self._last_cleanup > self._cleanup_interval:
            self._maybe_rotate()

    def log_exec(
        self,
        caller_uid: int,
        module_name: str,
        method_name: str,
        args_hash: str,
    ) -> None:
        """专用的 .exec 审计记录。

        Args:
            caller_uid: 调用者 UID。
            module_name: 目标模块名。
            method_name: 目标方法名。
            args_hash: 参数的 SHA256 哈希。
        """
        self.log(
            sender=str(caller_uid),
            action="exec",
            target=f"{module_name}.{method_name}",
            detail=f"args_hash={args_hash}",
            level=AuditLevel.WARNING,
        )

    def _maybe_rotate(self) -> None:
        """检查行数并在超出 max_lines 时截断。"""
        if not self._file_path:
            return
        self._last_cleanup = time.time()
        try:
            if not os.path.exists(self._file_path):
                return
            with open(self._file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) <= self._max_lines:
                return
            # 保留后半部分
            keep = lines[-self._max_lines // 2:]
            tmp = self._file_path + ".rotate.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(keep)
            os.replace(tmp, self._file_path)
            _log.info(
                "审计日志已轮转: %d → %d 行",
                len(lines), len(keep),
            )
        except OSError as e:
            _log.error("审计日志轮转失败: %s", e)


# ── 全局单例 ──────────────────────────────────────────────

_audit = _AuditLogger()


def configure_audit(
    file_path: str,
    max_lines: int = 100_000,
    cleanup_interval: int = 86400,
) -> None:
    """配置全局审计日志。应在框架启动时调用。"""
    _audit.configure(file_path, max_lines, cleanup_interval)


def audit_log(
    sender: str,
    action: str,
    target: str = "",
    detail: str = "",
    level: AuditLevel = AuditLevel.INFO,
    group_id: int = 0,
) -> None:
    """写入审计日志（便捷方法）。"""
    _audit.log(
        sender=str(sender),
        action=str(action),
        target=str(target),
        detail=str(detail),
        level=level,
        group_id=int(group_id),
    )


def audit_log_exec(
    caller_uid: int,
    module_name: str,
    method_name: str,
    args: Any,
) -> None:
    """记录 .exec 调用审计日志。

    参数被哈希化以保护隐私，同时仍可用于事后关联分析。
    """
    args_str = json.dumps(args, ensure_ascii=False, sort_keys=True)
    args_hash = hashlib.sha256(args_str.encode("utf-8")).hexdigest()[:16]
    _audit.log_exec(caller_uid, module_name, method_name, args_hash)


def get_audit_file_path() -> Optional[str]:
    """返回当前审计日志文件路径。"""
    return _audit._file_path
