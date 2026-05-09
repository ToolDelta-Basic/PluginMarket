# modules/game_forwarder.py
from ..core.module import Module
from ..events import GameChatEvent, GroupMessageEvent, PlayerJoinEvent, PlayerLeaveEvent
from ..services.dedup import LayeredDedup

class GameForwarder(Module):
    name = "game_forwarder"
    version = (1, 0, 0)
    required_services = ["message", "config", "adapter"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self.dedup: LayeredDedup = services.get("dedup")

    async def on_init(self):
        self.config.register_section("消息转发", {
            "游戏到群": {
                "是否启用": True,
                "转发格式": "<{player}> {message}",
                "屏蔽以下字符串开头的消息": [".", "。"],
                "仅转发以下字符串开头的消息": []
            },
            "群到游戏": {
                "是否启用": True,
                "转发格式": "§7[QQ] {nickname}§7: {message}",
                "屏蔽以下字符串开头的消息": []
            },
            "链接的群聊": [963953936],
            "转发玩家进退提示": True
        })

        self.listen("GameChatEvent", self.on_game_chat)
        self.listen("GroupMessageEvent", self.on_group_message, priority=-10)
        self.listen("PlayerJoinEvent", self.on_player_join)
        self.listen("PlayerLeaveEvent", self.on_player_leave)

    def _get_linked_groups(self) -> list[int]:
        groups = self.config.get("消息转发.链接的群聊", [])
        try:
            return [int(g) for g in groups if isinstance(g, (int, str))]
        except (ValueError, TypeError):
            return []

    async def on_game_chat(self, event: GameChatEvent):
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

        if not self.dedup.check_and_add_content(msg, hash(event.player_name)):
            return

        template = cfg.get("转发格式", "<{player}> {message}")
        text = template.replace("{player}", event.player_name).replace("{message}", msg)
        for gid in self._get_linked_groups():
            await self.message.send_group(gid, text)

    async def on_group_message(self, event: GroupMessageEvent):
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
        text = template.replace("{nickname}", event.nickname).replace("{message}", msg)
        self.adapter.send_game_message("@a", text)

    async def on_player_join(self, event: PlayerJoinEvent):
        if not self.config.get("消息转发.转发玩家进退提示", True):
            return
        for gid in self._get_linked_groups():
            await self.message.send_group(gid, f"§a[+] {event.player_name} 加入了游戏")

    async def on_player_leave(self, event: PlayerLeaveEvent):
        if not self.config.get("消息转发.转发玩家进退提示", True):
            return
        for gid in self._get_linked_groups():
            await self.message.send_group(gid, f"§e[-] {event.player_name} 离开了游戏")