"""适配器桥接库 — 平台回调 → 信道事件发布。

将 WS 消息回调转换为统一的信道事件，通过 EventBus 发布。
同时将消息队列的发送回调绑定到 WS 客户端。

依赖: ws_client
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict

from ..channel_host import Library

_log = logging.getLogger(__name__)


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
    """游戏内聊天事件。"""
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


class AdapterBridgeLibrary(Library):
    """适配器桥接库。"""

    name = "adapter_bridge"
    version = "1.6.0"
    dependencies = ["ws_client"]

    async def mount(self) -> None:
        import asyncio
        self._loop = asyncio.get_running_loop()

        ws_client = self.services.try_get("ws_client")
        message_queue = self.services.try_get("message")

        # 绑定 WS 消息回调 → 事件发布
        if ws_client:
            ws_client.set_message_callback(self._on_ws_message)

        # 绑定消息队列发送回调 → WS 客户端
        if message_queue and ws_client:
            def send_cb(msg_type, target, text):
                if msg_type == "group":
                    ws_client.send_group_msg(target, text)
                else:
                    ws_client.send_private_msg(target, text)
            message_queue.set_send_callback(send_cb)

    async def unmount(self) -> None:
        pass

    def _on_ws_message(self, data: dict) -> None:
        """WS 消息回调 — 解析后发布到事件总线。"""
        post_type = data.get("post_type", "")

        if post_type == "message":
            msg_type = data.get("message_type", "")
            if msg_type == "group":
                event = GroupMessageEvent(
                    user_id=data.get("user_id", 0),
                    group_id=data.get("group_id", 0),
                    nickname=data.get("sender", {}).get("nickname", ""),
                    message=data.get("raw_message", data.get("message", "")),
                    raw_data=data,
                )
                # 跨线程发布到事件总线
                if self._loop and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(
                        asyncio.ensure_future,
                        self.events.publish("GroupMessageEvent", event, source="adapter_bridge")
                    )
