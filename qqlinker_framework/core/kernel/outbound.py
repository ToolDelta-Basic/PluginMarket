from dataclasses import dataclass, field
from typing import Optional

from .events import BaseEvent


@dataclass
class OutboundMessageEvent(BaseEvent):
    """跨 lane 发送消息事件 → chat lane

    chat lane 收到后根据 target_type 执行对应的发送方法。
    """

    lane = "chat"

    target_type: str
    """发送目标类型: 'group' | 'private'"""

    target_id: int
    """目标 ID（群号或 QQ 号）"""

    content: str
    """消息文本内容"""

    media: Optional[str] = None
    """可选的媒体 URL"""

    # 追踪链: 此事件由哪个事件触发
    # reply_to 继承自 BaseEvent
