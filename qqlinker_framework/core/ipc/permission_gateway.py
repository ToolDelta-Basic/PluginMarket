"""IPC 权限网关 — 速率限制 + MID 检查 + 命令过滤 + 审计。

提供 PermissionGateway 作为 IPC Server 的核心安全组件，
在命令到达执行层之前进行完整的权限校验链。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional, Tuple

from .command_filter import check_command_safety

__all__ = [
    "PermissionGateway",
    "TokenBucket",
]


# ─── RPC 方法定义 ─────────────────────────────────────────────────────────────

# method_name → { min_mid: int, rate_key: str }
RPC_METHODS: Dict[str, Dict[str, Any]] = {
    # 命令执行
    "sendcmd": {"min_mid": 0, "rate_key": "sendcmd"},
    "sendcmd_wait": {"min_mid": 0, "rate_key": "sendcmd"},
    "send_ws_cmd": {"min_mid": 0, "rate_key": "sendcmd"},
    # 物品/传送（更严格的速率）
    "give": {"min_mid": 0, "rate_key": "give"},
    "tp": {"min_mid": 0, "rate_key": "tp"},
    "teleport": {"min_mid": 0, "rate_key": "tp"},
    # 消息发送
    "send_group_msg": {"min_mid": 100, "rate_key": "send_group_msg"},
    "send_private_msg": {"min_mid": 100, "rate_key": "send_private_msg"},
    # 查询（宽松）
    "get_player_list": {"min_mid": 0, "rate_key": "query"},
    "get_scoreboard": {"min_mid": 0, "rate_key": "query"},
    "get_server_info": {"min_mid": 0, "rate_key": "query"},
    # 事件订阅
    "subscribe": {"min_mid": 0, "rate_key": "subscribe"},
    "unsubscribe": {"min_mid": 0, "rate_key": "subscribe"},
}

# 命令类方法（需要进入 command_filter 检查）
_COMMAND_METHODS: set[str] = {"sendcmd", "sendcmd_wait", "send_ws_cmd"}


# ─── 速率限制器 ───────────────────────────────────────────────────────────────

# rate_key → (capacity, refill_per_second)
_RATE_CONFIGS: Dict[str, Tuple[int, float]] = {
    "sendcmd": (30, 30.0 / 60.0),  # 30次/分钟
    "give": (10, 10.0 / 60.0),  # 10次/分钟
    "tp": (5, 5.0 / 60.0),  # 5次/分钟
    "send_group_msg": (20, 20.0 / 60.0),  # 20次/分钟
    "send_private_msg": (5, 5.0 / 60.0),  # 5次/分钟
    "query": (60, 60.0 / 60.0),  # 60次/分钟
    "subscribe": (10, 10.0 / 60.0),  # 10次/分钟
}


class TokenBucket:
    """令牌桶速率限制器。

    基于经典令牌桶算法：
    - 桶有最大容量 capacity
    - 以 refill_rate (tokens/sec) 持续补充
    - 每次请求消耗 1 个令牌
    - 令牌不足时拒绝请求
    """

    __slots__ = ("capacity", "refill_rate", "_tokens", "_last_refill")

    def __init__(self, capacity: int, refill_rate: float) -> None:
        """
        Args:
            capacity: 桶的最大令牌数
            refill_rate: 每秒补充的令牌数
        """
        self.capacity: int = capacity
        self.refill_rate: float = refill_rate
        self._tokens: float = float(capacity)
        self._last_refill: float = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """尝试消耗令牌。

        Returns:
            True 如果有足够令牌（已消耗），False 如果不足（未消耗）。
        """
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        """根据经过时间补充令牌。"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(
                self.capacity, self._tokens + elapsed * self.refill_rate
            )
            self._last_refill = now

    @property
    def available(self) -> float:
        """当前可用令牌数（近似值）。"""
        self._refill()
        return self._tokens


# ─── 审计日志 ──────────────────────────────────────────────────────────────────


