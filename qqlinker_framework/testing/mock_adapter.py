"""Mock 适配器 — 实现 IFrameworkAdapter 完整接口，纯内存操作。"""
from typing import Any, Callable, Dict, List, Optional


_MOCK_PARAM = (
    '{"position":{"x":0,"y":64,"z":0},'
    '"dimension":0,"yRot":0,"uniqueId":"mock-uuid"}'
)


class MockAdapter:
    """模拟游戏/平台适配器，无外部依赖，用于测试。"""

    def __init__(self) -> None:
        self._online: List[str] = []
        self._game_messages: List[tuple] = []
        self._group_messages: List[tuple] = []
        self._commands: List[str] = []
        self._chat_handlers: List[Callable] = []
        self._group_handlers: List[Callable] = []
        self._join_handlers: List[Callable] = []
        self._leave_handlers: List[Callable] = []
        self._pre_join_handlers: List[Callable] = []
        self._active_handlers: List[Callable] = []
        self._frame_exit_handlers: List[Callable] = []
        self._packet_handlers: Dict[int, List[Callable]] = {}
        self._bytes_packet_handlers: Dict[int, List[Callable]] = {}
        self._admins: List[int] = []
        self._title_messages: List[tuple] = []
        self._subtitle_messages: List[tuple] = []
        self._actionbar_messages: List[tuple] = []
        self._pre_plugin_apis: Dict[str, Any] = {}
        self._active = False

    # ── 公开属性 ──

    @property
    def is_active(self) -> bool:
        """模拟器是否已激活。"""
        return self._active

    def get_stats(self) -> Dict[str, Any]:
        """返回统计信息。"""
        return {
            "admins": self._admins,
            "command_count": len(self._commands),
            "game_msg_count": len(self._game_messages),
        }

    # ── 游戏指令 ──

    def send_game_command(self, cmd: str) -> None:
        """记录指令。"""
        self._commands.append(cmd)

    def send_game_message(self, target: str, text: str) -> None:
        """记录消息。"""
        self._game_messages.append((target, text))

    def send_game_command_with_resp(
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[str]:
        """返回 mock 响应。"""
        return f"mock_response:{cmd}"

    def send_game_command_full(
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """返回完整 mock 响应。"""
        if "fail" in cmd:
            return None
        return {
            "success_count": 1,
            "output": [
                {"message": f"mock:{cmd}", "parameters": [_MOCK_PARAM]}
            ],
        }

    # ── 玩家管理 ──

    def get_online_players(self) -> List[str]:
        """返回在线玩家列表。"""
        return list(self._online)

    def set_online(self, players: List[str]) -> None:
        """设置在线玩家。"""
        self._online = list(players)

    def resolve_player_names(self, entries: list) -> dict:
        """返回 mock UUID 映射。"""
        return {"mock-uuid": "MockPlayer"}

    # ── 群聊消息 ──

    def send_group_msg(self, group_id: int, message: str) -> bool:
        """记录群消息。"""
        self._group_messages.append((group_id, message))
        return True

    def send_private_msg(self, user_id: int, message: str) -> bool:
        """记录私聊消息。"""
        self._group_messages.append(("private", user_id, message))
        return True

    # ── 标题栏消息 ──

    def send_game_title(self, target: str, text: str) -> None:
        """记录标题栏消息。"""
        self._title_messages.append((target, text))

    def send_game_subtitle(self, target: str, text: str) -> None:
        """记录副标题消息。"""
        self._subtitle_messages.append((target, text))

    def send_game_actionbar(self, target: str, text: str) -> None:
        """记录行动栏消息。"""
        self._actionbar_messages.append((target, text))

    # ── 事件监听 ──

    def listen_game_chat(self, handler: Callable) -> None:
        """注册游戏聊天监听。"""
        self._chat_handlers.append(handler)

    def listen_group_message(self, handler: Callable) -> None:
        """注册群消息监听。"""
        self._group_handlers.append(handler)

    def listen_player_join(self, handler: Callable) -> None:
        """注册玩家加入监听。"""
        self._join_handlers.append(handler)

    def listen_player_leave(self, handler: Callable) -> None:
        """注册玩家离开监听。"""
        self._leave_handlers.append(handler)

    def listen_player_pre_join(self, handler: Callable) -> None:
        """注册玩家预加入监听。"""
        self._pre_join_handlers.append(handler)

    def listen_active(self, handler: Callable) -> None:
        """注册激活监听。"""
        self._active_handlers.append(handler)

    def listen_frame_exit(self, handler: Callable) -> None:
        """注册退出监听。"""
        self._frame_exit_handlers.append(handler)

    def listen_dict_packet(
        self, packet_id: int, handler: Callable[[dict], bool]
    ) -> None:
        """注册字典数据包监听。"""
        self._packet_handlers.setdefault(packet_id, []).append(handler)

    def listen_bytes_packet(
        self, packet_id: int, handler: Callable[[bytes], bool]
    ) -> None:
        """注册二进制数据包监听。"""
        self._bytes_packet_handlers.setdefault(packet_id, []).append(handler)

    # ── 模拟触发 ──

    def fire_game_chat(self, player: str, message: str) -> None:
        """触发游戏聊天事件。"""
        for h in self._chat_handlers:
            h(player, message)

    def fire_player_join(self, player: str) -> None:
        """触发玩家加入事件。"""
        for h in self._join_handlers:
            h(player)

    def fire_player_leave(self, player: str) -> None:
        """触发玩家离开事件。"""
        for h in self._leave_handlers:
            h(player)

    def fire_player_pre_join(self, player: str) -> None:
        """触发玩家预加入事件。"""
        for h in self._pre_join_handlers:
            h(player)

    def fire_active(self) -> None:
        """触发激活事件。"""
        self._active = True
        for h in self._active_handlers:
            h()

    def fire_frame_exit(self, evt: Any = None) -> None:
        """触发框架退出事件。"""
        for h in self._frame_exit_handlers:
            h(evt)

    def fire_dict_packet(self, packet_id: int, packet: dict) -> bool:
        """触发字典数据包。"""
        return any(
            handler(packet)
            for handler in self._packet_handlers.get(packet_id, [])
        )

    # ── 其他 ──

    def register_console_command(
        self, triggers, hint, usage, func
    ) -> None:
        """桩：不执行实际注册。"""

    def get_plugin_api(self, name: str) -> Optional[Any]:
        """返回预设的前置插件 API。"""
        return self._pre_plugin_apis.get(name)

    def register_pre_plugin_api(
        self, api_name: str, min_version: tuple = (0, 0, 0)
    ) -> bool:
        """Mock：总是成功。"""
        if api_name not in self._pre_plugin_apis:
            self._pre_plugin_apis[api_name] = object()
        return True

    def get_pre_plugin_api(self, api_name: str) -> Optional[Any]:
        """返回预设的前置插件 API。"""
        return self._pre_plugin_apis.get(api_name)

    def set_pre_plugin_api(self, api_name: str, instance: Any) -> None:
        """测试辅助：预设前置插件 API 实例。"""
        self._pre_plugin_apis[api_name] = instance

    def is_user_admin(self, user_id: int, config_mgr=None) -> bool:
        """检查用户是否在预设管理员列表中。"""
        return user_id in self._admins

    def set_admins(self, admins: List[int]) -> None:
        """设置管理员列表。"""
        self._admins = admins

    def trigger_raw_group_handlers(self, data: dict) -> None:
        """触发原始群消息处理器。"""
        for handler in self._group_handlers:
            try:
                handler(data)
            except Exception:
                pass
