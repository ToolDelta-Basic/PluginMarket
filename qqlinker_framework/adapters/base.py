# adapters/base.py
from abc import ABC, abstractmethod
from typing import Callable, List, Optional, Any, Dict
import logging
_log = logging.getLogger(__name__)


class IFrameworkAdapter(ABC):
    """平台适配器抽象基类，定义所有需要实现的方法。"""

    @abstractmethod
    def send_game_command(self, cmd: str) -> None:  # noqa: PYL-R0201
        """发送游戏指令。"""

    @abstractmethod
    def send_game_message(self, target: str, text: str) -> None:  # noqa: PYL-R0201
        """向游戏内目标发送消息。"""

    @abstractmethod
    def get_online_players(self) -> List[str]:  # noqa: PYL-R0201
        """获取当前在线玩家列表（纯名字列表）。"""

    @abstractmethod
    def send_group_msg(self, group_id: int, message: str) -> bool:  # noqa: PYL-R0201
        """发送群聊消息。"""

    @abstractmethod
    def send_private_msg(self, user_id: int, message: str) -> bool:  # noqa: PYL-R0201
        """发送私聊消息。"""

    @abstractmethod
    def listen_game_chat(  # noqa: PYL-R0201
        self, handler: Callable[[str, str], None]
    ) -> None:
        """注册游戏聊天监听。"""

    @abstractmethod
    def listen_group_message(  # noqa: PYL-R0201
        self, handler: Callable[[Dict[str, Any]], None]
    ) -> None:
        """注册群消息监听。"""

    @abstractmethod
    def listen_player_join(  # noqa: PYL-R0201
        self, handler: Callable[[str], None]
    ) -> None:
        """注册玩家加入事件监听。"""

    @abstractmethod
    def listen_player_leave(  # noqa: PYL-R0201
        self, handler: Callable[[str], None]
    ) -> None:
        """注册玩家离开事件监听。"""

    @abstractmethod
    def register_console_command(  # noqa: PYL-R0201
        self,
        triggers: List[str],
        hint: str,
        usage: str,
        func: Callable,
    ) -> None:
        """注册控制台命令。"""

    @abstractmethod
    def get_plugin_api(self, name: str) -> Optional[Any]:  # noqa: PYL-R0201
        """获取其他插件的 API 实例。"""

    @abstractmethod
    def is_user_admin(self, user_id: int, config_mgr) -> bool:  # noqa: PYL-R0201
        """检查用户是否为平台管理员。"""

    @abstractmethod
    def send_game_command_with_resp(  # noqa: PYL-R0201
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[str]:
        """发送游戏指令并等待响应文本，超时返回 None。"""

    @abstractmethod
    def send_game_command_full(  # noqa: PYL-R0201
        self, cmd: str, timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """发送游戏指令并返回完整响应。

        Returns:
            None 表示异常或超时，否则返回字典：
            {
                "success_count": int,
                "output": [{"message": str, "parameters": list}, ...]
            }
        """

    def resolve_player_names(self, entries: list) -> dict:  # noqa: PYL-R0201 (abstract interface — subclasses may need self for platform-specific mappings)
        """将查询条目中的 UUID 映射为玩家名。

        默认实现为空映射，子类可覆盖以提供平台特定的 UUID→名字解析。

        Args:
            entries: 包含 uniqueId 键的条目列表。

        Returns:
            {uniqueId: player_name} 映射字典。
        """
        return {}

    # ── 可选扩展: 生命周期事件 ──────────────────────────────

    def listen_active(self, handler: Callable[[], None]) -> None:  # noqa: PYL-R0201
        """注册框架就绪处理器（可选实现）。"""

    def listen_frame_exit(self, handler: Callable[[Any], None]) -> None:  # noqa: PYL-R0201
        """注册框架退出处理器（可选实现）。"""

    def listen_player_pre_join(self, handler: Callable[[str], None]) -> None:  # noqa: PYL-R0201
        """注册玩家预加入处理器（可选实现）。"""

    # ── 可选扩展: 数据包监听 ──────────────────────────────────

    def listen_dict_packet(  # noqa: PYL-R0201
        self, packet_id: int, handler: Callable[[dict], bool]
    ) -> None:
        """注册字典数据包监听，返回 True 拦截数据包。"""

    def listen_bytes_packet(  # noqa: PYL-R0201
        self, packet_id: int, handler: Callable[[bytes], bool]
    ) -> None:
        """注册二进制数据包监听，返回 True 拦截数据包。"""

    # ── 可选扩展: 标题栏消息 ────────────────────────────────

    def send_game_title(self, target: str, text: str) -> None:  # noqa: PYL-R0201
        """向玩家显示标题栏消息（可选实现）。"""

    def send_game_subtitle(self, target: str, text: str) -> None:  # noqa: PYL-R0201
        """向玩家显示小标题栏消息（可选实现）。"""

    def send_game_actionbar(self, target: str, text: str) -> None:  # noqa: PYL-R0201
        """向玩家显示行动栏消息（可选实现）。"""

    # ── 可选扩展: 轮询发信 ────────────────────────────────

    def send_message_round_robin(  # noqa: PYL-R0201 (abstract interface — subclasses may need self for multi-bot round-robin)
        self, group_id: int, message: str
    ) -> bool:
        """轮询式群消息发送（多机器人场景下自动切换机器人）。

        多机器人模式:
          - 如果 send_guard 可用 → 通过 SendGuard.send_with_ack() 发送
          - SendGuard 自动选择机器人 → 发送 → 回显确认 → 故障转移

        单机器人模式:
          降级为 send_group_msg。

        Args:
            group_id: QQ 群号。
            message: 消息文本。

        Returns:
            是否发送成功。
        """
        send_guard = getattr(self, '_send_guard', None)
        if send_guard is not None:
            try:
                return send_guard.send_with_ack(group_id, message, priority=1)
            except Exception as e:
                _log.debug("base.send_message_round_robin: %s", e)
        return self.send_group_msg(group_id, message)

    # ── 可选扩展: 跨插件 API 代理 ─────────────────────────────

    def register_pre_plugin_api(  # noqa: PYL-R0201 (abstract interface — subclasses may need self for adapter-specific API registration)
        self, api_name: str, min_version: tuple = (0, 0, 0)
    ) -> bool:
        """注册 datas.json 声明的依赖插件 API。

        Args:
            api_name: API 名称。
            min_version: 最低版本要求。

        Returns:
            是否成功注册。
        """
        return False

    def get_pre_plugin_api(self, api_name: str) -> Optional[Any]:  # noqa: PYL-R0201 (abstract interface — subclasses may need self for adapter-specific API resolution)
        """获取已注册的前置插件 API 实例。

        Args:
            api_name: API 名称。

        Returns:
            API 实例或 None。
        """
        return None

    def get_pre_plugin_apis(self) -> Dict[str, Any]:  # noqa: PYL-R0201 (abstract interface — subclasses may need self for adapter-specific API collection)
        """返回所有已注册的前置插件 API 字典。"""
        return {}