class _AuditLog:
    """简单的 JSONL 审计日志。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path
        self._fd: Any = None
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
            self._fd = open(path, "a", encoding="utf-8")  # noqa: SIM115

    def record(
        self,
        method: str,
        caller_mid: int,
        params_summary: str,
        allowed: bool,
        reason: str = "",
    ) -> None:
        """写入一条审计记录。"""
        entry = {
            "ts": time.time(),
            "method": method,
            "caller_mid": caller_mid,
            "params_summary": params_summary[:100],
            "allowed": allowed,
            "reason": reason,
        }
        if self._fd:
            self._fd.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._fd.flush()

    def close(self) -> None:
        """关闭日志文件。"""
        if self._fd:
            self._fd.close()
            self._fd = None


# ─── 权限网关 ──────────────────────────────────────────────────────────────────


class PermissionGateway:
    """IPC 权限网关 — 统一安全检查入口。

    检查顺序：
    1. method 是否在 RPC_METHODS 中
    2. caller_mid 是否满足 min_mid 要求
    3. 速率限制检查
    4. 如果是 sendcmd 类方法，进入命令过滤
    5. 审计记录

    Usage:
        gw = PermissionGateway(audit_path="/var/log/qqlinker/audit.jsonl")
        allowed, reason = gw.check_permission("sendcmd", {"cmd": "/give @p diamond 64"}, caller_mid=200)
    """

    def __init__(self, audit_path: Optional[str] = None) -> None:
        self._rate_limiters: Dict[str, TokenBucket] = {}
        self._audit_log = _AuditLog(audit_path)

    def check_permission(
        self, method: str, params: dict, caller_mid: int
    ) -> Tuple[bool, str]:
        """完整权限检查链。

        Args:
            method: RPC 方法名
            params: 调用参数
            caller_mid: 调用方模块 ID

        Returns: (allowed, denial_reason)
        """
        params_summary = str(params)[:100] if params else ""

        # 1. 方法存在性检查
        method_config = RPC_METHODS.get(method)
        if method_config is None:
            reason = f"unknown method '{method}'"
            self._audit_log.record(method, caller_mid, params_summary, False, reason)
            return (False, reason)

        # 2. MID 最低要求检查
        min_mid = method_config["min_mid"]
        if caller_mid < min_mid:
            reason = f"method '{method}' requires min_mid={min_mid}, caller has mid={caller_mid}"
            self._audit_log.record(method, caller_mid, params_summary, False, reason)
            return (False, reason)

        # 3. 速率限制
        rate_key = method_config["rate_key"]
        bucket = self._get_bucket(rate_key, caller_mid)
        if not bucket.consume():
            reason = f"rate limit exceeded for '{rate_key}' (mid={caller_mid})"
            self._audit_log.record(method, caller_mid, params_summary, False, reason)
            return (False, reason)

        # 4. 命令过滤（仅 sendcmd 类方法）
        if method in _COMMAND_METHODS:
            cmd = params.get("cmd") or params.get("command") or ""
            if cmd:
                allowed, reason = self._check_command(cmd, caller_mid)
                if not allowed:
                    self._audit_log.record(method, caller_mid, params_summary, False, reason)
                    return (False, reason)

        # 5. 通过 — 记录审计
        self._audit_log.record(method, caller_mid, params_summary, True)
        return (True, "")

    def _check_command(self, cmd: str, caller_mid: int) -> Tuple[bool, str]:
        """命令级安全检查（委托给 command_filter）。"""
        return check_command_safety(cmd, caller_mid)

    def _get_bucket(self, rate_key: str, caller_mid: int) -> TokenBucket:
        """获取指定 rate_key + mid 的令牌桶（按模块隔离）。"""
        bucket_id = f"{rate_key}:{caller_mid}"
        if bucket_id not in self._rate_limiters:
            config = _RATE_CONFIGS.get(rate_key, (30, 0.5))
            self._rate_limiters[bucket_id] = TokenBucket(
                capacity=config[0], refill_rate=config[1]
            )
        return self._rate_limiters[bucket_id]

    def close(self) -> None:
        """关闭网关资源。"""
        self._audit_log.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
