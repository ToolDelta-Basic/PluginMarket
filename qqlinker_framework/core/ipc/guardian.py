import argparse
import asyncio
import logging
import os
import signal
import sys

# ── 确保框架根目录在 sys.path ──
_FRAMEWORK_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from .server import IPCServer
from .client import IPCClient
from .protocol import (
    IPC_VERSION, DEFAULT_CAPABILITIES,
    make_event, make_hello_ack, _encode_message, _decode_line,
    is_hello, negotiate_capabilities,
)

_log = logging.getLogger(__name__)


class Guardian:
    """守护进程：独立运行 FrameworkHost + IPC 服务端。

    ToolDelta 插件薄壳通过 IPC 客户端连接本守护进程。
    """

    def __init__(self, socket_path: str, data_path: str):
        self.socket_path = socket_path
        self.data_path = data_path
        self._host = None
        self._server = IPCServer(socket_path)
        self._shell: asyncio.StreamWriter | None = None
        self._logger = logging.getLogger("guardian")
        # ── v1.5: IPC 版本协商 ──
        self._client_version: int | None = None
        self._client_capabilities: list = []
        self._negotiated_capabilities: list = []
        self._version_negotiated = False

    # ═══════════════════════════════════════════════════════════
    # IPC 处理器（薄壳 → 守护进程）
    # ═══════════════════════════════════════════════════════════

    async def _handle_start(self, params: dict) -> dict:
        """启动框架。params: {data_path}"""
        if self._host is not None:
            return {"ok": True, "msg": "already_started"}

        from ...libraries.channel_host import ChannelHost as FrameworkHost
        # 创建最小化适配器（不连任何外部服务，全通过 IPC 通信）
        from .guardian_adapter import GuardianAdapter
        adapter = GuardianAdapter(self)

        self._host = FrameworkHost(adapter, data_path=self.data_path, skip_ws=True)
        self._host.register_modules_from_package("qqlinker_framework.modules")
        self._host.register_external_modules()

        await self._host.start()
        self._logger.info("框架已启动")

        # 通知薄壳就绪
        await self._push_to_shell("started", {})
        return {"ok": True}

    async def _handle_stop(self, params: dict) -> dict:
        """停止框架。"""
        if self._host is None:
            return {"ok": True, "msg": "not_started"}
        try:
            await self._host.stop()
        except Exception as e:
            self._logger.error("stop 异常: %s", e)
        self._host = None
        await self._push_to_shell("stopped", {})
        return {"ok": True}

    async def _handle_group_message(self, params: dict) -> dict:
        """转发群消息到框架事件总线。"""
        if self._host is None:
            return {"ok": False, "error": "framework not started"}

        from ...core.kernel.events import GroupMessageEvent
        event = GroupMessageEvent(
            user_id=params.get("user_id", 0),
            group_id=params.get("group_id", 0),
            nickname=params.get("nickname", ""),
            message=params.get("message", ""),
            raw_data=params.get("raw_data", {}),
        )
        await self._host.event_bus.publish(event)
        return {"ok": True}

    async def _handle_ping(self, params: dict) -> dict:
        return {"pong": True, "framework_ready": self._host is not None}

    async def _handle_cmd(self, params: dict) -> dict:
        """直接执行命令（供 GameCommand 转发）。"""
        if self._host is None:
            return {"ok": False}
        cmd = params.get("command", "")
        adapter = self._host.services.try_get("adapter")
        if adapter and cmd:
            await adapter.send_game_command(cmd)
        return {"ok": True}

    async def _handle_hello(self, params: dict) -> dict:
        """处理客户端 HELLO 握手 — 版本协商。

        客户端连接后发送 HELLO，服务端回复 HELLO_ACK。
        如果版本不匹配，记录警告但不拒绝连接（降级运行）。
        """
        client_version = params.get("version", 0)
        client_caps = params.get("capabilities", [])
        self._client_version = client_version
        self._client_capabilities = client_caps

        if client_version != IPC_VERSION:
            self._logger.warning(
                "IPC 版本不匹配: 客户端 v%d, 服务端 v%d。降级运行。",
                client_version, IPC_VERSION,
            )
        else:
            self._logger.info(
                "IPC 版本协商成功: v%d, 客户端能力=%s",
                client_version, client_caps,
            )

        # 协商共同支持的能力
        self._negotiated_capabilities = negotiate_capabilities(
            client_caps, DEFAULT_CAPABILITIES
        )
        self._version_negotiated = True

        self._logger.info(
            "协商能力: %s (客户端=%d, 服务端=%d, 交集=%d)",
            self._negotiated_capabilities,
            len(client_caps), len(DEFAULT_CAPABILITIES),
            len(self._negotiated_capabilities),
        )

        return {
            "type": "HELLO_ACK",
            "version": IPC_VERSION,
            "capabilities": DEFAULT_CAPABILITIES,
        }

    def has_capability(self, cap: str) -> bool:
        """检查协商后是否支持指定能力。"""
        return cap in self._negotiated_capabilities

    def get_capabilities(self) -> list:
        """返回协商后的能力列表。"""
        return list(self._negotiated_capabilities)

    def is_version_negotiated(self) -> bool:
        """版本协商是否已完成。"""
        return self._version_negotiated

    # ═══════════════════════════════════════════════════════════
    # 反向通道（守护进程 → 薄壳）
    # ═══════════════════════════════════════════════════════════

    def set_shell(self, writer: asyncio.StreamWriter | None):
        """设置薄壳连接（由 GuardianAdapter 管理）。"""
        self._shell = writer

    async def _push_to_shell(self, event: str, data: dict) -> None:
        """推送事件到薄壳。"""
        if self._shell is None:
            return
        try:
            msg = make_event(event, data)
            self._shell.write(_encode_message(msg))
            await self._shell.drain()
        except Exception as e:
            self._logger.debug("推送失败: %s", e)

    async def push_send_group_msg(self, group_id: int, message: str) -> None:
        if not self.has_capability("send_group_msg"):
            self._logger.debug("能力 'send_group_msg' 未协商，跳过推送")
            return
        await self._push_to_shell("send_group_msg", {
            "group_id": group_id, "message": message,
        })

    async def push_send_private_msg(self, user_id: int, message: str) -> None:
        if not self.has_capability("send_private_msg"):
            self._logger.debug("能力 'send_private_msg' 未协商，跳过推送")
            return
        await self._push_to_shell("send_private_msg", {
            "user_id": user_id, "message": message,
        })

    async def push_game_command(self, cmd: str) -> None:
        if not self.has_capability("game_command"):
            self._logger.debug("能力 'game_command' 未协商，跳过推送")
            return
        await self._push_to_shell("game_command", {"command": cmd})

    async def push_get_online_players(self) -> None:
        if not self.has_capability("player_list"):
            self._logger.debug("能力 'player_list' 未协商，跳过推送")
            return
        await self._push_to_shell("get_online_players", {})

    # ═══════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════

    async def start(self) -> None:
        """启动守护进程。"""
        # 注册 IPC 方法
        self._server.register("start", self._handle_start)
        self._server.register("stop", self._handle_stop)
        self._server.register("group_message", self._handle_group_message)
        self._server.register("cmd", self._handle_cmd)
        self._server.register("ping", self._handle_ping)
        # v1.5: 注册版本协商 HELLO 处理器
        self._server.register("HELLO", self._handle_hello)

        # 启动 IPC Server（接受薄壳连接）
        await self._server.start()
        self._logger.info("守护进程已就绪: %s", self.socket_path)

    async def stop(self) -> None:
        """停止守护进程。"""
        if self._host:
            try:
                await self._host.stop()
            except Exception as e:
                _log.warning("guardian.stop: %s", e)
            self._host = None
        await self._server.stop()
        self._logger.info("守护进程已停止")


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

def main():
    """守护进程入口。"""
    parser = argparse.ArgumentParser(description="QQLinker 守护进程")
    parser.add_argument("--socket", default="/tmp/qqlinker-guardian.sock",
                        help="Unix socket 路径")
    parser.add_argument("--data-path", default=".",
                        help="数据目录路径")
    parser.add_argument("--log-level", default="INFO",
                        help="日志级别")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    guardian = Guardian(args.socket, args.data_path)

    async def run():
        await guardian.start()
        # 等待信号
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
        await guardian.stop()

    try:
        asyncio.run(run())
    except KeyboardInterrupt as e:
        _log.debug("guardian.run: %s", e)


if __name__ == "__main__":
    main()
