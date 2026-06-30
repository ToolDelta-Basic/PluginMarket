import logging
from typing import TYPE_CHECKING

from .protocol import (
    IPC_VERSION, DEFAULT_CAPABILITIES,
    is_hello, make_hello_ack,
)

if TYPE_CHECKING:
    from .guardian import Guardian

_log = logging.getLogger(__name__)


class GuardianAdapter:
    """守护进程内的适配器——所有外发操作通过 IPC 推回薄壳。"""

    def __init__(self, guardian: "Guardian"):
        self._guardian = guardian
        self._console_commands = {}
        # ── v1.5: IPC 版本协商 ──
        self._client_version: int | None = None
        self._client_capabilities: list = []
        self._version_negotiated = False

    def handle_hello(self, params: dict) -> dict:
        """处理客户端 HELLO 握手，回复 HELLO_ACK。

        由 IPCServer 在连接建立后调用。
        记录客户端版本和能力，不因版本不匹配而拒绝连接。

        Args:
            params: HELLO 消息体 {"version": int, "capabilities": [...]}
        Returns:
            HELLO_ACK 响应
        """
        client_version = params.get("version", 0)
        client_caps = params.get("capabilities", [])
        self._client_version = client_version
        self._client_capabilities = client_caps
        self._version_negotiated = True

        if client_version != IPC_VERSION:
            _log.warning(
                "IPC 版本不匹配: 客户端 v%d, 服务端 v%d。降级运行。",
                client_version, IPC_VERSION,
            )
        else:
            _log.info(
                "IPC 版本协商完成: v%d, 客户端能力=%s",
                client_version, client_caps,
            )

        return make_hello_ack(
            version=IPC_VERSION,
            capabilities=DEFAULT_CAPABILITIES,
        )

    def get_client_version(self) -> int | None:
        """返回客户端的 IPC 版本号。"""
        return self._client_version

    def get_client_capabilities(self) -> list:
        """返回客户端声明的能力列表。"""
        return list(self._client_capabilities)

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

    def listen_game_chat(self, handler):  # noqa: PYL-R0201
        """注册游戏聊天监听。"""
        pass  # GameChatEvent 由薄壳转发

    def listen_player_join(self, handler):  # noqa: PYL-R0201
        """注册玩家加入监听。"""
        pass  # PlayerJoinEvent 由薄壳转发

    def listen_player_leave(self, handler):  # noqa: PYL-R0201
        """注册玩家离开监听。"""
        pass  # PlayerLeaveEvent 由薄壳转发

    def listen_group_message(self, handler):  # noqa: PYL-R0201
        """注册群消息监听。"""
        pass  # GroupMessageEvent 由薄壳转发

    def register_console_command(self, triggers, hint, usage, func):
        """注册控制台命令（守护进程 stdout）。"""
        if not isinstance(triggers, list):
            triggers = [triggers]
        for t in triggers:
            self._console_commands[t] = func

    # ── 查询 ──

    def get_plugin_api(self, name: str):  # noqa: PYL-R0201
        """获取插件 API。"""
        return None

    def is_user_admin(self, user_id: int, config_mgr) -> bool:  # noqa: PYL-R0201
        """检查用户是否为管理员。"""
        return False

    def set_config_mgr(self, config_mgr):  # noqa: PYL-R0201
        """设置配置管理器引用。"""
        pass

    def set_online(self, players: list):
        """由薄壳通过 IPC 设置在线玩家列表。"""
        self._online_players = players

    @property
    def online_players(self) -> list:
        """在线玩家列表。"""
        return getattr(self, '_online_players', [])
