# adapters/standalone.py
"""QQ 独立模式适配器 — 不连接游戏服务器，纯 QQ 机器人。

所有游戏相关方法返回空值/NOOP，保持接口兼容。
模块可通过 self.adapter 存在性判断是否在游戏模式。
"""
import logging
from typing import Callable, Dict, Any, List, Optional

from .base import IFrameworkAdapter

_log = logging.getLogger(__name__)


class StandaloneAdapter(IFrameworkAdapter):
    """QQ 独立模式适配器。只提供 QQ 消息功能，游戏接口全部空实现。

    适用场景：
      - 纯 QQ 群机器人（无 Minecraft 服）
      - 测试环境（不需要游戏连接）
      - 其他 IM 平台（Telegram/Discord/WhatsApp）
    """

    def __init__(self, ws_client=None):
        self._ws_client = ws_client
        self._active = False

    # ── QQ 消息（委托给 WS 客户端）──

    def send_group_msg(self, group_id: int, message: str) -> bool:
        if self._ws_client and self._ws_client.available:
            return self._ws_client.send_group_msg(group_id, message)
        _log.warning("WS 客户端不可用，群消息未发送")
        return False

    def send_private_msg(self, user_id: int, message: str) -> bool:
        if self._ws_client and self._ws_client.available:
            return self._ws_client.send_private_msg(user_id, message)
        _log.warning("WS 客户端不可用，私聊消息未发送")
        return False

    # ── 游戏指令（空实现）──

    def send_game_command(self, cmd: str) -> None:
        _log.debug("独立模式: 跳过游戏指令 '%s'", cmd[:60])

    def send_game_message(self, target: str, text: str) -> None:
        _log.debug("独立模式: 跳过游戏消息 → %s", target)

    def send_game_title(self, target: str, text: str) -> None:
        pass

    def send_game_subtitle(self, target: str, text: str) -> None:
        pass

    def send_game_actionbar(self, target: str, text: str) -> None:
        pass

    def get_online_players(self) -> List[str]:
        return []

    def send_game_command_with_resp(
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[str]:
        _log.debug("独立模式: 跳过同步指令 '%s'", cmd[:60])
        return None

    def send_game_command_full(
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        _log.debug("独立模式: 跳过完整指令 '%s'", cmd[:60])
        return None

    # ── 事件监听（空实现）──

    def listen_game_chat(
        self, handler: Callable[[str, str], None]
    ) -> None:
        pass

    def listen_player_join(self, handler: Callable[[str], None]) -> None:
        pass

    def listen_player_leave(self, handler: Callable[[str], None]) -> None:
        pass

    def listen_group_message(
        self, handler: Callable[[Dict[str, Any]], None]
    ) -> None:
        pass

    def register_console_command(
        self, triggers: List[str], hint: str, usage: str, func: Callable
    ) -> None:
        pass

    def get_plugin_api(self, name: str) -> Optional[Any]:
        return None

    def is_user_admin(self, user_id: int, config_mgr=None) -> bool:
        if config_mgr is None:
            return False
        admin_list = config_mgr.get("管理员.管理员QQ", [])
        try:
            uid_int = int(user_id) if not isinstance(user_id, int) else user_id
            return uid_int in [int(q) for q in admin_list]
        except (TypeError, ValueError):
            return False

    def resolve_player_names(self, entries: list) -> dict:
        return {}
