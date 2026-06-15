"""
AdapterBridgeLibrary – 平台适配器 → 信道事件桥接

将适配器（adapter）的原生回调转换为统一的 ChannelEvent，
通过 self.events 发布到事件总线，供其他 Library 订阅。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.library import Library
from ..core.channel import ChannelEvent


# ── 信道事件定义 ──────────────────────────────────────────────


@dataclass
class GroupMessageEvent(ChannelEvent):
    """群聊消息（来自 WS / 适配器回调）。"""
    user_id: int = 0
    group_id: int = 0
    nickname: str = ""
    message: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameChatEvent(ChannelEvent):
    """游戏内聊天消息。"""
    player_name: str = ""
    message: str = ""


@dataclass
class PlayerJoinEvent(ChannelEvent):
    """玩家加入游戏事件。"""
    player_name: str = ""


@dataclass
class PlayerLeaveEvent(ChannelEvent):
    """玩家离开游戏事件。"""
    player_name: str = ""


# ── Library 实现 ──────────────────────────────────────────────


class AdapterBridgeLibrary(Library):
    name = "adapter_bridge"
    version = "1.0.0"
    dependencies = ["core"]

    async def mount(self) -> None:
        adapter = self.services.try_get("adapter")
        if not adapter:
            return

        # WS 消息回调 → GroupMessageEvent
        ws_client = self.services.try_get("ws_client")
        if ws_client and hasattr(ws_client, "set_message_callback"):
            ws_client.set_message_callback(self._on_ws_message)

        # 适配器原生回调
        if hasattr(adapter, "listen_group_message"):
            adapter.listen_group_message(self._on_ws_message)
        if hasattr(adapter, "listen_game_chat"):
            adapter.listen_game_chat(self._on_game_chat)
        if hasattr(adapter, "listen_player_join"):
            adapter.listen_player_join(self._on_player_join)
        if hasattr(adapter, "listen_player_leave"):
            adapter.listen_player_leave(self._on_player_leave)

    # ── 回调处理 ───────────────────────────────────────────

    async def _on_ws_message(self, data: dict[str, Any]) -> None:
        await self.events.publish(
            GroupMessageEvent(
                user_id=data.get("user_id", 0),
                group_id=data.get("group_id", 0),
                nickname=data.get("nickname", ""),
                message=data.get("message", ""),
                raw_data=data,
            ),
            source=self.name,
        )

    async def _on_game_chat(self, player: str, msg: str) -> None:
        await self.events.publish(
            GameChatEvent(player_name=player, message=msg),
            source=self.name,
        )

    async def _on_player_join(self, player: str) -> None:
        await self.events.publish(
            PlayerJoinEvent(player_name=player),
            source=self.name,
        )

    async def _on_player_leave(self, player: str) -> None:
        await self.events.publish(
            PlayerLeaveEvent(player_name=player),
            source=self.name,
        )
