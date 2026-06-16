"""GameProxy — 框架端游戏操作代理（通过 IPC 转发到宿主）。

在 --ipc-mode 下，模块通过 GameProxy 执行游戏指令。
GameProxy 内嵌权限检查（PermissionGateway），再将合法请求序列化后通过 IPC 发往宿主。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .command_filter import check_command_safety

logger = logging.getLogger(__name__)

__all__ = ["GameProxy", "PermissionGateway"]


# ═══════════════════════════════════════════════════════════
# PermissionGateway — 权限网关
# ═══════════════════════════════════════════════════════════

# RPC 方法权限表：method → 最小允许 mid（越小权限越高）
# mid=0 核心, mid=100 守护, mid=300 应用, mid=400 nobody
RPC_METHODS: dict[str, int] = {
    "sendcmd": 100,          # 发送游戏命令 — 至少 daemon 级
    "sendcmd_raw": 0,        # 原始命令（无过滤）— 仅核心
    "send_group_msg": 300,   # 发群消息 — 应用级
    "send_private_msg": 300, # 发私聊 — 应用级
    "get_online_players": 400,  # 获取在线玩家 — 任何人
    "player_list": 400,      # 玩家列表 — 任何人
    "ping": 400,             # 心跳 — 任何人
}

# 速率限制配置（每秒最大调用次数）
RATE_LIMITS: dict[str, int] = {
    "sendcmd": 30,
    "sendcmd_raw": 10,
    "send_group_msg": 20,
    "send_private_msg": 10,
}


class PermissionGateway:
    """权限网关 — 检查 mid 权限 + 命令安全过滤 + 速率限制。"""

    def __init__(self) -> None:
        # 速率追踪: method → [timestamps]
        self._call_times: dict[str, list[float]] = {}

    def check_permission(self, method: str, caller_mid: int) -> tuple[bool, str]:
        """检查调用者是否有权限调用指定方法。

        Returns: (allowed, reason)
        """
        required_mid = RPC_METHODS.get(method)
        if required_mid is None:
            return (False, f"unknown method '{method}'")

        if caller_mid > required_mid:
            return (False, f"permission denied: mid={caller_mid} cannot call '{method}' (requires mid<={required_mid})")

        return (True, "")

    def check_rate_limit(self, method: str) -> tuple[bool, str]:
        """检查速率限制。

        Returns: (allowed, reason)
        """
        limit = RATE_LIMITS.get(method)
        if limit is None:
            return (True, "")

        now = time.time()
        times = self._call_times.setdefault(method, [])

        # 滑动窗口：保留最近 1 秒内的调用
        cutoff = now - 1.0
        times[:] = [t for t in times if t > cutoff]

        if len(times) >= limit:
            return (False, f"rate limit exceeded for '{method}': {limit}/s")

        times.append(now)
        return (True, "")

    def check_command(self, method: str, params: dict, caller_mid: int) -> tuple[bool, str]:
        """综合检查：权限 + 速率 + 命令安全。

        Returns: (allowed, reason)
        """
        # 1. 权限检查
        allowed, reason = self.check_permission(method, caller_mid)
        if not allowed:
            return (False, reason)

        # 2. 速率限制
        allowed, reason = self.check_rate_limit(method)
        if not allowed:
            return (False, reason)

        # 3. 命令安全检查（仅对 sendcmd 生效，sendcmd_raw 跳过）
        if method == "sendcmd":
            cmd = params.get("cmd", "")
            allowed, reason = check_command_safety(cmd, caller_mid)
            if not allowed:
                return (False, reason)

        return (True, "")


# ═══════════════════════════════════════════════════════════
# GameProxy — 框架端代理
# ═══════════════════════════════════════════════════════════

class GameProxy:
    """框架端游戏操作代理。

    模块通过此代理发送游戏命令，所有操作经过 PermissionGateway 过滤后
    通过 IPC 转发到宿主进程执行。
    """

    def __init__(self, ipc_client: Any, caller_mid: int = 300) -> None:
        self._client = ipc_client
        self._mid = caller_mid
        self._gateway = PermissionGateway()

    def send_command(self, cmd: str) -> Any:
        """发送游戏命令（经过权限 + 安全过滤）。"""
        params = {"cmd": cmd}
        allowed, reason = self._gateway.check_command("sendcmd", params, self._mid)
        if not allowed:
            logger.warning("GameProxy.send_command blocked: %s", reason)
            return {"ok": False, "error": reason}
        return self._client.call("sendcmd", params, self._mid)

    def send_command_raw(self, cmd: str) -> Any:
        """发送原始命令（无安全过滤，仅 mid=0 可用）。"""
        params = {"cmd": cmd}
        allowed, reason = self._gateway.check_command("sendcmd_raw", params, self._mid)
        if not allowed:
            logger.warning("GameProxy.send_command_raw blocked: %s", reason)
            return {"ok": False, "error": reason}
        return self._client.call("sendcmd_raw", params, self._mid)

    def get_online_players(self) -> Any:
        """获取在线玩家列表。"""
        params = {}
        allowed, reason = self._gateway.check_command("get_online_players", params, self._mid)
        if not allowed:
            return {"ok": False, "error": reason}
        return self._client.call("get_online_players", params, self._mid)
