"""框架端 IPC 集成 — 当以 --ipc-mode 启动时，用 IPCClient 替代直接 adapter。

在 ChannelHost.start() 中检测 IPC 模式：
- 如果有 --ipc-mode 参数，创建 IPCClient 连接宿主
- 注册 GameProxy 作为 "game" 服务
- adapter 设为 IPCAdapterProxy（通过 IPC 调用宿主方法）
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["IPCAdapterProxy", "setup_ipc_mode"]


class IPCAdapterProxy:
    """通过 IPC 调用宿主的适配器代理。

    对框架内部来说，它实现了 IFrameworkAdapter 接口的子集，
    但所有调用都通过 IPC 转发到宿主进程。
    """

    def __init__(self, ipc_client: Any, caller_mid: int = 300):
        self._client = ipc_client
        self._mid = caller_mid

    def _make_params(self, params: dict) -> dict:
        """将 _mid 注入到参数中供宿主端权限检查。"""
        params["_mid"] = self._mid
        return params

    def send_game_command(self, cmd: str) -> Any:
        """发送游戏命令（通过 IPC）。"""
        return self._client.call(
            "sendcmd", self._make_params({"cmd": cmd}), self._mid
        )

    def send_game_command_raw(self, cmd: str) -> Any:
        """发送原始游戏命令（通过 IPC，无安全过滤）。"""
        return self._client.call(
            "sendcmd_raw", self._make_params({"cmd": cmd}), self._mid
        )

    def send_group_msg(self, group_id: int, message: str) -> Any:
        """发送群消息（通过 IPC）。"""
        return self._client.call(
            "send_group_msg",
            self._make_params({"group_id": group_id, "message": message}),
            self._mid,
        )

    def send_private_msg(self, user_id: int, message: str) -> Any:
        """发送私聊消息（通过 IPC）。"""
        return self._client.call(
            "send_private_msg",
            self._make_params({"user_id": user_id, "message": message}),
            self._mid,
        )

    def get_online_players(self) -> Any:
        """获取在线玩家列表（通过 IPC）。"""
        return self._client.call(
            "get_online_players", self._make_params({}), self._mid
        )

    def ping(self) -> Any:
        """心跳检测。"""
        return self._client.call("ping", {}, self._mid)

    # ── 回调注册（框架进程端由事件总线处理，这里是 no-op）──

    def listen_game_chat(self, handler: Any) -> None:
        """注册游戏聊天监听（占位）。"""
        pass

    def listen_player_join(self, handler: Any) -> None:
        """注册玩家加入监听（占位）。"""
        pass

    def listen_player_leave(self, handler: Any) -> None:
        """注册玩家离开监听（占位）。"""
        pass

    def listen_group_message(self, handler: Any) -> None:
        """注册群消息监听（占位）。"""
        pass

    def register_console_command(self, triggers: Any, hint: str, usage: str, func: Any) -> None:
        """注册控制台命令（占位）。"""
        pass

    def get_plugin_api(self, name: str) -> Any:
        """获取插件 API（占位）。"""
        return None

    def is_user_admin(self, user_id: int, config_mgr: Any = None) -> bool:
        """检查用户是否为管理员。"""
        return False


class SyncIPCAdapterProxy(IPCAdapterProxy):
    """同步版 IPC 适配器代理 — 用于非异步上下文的测试和集成。

    包装 IPCClient 的同步 call 方法（如果有的话），或者
    在内部使用 asyncio.run_coroutine_threadsafe。
    """

    def __init__(self, call_fn: Any, caller_mid: int = 300):
        self._call_fn = call_fn
        self._mid = caller_mid

    def _make_params(self, params: dict) -> dict:
        params["_mid"] = self._mid
        return params

    def send_game_command(self, cmd: str) -> Any:
        return self._call_fn("sendcmd", self._make_params({"cmd": cmd}), self._mid)

    def send_game_command_raw(self, cmd: str) -> Any:
        return self._call_fn("sendcmd_raw", self._make_params({"cmd": cmd}), self._mid)

    def send_group_msg(self, group_id: int, message: str) -> Any:
        return self._call_fn(
            "send_group_msg",
            self._make_params({"group_id": group_id, "message": message}),
            self._mid,
        )

    def send_private_msg(self, user_id: int, message: str) -> Any:
        return self._call_fn(
            "send_private_msg",
            self._make_params({"user_id": user_id, "message": message}),
            self._mid,
        )

    def get_online_players(self) -> Any:
        return self._call_fn("get_online_players", self._make_params({}), self._mid)


def setup_ipc_mode(socket_path: str, token: str) -> tuple:
    """设置 IPC 模式，返回 (IPCClient, IPCAdapterProxy)。

    用于框架 __main__.py 在 --ipc-mode 时调用。
    """
    from .client import IPCClient

    client = IPCClient(socket_path)
    adapter = IPCAdapterProxy(client, caller_mid=300)
    return client, adapter
