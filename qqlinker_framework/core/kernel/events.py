# core/events.py
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any, Dict


@dataclass
class BaseEvent:
    """所有事件的基类。

    Attributes:
        timestamp: 事件创建时间戳（自动生成）。
        priority: lane 内优先级。正值 = 更高优先，0 = 默认。
        event_id: 事件唯一标识（自动生成）。
        reply_to: 跨 lane 追踪链 — 当前事件由哪个事件触发。
    """

    timestamp: float = field(default_factory=time.time, init=False, repr=False)
    priority: int = field(default=0, init=False, repr=False)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12], init=False, repr=False)
    reply_to: Optional[str] = field(default=None, init=False, repr=False)


# ═══════════════════════════════════════════════════════════
# chat lane — QQ 群/私聊消息
# ═══════════════════════════════════════════════════════════

@dataclass
class GroupMessageEvent(BaseEvent):
    """QQ 群消息事件 → chat lane"""

    lane = "chat"

    user_id: int
    group_id: int
    nickname: str
    message: str
    raw_data: Dict[str, Any] = field(default_factory=dict)
    handled: bool = field(default=False, init=False)


@dataclass
class PrivateMessageEvent(BaseEvent):
    """QQ 私聊消息事件 → chat lane"""

    lane = "chat"

    user_id: int
    nickname: str
    message: str
    raw_data: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
# realtime lane — 游戏实时事件
# ═══════════════════════════════════════════════════════════

@dataclass
class GameChatEvent(BaseEvent):
    """游戏内聊天事件 → realtime lane"""

    lane = "realtime"

    player_name: str
    message: str


@dataclass
class PlayerJoinEvent(BaseEvent):
    """玩家加入游戏事件 → realtime lane"""

    lane = "realtime"

    player_name: str


@dataclass
class PlayerLeaveEvent(BaseEvent):
    """玩家离开游戏事件 → realtime lane"""

    lane = "realtime"

    player_name: str


@dataclass
class PlayerPositionEvent(BaseEvent):
    """玩家坐标更新事件 → realtime lane"""

    lane = "realtime"

    positions: Dict[str, Dict[str, float]]


# ═══════════════════════════════════════════════════════════
# ai lane — AI 处理事件（慢车道）
# ═══════════════════════════════════════════════════════════

@dataclass
class AIResponseEvent(BaseEvent):
    """AI 响应事件 → ai lane"""

    lane = "ai"

    user_id: int
    group_id: int
    reply: str
    media: Optional[str] = None
    should_forward_to_game: bool = True


@dataclass
class AIPrePromptReflectionEvent(BaseEvent):
    """AI 输入前的前提性反思事件 → ai lane"""

    lane = "ai"

    user_id: int
    group_id: int
    message: str
    supplement: Optional[str] = field(default=None, init=False)


@dataclass
class AIPostResponseReflectionEvent(BaseEvent):
    """AI 输出后的合规性反思事件 → ai lane"""

    lane = "ai"

    user_id: int
    group_id: int
    reply: str
    original_message: str
    warning: Optional[str] = field(default=None, init=False)


# ═══════════════════════════════════════════════════════════
# critical lane — 系统关键事件
# ═══════════════════════════════════════════════════════════

@dataclass
class SystemStartEvent(BaseEvent):
    """框架启动事件 → critical lane"""

    lane = "critical"


@dataclass
class SystemStopEvent(BaseEvent):
    """框架停止事件 → critical lane"""

    lane = "critical"


@dataclass
class SystemPanicEvent(BaseEvent):
    """系统恐慌事件 → critical lane"""

    lane = "critical"

    service: str
    reason: str = ""


# ═══════════════════════════════════════════════════════════
# admin lane — 管理事件
# ═══════════════════════════════════════════════════════════

@dataclass
class ConfigReloadEvent(BaseEvent):
    """配置热重载事件 → admin lane"""

    lane = "admin"
