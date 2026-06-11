"""守护进程适配器 — FrameworkHost 在守护进程中的"外部接口"

═══════════════════════════════════════════════════════════════════════════
 设计
═══════════════════════════════════════════════════════════════════════════
 GuardianAdapter 实现了 IFrameworkAdapter 接口，但它不做真正的 I/O。
 所有对外操作（发消息、发游戏指令等）通过 Guardian 推送到 IPC 连接，
 由 ToolDelta 端的薄壳实际执行。

 方向:
   模块 → host.services.adapter.send_group_msg(...)
        → GuardianAdapter._push_to_shell("send_group_msg", ...)
        → ToolDelta 薄壳收到推送 → 调用真正的 adapter.send_group_msg(...)
═══════════════════════════════════════════════════════════════════════════
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .guardian import Guardian

_log = logging.getLogger(__name__)


class GuardianAdapter:
    """守护进程内的适配器——所有外发操作通过 IPC 推回薄壳。"""

    def __init__(self, guardian: "Guardian"):
        self._guardian = guardian
        self._console_commands = {}

    # ── 消息发送（通过 IPC 推回薄壳）──

    async def send_group_msg(self, group_id: int, message: str) -> bool:
        """发送群消息 → IPC 推送。"""
        await self._guardian.push_send_group_msg(group_id, message)
        return True

    async def send_private_msg(self, user_id: int, message: str) -> bool:
        """发送私聊消息 → IPC 推送。"""
        await self._guardian.push_send_private_msg(user_id, message)
        return True

    # ── 游戏操作（通过 IPC 推回薄壳）──

    async def send_game_command(self, cmd: str):
        """执行游戏指令 → IPC 推送。"""
        await self._guardian.push_game_command(cmd)

    async def send_game_message(self, target: str, text: str):
        """发送游戏内消息 → tellraw 指令。"""
        escaped = text.replace('"', '\\"')
        await self.send_game_command(f'tellraw {target} {{"rawtext":[{{"text":"{escaped}"}}]}}')

    async def get_online_players(self) -> list:
        """获取在线玩家 → IPC 推送（由薄壳返回）。"""
        await self._guardian.push_get_online_players()
        return []

    # ── 回调注册（守护进程内无需真实绑定，由薄壳转发事件）──

    def listen_game_chat(self, handler):
        pass  # GameChatEvent 由薄壳转发

    def listen_player_join(self, handler):
        pass  # PlayerJoinEvent 由薄壳转发

    def listen_player_leave(self, handler):
        pass  # PlayerLeaveEvent 由薄壳转发

    def listen_group_message(self, handler):
        pass  # GroupMessageEvent 由薄壳转发

    def register_console_command(self, triggers, hint, usage, func):
        """注册控制台命令（守护进程 stdout）。"""
        if not isinstance(triggers, list):
            triggers = [triggers]
        for t in triggers:
            self._console_commands[t] = func

    # ── 查询 ──

    def get_plugin_api(self, name: str):
        return None

    def is_user_admin(self, user_id: int, config_mgr) -> bool:
        return False

    def set_config_mgr(self, config_mgr):
        pass

    def set_online(self, players: list):
        """由薄壳通过 IPC 设置在线玩家列表。"""
        self._online_players = players

    @property
    def online_players(self) -> list:
        return getattr(self, '_online_players', [])
