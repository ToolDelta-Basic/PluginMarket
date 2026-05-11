# adapters/tooldelta_adapter.py
"""ToolDelta 平台适配器实现"""
import logging
from typing import Callable, Dict, Any, List, Optional
from tooldelta import Plugin, Player, Chat
from .base import IFrameworkAdapter
from services.ws_client import WsClient


class ToolDeltaAdapter(IFrameworkAdapter):
    """基于 ToolDelta 的平台适配器，封装游戏控制、事件监听和 WebSocket 通信。"""

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
        """设置 WebSocket 客户端实例。"""
        self._ws_client = ws_client

    def set_config_mgr(self, config_mgr):
        """设置配置管理器。"""
        self._config_mgr = config_mgr

    def send_game_command(self, cmd: str):
        """发送游戏指令。"""
        try:
            self.game_ctrl.sendcmd(cmd)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "游戏命令发送失败: %s, 错误: %s", cmd, e
            )

    def send_game_message(self, target: str, text: str):
        """向游戏内目标发送消息。"""
        try:
            self.game_ctrl.say_to(target, text)
        except Exception as e:
            logging.getLogger(__name__).warning(
                "游戏消息发送失败, 目标: %s, 错误: %s", target, e
            )

    def get_online_players(self) -> List[str]:
        """获取在线玩家列表，自动兼容 ToolDelta 返回的 list 或 dict。"""
        try:
            raw = self.game_ctrl.allplayers
            # 旧版本返回 dict，新版本返回 list
            if isinstance(raw, dict):
                return list(raw.keys())
            if isinstance(raw, (list, tuple)):
                return list(raw)
            # 未知类型，返回空列表
            logging.getLogger(__name__).warning(
                "allplayers 返回了未知类型: %s", type(raw).__name__
            )
            return []
        except Exception as e:
            logging.getLogger(__name__).error(
                "获取在线玩家列表异常: %s", e
            )
            return []

    def send_group_msg(self, group_id: int, message: str) -> bool:
        """发送群消息。"""
        if not self._ws_client:
            logging.getLogger(__name__).warning("WebSocket 客户端不可用")
            return False
        if not self._ws_client.available:
            logging.getLogger(__name__).warning("WebSocket 未连接")
            return False
        return self._ws_client.send_group_msg(group_id, message)

    def send_private_msg(self, user_id: int, message: str) -> bool:
        """发送私聊消息。"""
        if not self._ws_client:
            logging.getLogger(__name__).warning("WebSocket 客户端不可用")
            return False
        if not self._ws_client.available:
            logging.getLogger(__name__).warning("WebSocket 未连接")
            return False
        return self._ws_client.send_private_msg(user_id, message)

    def _on_game_chat(self, chat: Chat):
        """分发游戏聊天事件给所有处理器。"""
        for h in self._chat_handlers:
            try:
                h(chat.player.name, chat.msg)
            except Exception as e:
                logging.getLogger(__name__).error("游戏聊天处理器异常: %s", e)

    def _on_player_join(self, player: Player):
        """分发玩家加入事件。"""
        for h in self._player_join_handlers:
            try:
                h(player.name)
            except Exception as e:
                logging.getLogger(__name__).error("玩家加入处理器异常: %s", e)

    def _on_player_leave(self, player: Player):
        """分发玩家离开事件。"""
        for h in self._player_leave_handlers:
            try:
                h(player.name)
            except Exception as e:
                logging.getLogger(__name__).error("玩家离开处理器异常: %s", e)

    def listen_game_chat(self, handler: Callable[[str, str], None]):
        """注册游戏聊天处理器。"""
        self._chat_handlers.append(handler)

    def listen_player_join(self, handler: Callable[[str], None]):
        """注册玩家加入处理器。"""
        self._player_join_handlers.append(handler)

    def listen_player_leave(self, handler: Callable[[str], None]):
        """注册玩家离开处理器。"""
        self._player_leave_handlers.append(handler)

    def listen_group_message(self, handler: Callable[[Dict[str, Any]], None]):
        """注册原始群消息处理器。"""
        self._group_message_handlers.append(handler)

    def trigger_raw_group_handlers(self, data: dict):
        """触发所有原始群消息处理器。"""
        for handler in self._group_message_handlers:
            try:
                handler(data)
            except Exception as e:
                logging.getLogger(__name__).error("原始消息处理器异常: %s", e)

    def register_console_command(
        self, triggers: List[str], hint: str, usage: str, func: Callable
    ):
        """注册控制台命令。"""
        self.plugin.frame.add_console_cmd_trigger(triggers, hint, usage, func)

    def get_plugin_api(self, name: str) -> Optional[Any]:
        """获取其他插件的 API 实例。"""
        return self.plugin.GetPluginAPI(name)

    def is_user_admin(self, user_id: int, config_mgr=None) -> bool:
        """检查用户是否为管理员。"""
        cfg = config_mgr or self._config_mgr
        if cfg is None:
            return False
        admin_list = cfg.get("管理员.管理员QQ", [])
        try:
            return user_id in [int(q) for q in admin_list]
        except (TypeError, ValueError):
            return False

    def send_game_command_with_resp(self, cmd: str, timeout: float = 5.0) -> Optional[str]:
        """发送游戏指令并返回响应文本。"""
        try:
            resp = self.game_ctrl.sendwscmd_with_resp(cmd, timeout)
            if resp and resp.OutputMessages:
                # 合并输出消息为纯文本
                lines = []
                for msg in resp.OutputMessages:
                    if hasattr(msg, 'Message'):
                        lines.append(msg.Message)
                    else:
                        lines.append(str(msg))
                return "\n".join(lines)
            return ""
        except Exception as e:
            logging.getLogger(__name__).error("同步指令执行失败: %s", e)
            return None
