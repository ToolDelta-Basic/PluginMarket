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
    """QQ 群消息事件。

    Attributes:
        user_id: 发送者 QQ 号。
        group_id: 群号。
        nickname: 发送者昵称。
        message: 消息文本。
        raw_data: 原始消息数据。
        handled: 是否已被命令路由处理。
    """

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

    pass


@dataclass
class SystemStopEvent(BaseEvent):
    """框架停止事件。"""

    pass
    