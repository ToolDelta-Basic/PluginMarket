# adapters/tooldelta_adapter.py
"""ToolDelta 平台适配器实现"""
import logging
from typing import Callable, Dict, Any, List, Optional
from tooldelta import Plugin, Player, Chat
from .base import IFrameworkAdapter
from services.ws_client import WsClient

class ToolDeltaAdapter(IFrameworkAdapter):
    def __init__(self, plugin_instance: Plugin):
        self.plugin = plugin_instance
        self.game_ctrl = plugin_instance.game_ctrl
        self._config_mgr = None

        self.plugin.ListenChat(self._on_game_chat)
        self.plugin.ListenPlayerJoin(self._on_player_join)
        self.plugin.ListenPlayerLeave(self._on_player_leave)

        self._chat_handlers: list[Callable] = []
        self._player_join_handlers: list[Callable] = []
        self._player_leave_handlers: list[Callable] = []
        self._group_message_handlers: list[Callable] = []

        self._ws_client: Optional[WsClient] = None
        self.event_bus = None
        self.main_loop = None

    def set_ws_client(self, ws_client: WsClient):
        self._ws_client = ws_client

    def set_config_mgr(self, config_mgr):
        self._config_mgr = config_mgr

    # ---------- 游戏控制 ----------
    def send_game_command(self, cmd: str):
        try:
            self.game_ctrl.sendcmd(cmd)
        except Exception as e:
            logging.getLogger(__name__).warning("游戏命令发送失败: %s, 错误: %s", cmd, e)

    def send_game_message(self, target: str, text: str):
        try:
            self.game_ctrl.say_to(target, text)
        except Exception as e:
            logging.getLogger(__name__).warning("游戏消息发送失败, 目标: %s, 错误: %s", target, e)

    def get_online_players(self) -> List[str]:
        try:
            return list(self.game_ctrl.allplayers.keys())
        except Exception:
            return []

    # ---------- QQ消息 ----------
    def send_group_msg(self, group_id: int, message: str) -> bool:
        if not self._ws_client:
            logging.getLogger(__name__).warning("WebSocket 客户端不可用")
            return False
        if not self._ws_client.available:
            logging.getLogger(__name__).warning("WebSocket 未连接")
            return False
        return self._ws_client.send_group_msg(group_id, message)

    def send_private_msg(self, user_id: int, message: str) -> bool:
        if not self._ws_client:
            logging.getLogger(__name__).warning("WebSocket 客户端不可用")
            return False
        if not self._ws_client.available:
            logging.getLogger(__name__).warning("WebSocket 未连接")
            return False
        return self._ws_client.send_private_msg(user_id, message)

    # ---------- 事件监听（增加异常隔离）----------
    def _on_game_chat(self, chat: Chat):
        for h in self._chat_handlers:
            try:
                h(chat.player.name, chat.msg)
            except Exception as e:
                logging.getLogger(__name__).error("游戏聊天处理器异常: %s", e)

    def _on_player_join(self, player: Player):
        for h in self._player_join_handlers:
            try:
                h(player.name)
            except Exception as e:
                logging.getLogger(__name__).error("玩家加入处理器异常: %s", e)

    def _on_player_leave(self, player: Player):
        for h in self._player_leave_handlers:
            try:
                h(player.name)
            except Exception as e:
                logging.getLogger(__name__).error("玩家离开处理器异常: %s", e)

    def listen_game_chat(self, handler: Callable[[str, str], None]):
        self._chat_handlers.append(handler)

    def listen_player_join(self, handler: Callable[[str], None]):
        self._player_join_handlers.append(handler)

    def listen_player_leave(self, handler: Callable[[str], None]):
        self._player_leave_handlers.append(handler)

    def listen_group_message(self, handler: Callable[[Dict[str, Any]], None]):
        self._group_message_handlers.append(handler)

    def trigger_raw_group_handlers(self, data: dict):
        for handler in self._group_message_handlers:
            try:
                handler(data)
            except Exception as e:
                logging.getLogger(__name__).error("原始消息处理器异常: %s", e)

    def register_console_command(self, triggers: List[str], hint: str, usage: str, func: Callable):
        self.plugin.frame.add_console_cmd_trigger(triggers, hint, usage, func)

    def get_plugin_api(self, name: str) -> Optional[Any]:
        return self.plugin.GetPluginAPI(name)

    def is_user_admin(self, user_id: int, config_mgr=None) -> bool:
        cfg = config_mgr or self._config_mgr
        if cfg is None:
            return False
        admin_list = cfg.get("管理员.管理员QQ", [])
        try:
            return user_id in [int(q) for q in admin_list]
        except (TypeError, ValueError):
            return False