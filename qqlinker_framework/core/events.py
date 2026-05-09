# core/events.py
"""框架标准事件定义"""
import time
from dataclasses import dataclass, field
from typing import Optional, Any, Dict

@dataclass
class BaseEvent:
    timestamp: float = field(default_factory=time.time, init=False)

@dataclass
class GroupMessageEvent(BaseEvent):
    user_id: int
    group_id: int
    nickname: str
    message: str
    raw_data: Dict[str, Any] = field(default_factory=dict)
    handled: bool = field(default=False, init=False)

@dataclass
class PrivateMessageEvent(BaseEvent):
    user_id: int
    nickname: str
    message: str
    raw_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GameChatEvent(BaseEvent):
    player_name: str
    message: str

@dataclass
class PlayerJoinEvent(BaseEvent):
    player_name: str

@dataclass
class PlayerLeaveEvent(BaseEvent):
    player_name: str

@dataclass
class AIResponseEvent(BaseEvent):
    user_id: int
    group_id: int
    reply: str
    media: Optional[str] = None
    should_forward_to_game: bool = True

@dataclass
class SystemStartEvent(BaseEvent):
    pass

@dataclass
class SystemStopEvent(BaseEvent):
    pass