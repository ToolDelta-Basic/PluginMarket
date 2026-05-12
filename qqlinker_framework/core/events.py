# core/events.py
"""框架标准事件定义"""
import time
from dataclasses import dataclass, field
from typing import Optional, Any, Dict


@dataclass
class BaseEvent:
    """所有事件的基类，包含时间戳。"""

    timestamp: float = field(default_factory=time.time, init=False)


@dataclass
class GroupMessageEvent(BaseEvent):
    """QQ 群消息事件。"""

    user_id: int
    group_id: int
    nickname: str
    message: str
    raw_data: Dict[str, Any] = field(default_factory=dict)
    handled: bool = field(default=False, init=False)


@dataclass
class PrivateMessageEvent(BaseEvent):
    """QQ 私聊消息事件。"""

    user_id: int
    nickname: str
    message: str
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GameChatEvent(BaseEvent):
    """游戏内聊天事件。"""

    player_name: str
    message: str


@dataclass
class PlayerJoinEvent(BaseEvent):
    """玩家加入游戏事件。"""

    player_name: str


@dataclass
class PlayerLeaveEvent(BaseEvent):
    """玩家离开游戏事件。"""

    player_name: str


@dataclass
class AIResponseEvent(BaseEvent):
    """AI 响应事件，可用于二次分发。"""

    user_id: int
    group_id: int
    reply: str
    media: Optional[str] = None
    should_forward_to_game: bool = True


@dataclass
class SystemStartEvent(BaseEvent):
    """框架启动事件。"""


@dataclass
class SystemStopEvent(BaseEvent):
    """框架停止事件。"""


@dataclass
class PlayerPositionEvent(BaseEvent):
    """玩家坐标更新事件，data 为 {玩家名: {x, y, z, yRot, dimension}}"""

    positions: Dict[str, Dict[str, float]]

@dataclass
class AIPrePromptReflectionEvent(BaseEvent):
    """AI 输入前的前提性反思事件。"""

    user_id: int
    group_id: int
    message: str
    # 监听器可返回补充提示文本（str），框架将注入至 system 消息前
    supplement: Optional[str] = field(default=None, init=False)


@dataclass
class AIPostResponseReflectionEvent(BaseEvent):
    """AI 输出后的合规性反思事件。"""

    user_id: int
    group_id: int
    reply: str
    original_message: str
    # 监听器可返回一段违规通知文本，框架将追加到会话历史中
    warning: Optional[str] = field(default=None, init=False)
