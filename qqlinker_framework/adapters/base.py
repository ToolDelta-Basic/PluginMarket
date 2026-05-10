# adapters/base.py
"""平台适配器抽象接口"""
from abc import ABC, abstractmethod
from typing import Callable, List, Optional, Any, Dict


class IFrameworkAdapter(ABC):
    """平台适配器抽象基类，定义所有需要实现的方法。"""

    @abstractmethod
    def send_game_command(self, cmd: str) -> None:
        """发送游戏指令。

        Args:
            cmd: 完整的指令字符串。
        """

    @abstractmethod
    def send_game_message(self, target: str, text: str) -> None:
        """向游戏内目标发送消息。

        Args:
            target: 目标选择器或玩家名。
            text: 消息文本。
        """

    @abstractmethod
    def get_online_players(self) -> List[str]:
        """获取当前在线玩家列表。

        Returns:
            玩家名称列表。
        """

    @abstractmethod
    def send_group_msg(self, group_id: int, message: str) -> bool:
        """发送群聊消息。

        Args:
            group_id: 群号。
            message: 消息内容。

        Returns:
            是否成功发送。
        """

    @abstractmethod
    def send_private_msg(self, user_id: int, message: str) -> bool:
        """发送私聊消息。

        Args:
            user_id: QQ 号。
            message: 消息内容。

        Returns:
            是否成功发送。
        """

    @abstractmethod
    def listen_game_chat(self, handler: Callable[[str, str], None]) -> None:
        """注册游戏聊天监听。

        Args:
            handler: 回调函数，接收玩家名和消息。
        """

    @abstractmethod
    def listen_group_message(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """注册群消息监听。

        Args:
            handler: 回调函数，接收原始消息字典。
        """

    @abstractmethod
    def listen_player_join(self, handler: Callable[[str], None]) -> None:
        """注册玩家加入事件监听。

        Args:
            handler: 回调函数，接收玩家名。
        """

    @abstractmethod
    def listen_player_leave(self, handler: Callable[[str], None]) -> None:
        """注册玩家离开事件监听。

        Args:
            handler: 回调函数，接收玩家名。
        """

    @abstractmethod
    def register_console_command(
        self, triggers: List[str], hint: str, usage: str, func: Callable
    ) -> None:
        """注册控制台命令。

        Args:
            triggers: 命令触发词列表。
            hint: 命令参数提示。
            usage: 命令用途说明。
            func: 回调函数。
        """

    @abstractmethod
    def get_plugin_api(self, name: str) -> Optional[Any]:
        """获取其他插件的 API 实例。

        Args:
            name: 插件名或 API 名。

        Returns:
            插件实例或 None。
        """

    @abstractmethod
    def is_user_admin(self, user_id: int, config_mgr) -> bool:
        """检查用户是否为平台管理员。

        Args:
            user_id: QQ 号。
            config_mgr: 配置管理器。

        Returns:
            是否管理员。
        """
        