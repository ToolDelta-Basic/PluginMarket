"""双向消息转发模块：游戏↔QQ群。"""
import asyncio
import hashlib
from ...core.module import Module
from ...core.events import (
    GameChatEvent,
    GroupMessageEvent,
    PlayerJoinEvent,
    PlayerLeaveEvent,
)
from ...services.dedup import LayeredDedup


class GameForwarder(Module):
    """负责游戏聊天与QQ群消息的双向转发，以及加入/离开提示。"""

    name = "game_forwarder"
    version = (1, 0, 0)
    required_services = ["message", "config", "adapter"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self.dedup: LayeredDedup = services.get("dedup")

    async def on_init(self):
        """注册配置节并订阅事件。"""

        async def _dbg_stats():
            """调试端点。"""
            return str(self.dedup.get_stats())

        try:
            debug = self.services.get("debug")
            await debug.register_module(
                self.name, {"stats": _dbg_stats}
            )
        except KeyError:
            pass

        self.config.register_section("消息转发", {
            "游戏到群": {
                "是否启用": True,
                "转发格式": "<{player}> {message}",
                "屏蔽以下字符串开头的消息": [".", "。"],
                "仅转发以下字符串开头的消息": [],
            },
            "群到游戏": {
                "是否启用": True,
                "转发格式": "§7[QQ] {nickname}§7: {message}",
                "屏蔽以下字符串开头的消息": [],
            },
            "链接的群聊": [963953936],
            "转发玩家进退提示": True,
        })

        self.listen("GameChatEvent", self.on_game_chat)
        self.listen(
            "GroupMessageEvent", self.on_group_message, priority=-10
        )
        self.listen("PlayerJoinEvent", self.on_player_join)
        self.listen("PlayerLeaveEvent", self.on_player_leave)

    def _get_linked_groups(self) -> list[int]:
        """获取配置中链接的群号列表。"""
        groups = self.config.get("消息转发.链接的群聊", [])
        try:
            return [
                int(g) for g in groups if isinstance(g, (int, str))
            ]
        except (ValueError, TypeError):
            return []

    async def on_game_chat(self, event: GameChatEvent):
        """将游戏聊天消息转发到所有链接的QQ群。"""
        cfg = self.config.get("消息转发.游戏到群", {})
        if not cfg.get("是否启用", True):
            return
        msg = event.message.strip()
        allow_prefixes = cfg.get("仅转发以下字符串开头的消息", [])
        block_prefixes = cfg.get("屏蔽以下字符串开头的消息", [])
        if allow_prefixes:
            if not any(msg.startswith(p) for p in allow_prefixes):
                return
        else:
            if any(msg.startswith(p) for p in block_prefixes):
                return

        # 稳定哈希避免 PYTHONHASHSEED 随机化导致去重失效
        name_bytes = event.player_name.encode()
        player_hash = int(
            hashlib.sha256(name_bytes).hexdigest()[:8], 16
        )
        if not self.dedup.check_and_add_content(
            msg, player_hash
        ):
            return

        template = cfg.get("转发格式", "<{player}> {message}")
        text = template.replace("{player}", event.player_name).replace(
            "{message}", msg
        )
        for gid in self._get_linked_groups():
            await self.message.send_group(gid, text)

    async def on_group_message(self, event: GroupMessageEvent):
        """将QQ群消息转发到游戏公屏。"""
        groups = self._get_linked_groups()
        if event.group_id not in groups:
            return
        if event.handled:
            return
        cfg = self.config.get("消息转发.群到游戏", {})
        if not cfg.get("是否启用", True):
            return
        msg = event.message.strip()
        block_prefixes = cfg.get("屏蔽以下字符串开头的消息", [])
        if any(msg.startswith(p) for p in block_prefixes):
            return

        msg_id = event.raw_data.get("message_id")
        if not msg_id or not self.dedup.check_and_add_id(str(msg_id)):
            return

        template = cfg.get("转发格式", "§7[QQ] {nickname}§7: {message}")
        text = template.replace("{nickname}", event.nickname).replace(
            "{message}", msg
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self.adapter.send_game_message, "@a", text
        )

    async def on_player_join(self, event: PlayerJoinEvent):
        """转发玩家加入游戏提示。"""
        if not self.config.get("消息转发.转发玩家进退提示", True):
            return
        for gid in self._get_linked_groups():
            await self.message.send_group(
                gid, f"{event.player_name} 加入了游戏"
            )

    async def on_player_leave(self, event: PlayerLeaveEvent):
        """转发玩家离开游戏提示。"""
        if not self.config.get("消息转发.转发玩家进退提示", True):
            return
        for gid in self._get_linked_groups():
            await self.message.send_group(
                gid, f"{event.player_name} 离开了游戏"
            )
