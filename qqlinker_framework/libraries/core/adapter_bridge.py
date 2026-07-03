import asyncio
import logging
from typing import Any

from ..channel_host import Library
from ...core.kernel.events import (
    GroupMessageEvent, GameChatEvent, PlayerJoinEvent, PlayerLeaveEvent,
)

_log = logging.getLogger(__name__)


class AdapterBridgeLibrary(Library):
    """适配器桥接库 — 双向事件转发。

    QQ→Game: WS 消息 → GroupMessageEvent → 事件总线
    Game→QQ: 适配器事件 → GameChatEvent/PlayerJoinEvent/PlayerLeaveEvent → 事件总线
    发送回调: 消息队列 → ws_client
    """

    name = "adapter_bridge"
    version = "1.6.1"
    dependencies = ["ws_client"]

    async def mount(self) -> None:
        self._loop = asyncio.get_running_loop()

        ws_client = self.services.try_get("ws_client")
        message_queue = self.services.try_get("message")
        adapter = self.services.try_get("adapter")

        # ── QQ→Game: WS 消息 → 事件总线 ──
        if ws_client:
            ws_client.set_message_callback(self._on_ws_message)

        # ── Game→QQ: 消息队列 → ws_client 发送 ──
        if message_queue and ws_client:
            def send_cb(msg_type, target, text):
                if msg_type == "group":
                    ws_client.send_group_msg(target, text)
                else:
                    ws_client.send_private_msg(target, text)
            message_queue.set_send_callback(send_cb)

        # ── Game→QQ: 适配器事件 → 事件总线 ──
        if adapter:
            if hasattr(adapter, "listen_game_chat"):
                adapter.listen_game_chat(self._on_game_chat)
            if hasattr(adapter, "listen_player_join"):
                adapter.listen_player_join(self._on_player_join)
            if hasattr(adapter, "listen_player_leave"):
                adapter.listen_player_leave(self._on_player_leave)

    async def unmount(self) -> None:
        pass

    # ── QQ→Game ─────────────────────────────────────────────

    def _on_ws_message(self, data: dict) -> None:
        """WS 消息回调 — 解析后发布 GroupMessageEvent 到事件总线。

        仅处理配置中 "消息转发.链接的群聊" 中指定的群。
        WS 回调运行在后台线程，无模块 CallContext，显式传入 requester_uid=0。
        """
        post_type = data.get("post_type", "")
        if post_type != "message":
            return
        msg_type = data.get("message_type", "")
        if msg_type != "group":
            return

        group_id = data.get("group_id", 0)

        # 群白名单过滤
        config = self.services.try_get("config")
        if config is not None:
            linked_groups = config.get("消息转发.链接的群聊", [], requester_uid=0)
            linked_set = {int(g) for g in linked_groups}
            if group_id not in linked_set:
                return

        event = GroupMessageEvent(
            user_id=data.get("user_id", 0),
            group_id=group_id,
            nickname=data.get("sender", {}).get("nickname", ""),
            message=data.get("raw_message", data.get("message", "")),
            raw_data=data,
        )
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(
                asyncio.ensure_future,
                self.events.publish(event),
            )

    # ── Game→QQ ─────────────────────────────────────────────

    def _on_game_chat(self, player_name: str, msg: str) -> None:
        """游戏聊天 → GameChatEvent → 事件总线。"""
        event = GameChatEvent(player_name=player_name, message=msg)
        asyncio.run_coroutine_threadsafe(
            self.events.publish(event), self._loop,
        )

    def _on_player_join(self, player_name: str) -> None:
        """玩家加入 → PlayerJoinEvent → 事件总线。"""
        event = PlayerJoinEvent(player_name=player_name)
        asyncio.run_coroutine_threadsafe(
            self.events.publish(event), self._loop,
        )

    def _on_player_leave(self, player_name: str) -> None:
        """玩家离开 → PlayerLeaveEvent → 事件总线。"""
        event = PlayerLeaveEvent(player_name=player_name)
        asyncio.run_coroutine_threadsafe(
            self.events.publish(event), self._loop,
        )
