"""协议定义库 — 公共常量 + 事件类型 + UID 层级。

注册服务: "protocol"
依赖: 无

模块通过 self.services.get("protocol") 获取所有公共定义，
不需要 import 任何框架内部模块。
"""
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..channel_host import Library


# ═══════════════════════════════════════════════════════════
# UID / 权限层级常量
# ═══════════════════════════════════════════════════════════

TIER_KERNEL = 0
TIER_DAEMON = 100
TIER_SERVICE = 200
TIER_APP = 300
UID_NOBODY = 400

_UID_LABELS = {
    0: "kernel",
    100: "daemon",
    200: "service",
    300: "app",
    400: "nobody",
}


def uid_label(uid: int) -> str:
    """返回 UID 层级名称。"""
    if uid <= 0:
        return "kernel"
    if uid <= 100:
        return "daemon"
    if uid <= 200:
        return "service"
    if uid <= 300:
        return "app"
    return "nobody"


# ═══════════════════════════════════════════════════════════
# 事件类型定义
# ═══════════════════════════════════════════════════════════

@dataclass
class GroupMessageEvent:
    """群聊消息事件。"""
    user_id: int = 0
    group_id: int = 0
    nickname: str = ""
    message: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    handled: bool = field(default=False, init=False)
    timestamp: float = field(default_factory=time.time, init=False)


@dataclass
class GameChatEvent:
    """游戏内聊天消息事件。"""
    player_name: str = ""
    message: str = ""
    handled: bool = field(default=False, init=False)
    timestamp: float = field(default_factory=time.time, init=False)


@dataclass
class PlayerJoinEvent:
    """玩家加入事件。"""
    player_name: str = ""
    handled: bool = field(default=False, init=False)
    timestamp: float = field(default_factory=time.time, init=False)


@dataclass
class PlayerLeaveEvent:
    """玩家离开事件。"""
    player_name: str = ""
    handled: bool = field(default=False, init=False)
    timestamp: float = field(default_factory=time.time, init=False)


@dataclass
class ConfigReloadEvent:
    """配置重载事件。"""
    section: str = ""
    handled: bool = field(default=False, init=False)
    timestamp: float = field(default_factory=time.time, init=False)


@dataclass
class AIPrePromptReflectionEvent:
    """​AI 输入前的前提性反思事件。"""
    user_id: int = 0
    group_id: int = 0
    message: str = ""
    supplement: Optional[str] = None
    handled: bool = field(default=False, init=False)
    timestamp: float = field(default_factory=time.time, init=False)


@dataclass
class AIPostResponseReflectionEvent:
    """​AI 输出后的合规性反思事件。"""
    user_id: int = 0
    group_id: int = 0
    reply: str = ""
    original_message: str = ""
    warning: Optional[str] = None
    handled: bool = field(default=False, init=False)
    timestamp: float = field(default_factory=time.time, init=False)


@dataclass
class SystemStopEvent:
    """系统停止事件。"""
    reason: str = ""
    handled: bool = field(default=False, init=False)
    timestamp: float = field(default_factory=time.time, init=False)


# ═══════════════════════════════════════════════════════════
# Protocol 服务对象
# ═══════════════════════════════════════════════════════════

class Protocol:
    """公共协议服务 — 所有模块共享的常量和类型定义。

    使用方式:
        proto = self.services.get("protocol")
        if uid == proto.UID_NOBODY: ...
        isinstance(event, proto.GroupMessageEvent)
    """

    # ── 常量 ──
    TIER_KERNEL = TIER_KERNEL
    TIER_DAEMON = TIER_DAEMON
    TIER_SERVICE = TIER_SERVICE
    TIER_APP = TIER_APP
    UID_NOBODY = UID_NOBODY
    MID_KERNEL = TIER_KERNEL
    MID_DAEMON = TIER_DAEMON

    # ── 事件类型 ──
    GroupMessageEvent = GroupMessageEvent
    GameChatEvent = GameChatEvent
    PlayerJoinEvent = PlayerJoinEvent
    PlayerLeaveEvent = PlayerLeaveEvent
    ConfigReloadEvent = ConfigReloadEvent
    SystemStopEvent = SystemStopEvent
    AIPrePromptReflectionEvent = AIPrePromptReflectionEvent
    AIPostResponseReflectionEvent = AIPostResponseReflectionEvent

    # ── 工具方法 ──
    uid_label = staticmethod(uid_label)


# ═══════════════════════════════════════════════════════════
# Library
# ═══════════════════════════════════════════════════════════

class ProtocolLibrary(Library):
    """协议定义库。"""

    name = "protocol"
    version = "1.6.0"
    dependencies: list = []

    async def mount(self) -> None:
        proto = Protocol()
        self.services.register("protocol", proto, mid=400)  # 所有模块可访问

    async def unmount(self) -> None:
        pass
