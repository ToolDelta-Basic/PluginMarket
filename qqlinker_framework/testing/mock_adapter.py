"""Mock 适配器 — 实现 IFrameworkAdapter 完整接口，所有方法返回假数据。

v1.1.0 — 同步更新以匹配 IFrameworkAdapter 新增的可选方法。
"""
from typing import Any, Callable, Dict, List, Optional


class MockAdapter:
    """模拟游戏/平台适配器，纯内存操作，无外部依赖。"""

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

    # ── 游戏指令 ──
    def send_game_command(self, cmd: str) -> None:
        self._commands.append(cmd)

    def send_game_message(self, target: str, text: str) -> None:
        self._game_messages.append((target, text))

    def send_game_command_with_resp(
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[str]:
        return f"mock_response:{cmd}"

    # ★ 修复: 返回类型与 IFrameworkAdapter 对齐
    def send_game_command_full(
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        if "fail" in cmd:
            return None  # 模拟失败
        return {
            "success_count": 1,
            "output": [
                {
                    "message": f"mock:{cmd}",
                    "parameters": ['{"position":{"x":0,"y":64,"z":0},"dimension":0,"yRot":0,"uniqueId":"mock-uuid"}'],
                }
            ],
        }

    # ── 玩家管理 ──
    def get_online_players(self) -> List[str]:
        return list(self._online)

    def set_online(self, players: List[str]) -> None:
        self._online = list(players)

    def resolve_player_names(self, entries: list) -> dict:
        """Mock 实现：返回预设的 UUID→名字映射。"""
        return {"mock-uuid": "MockPlayer"}

    # ── 群聊消息 ──
    def send_group_msg(self, group_id: int, message: str) -> bool:
        self._group_messages.append((group_id, message))
        return True

    def send_private_msg(self, user_id: int, message: str) -> bool:
        self._group_messages.append(("private", user_id, message))
        return True

    # ── 标题栏消息 ──
    def send_game_title(self, target: str, text: str) -> None:
        self._title_messages.append((target, text))

    def send_game_subtitle(self, target: str, text: str) -> None:
        self._subtitle_messages.append((target, text))

    def send_game_actionbar(self, target: str, text: str) -> None:
        self._actionbar_messages.append((target, text))

    # ── 事件监听 ──
    def listen_game_chat(self, handler: Callable) -> None:
        self._chat_handlers.append(handler)

    def listen_group_message(self, handler: Callable) -> None:
        self._group_handlers.append(handler)

    def listen_player_join(self, handler: Callable) -> None:
        self._join_handlers.append(handler)

    def listen_player_leave(self, handler: Callable) -> None:
        self._leave_handlers.append(handler)

    def listen_player_pre_join(self, handler: Callable) -> None:
        self._pre_join_handlers.append(handler)

    def listen_active(self, handler: Callable) -> None:
        self._active_handlers.append(handler)

    def listen_frame_exit(self, handler: Callable) -> None:
        self._frame_exit_handlers.append(handler)

    def listen_dict_packet(
        self, packet_id: int, handler: Callable[[dict], bool]
    ) -> None:
        self._packet_handlers.setdefault(packet_id, []).append(handler)

    def listen_bytes_packet(
        self, packet_id: int, handler: Callable[[bytes], bool]
    ) -> None:
        self._bytes_packet_handlers.setdefault(packet_id, []).append(handler)

    # ── 模拟触发 ──
    def fire_game_chat(self, player: str, message: str) -> None:
        for h in self._chat_handlers:
            h(player, message)

    def fire_player_join(self, player: str) -> None:
        for h in self._join_handlers:
            h(player)

    def fire_player_leave(self, player: str) -> None:
        for h in self._leave_handlers:
            h(player)

    def fire_player_pre_join(self, player: str) -> None:
        for h in self._pre_join_handlers:
            h(player)

    def fire_active(self) -> None:
        self._active = True
        for h in self._active_handlers:
            h()

    def fire_frame_exit(self, evt: Any = None) -> None:
        for h in self._frame_exit_handlers:
            h(evt)

    def fire_dict_packet(self, packet_id: int, packet: dict) -> bool:
        for handler in self._packet_handlers.get(packet_id, []):
            if handler(packet):
                return True
        return False

    # ── 其他 ──
    def register_console_command(self, triggers, hint, usage, func) -> None:
        pass

    def get_plugin_api(self, name: str) -> Optional[Any]:
        return self._pre_plugin_apis.get(name)

    def register_pre_plugin_api(
        self, api_name: str, min_version: tuple = (0, 0, 0)
    ) -> bool:
        # Mock: 总是成功注册，set_pre_plugin_api 可预设
        if api_name not in self._pre_plugin_apis:
            self._pre_plugin_apis[api_name] = object()  # 占位
        return True

    def get_pre_plugin_api(self, api_name: str) -> Optional[Any]:
        return self._pre_plugin_apis.get(api_name)

    def set_pre_plugin_api(self, api_name: str, instance: Any) -> None:
        """测试辅助：预设前置插件 API 实例。"""
        self._pre_plugin_apis[api_name] = instance

    def is_user_admin(self, user_id: int, config_mgr=None) -> bool:
        return user_id in self._admins

    def set_admins(self, admins: List[int]) -> None:
        self._admins = admins
