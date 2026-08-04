from __future__ import annotations

import asyncio
import logging
_log = logging.getLogger(__name__)
import os
import secrets
import subprocess
import sys
import time
from typing import Any

from .server import IPCServer
from .game_proxy import PermissionGateway
from .command_filter import check_command_safety

logger = logging.getLogger(__name__)

__all__ = ["Shell"]

_MAX_RESTART = 3
_CONNECT_TIMEOUT = 10.0  # 秒
_RESTART_DELAY = 2.0  # 秒


class Shell:
    """IPC 薄壳 — 宿主端控制器。"""

    def __init__(self, plugin_instance: Any, framework_package: str = "qqlinker_framework"):
        self.plugin = plugin_instance
        self.game_ctrl = plugin_instance.game_ctrl
        self._socket_path = f"/tmp/qqlinker_ipc_{os.getpid()}.sock"
        self._token = secrets.token_hex(16)
        self._server: IPCServer | None = None
        self._framework_process: subprocess.Popen | None = None
        self._framework_package = framework_package
        self._gateway = PermissionGateway()
        self._restart_count = 0
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        self._connected_event: asyncio.Event | None = None

    # ──────────────────────────────────────────────────────────────────
    # 生命周期
    # ──────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 IPC Server + 框架子进程。"""
        self._running = True
        self._restart_count = 0

        # 1. 创建 IPCServer 并注册 RPC 处理器
        self._server = IPCServer(self._socket_path)
        self._register_handlers()
        await self._server.start()
        logger.info("Shell: IPC Server started at %s", self._socket_path)

        # 2. 启动框架子进程
        self._start_framework_process()

        # 3. 等待子进程连接（超时 10s）
        self._connected_event = asyncio.Event()
        try:
            await asyncio.wait_for(
                self._connected_event.wait(), timeout=_CONNECT_TIMEOUT
            )
            logger.info("Shell: Framework process connected")
        except asyncio.TimeoutError:
            logger.warning("Shell: Framework process did not connect within %ss", _CONNECT_TIMEOUT)

        # 4. 启动进程监控
        self._monitor_task = asyncio.create_task(self._monitor_process())

    async def stop(self) -> None:
        """停止框架子进程 + IPC Server。"""
        self._running = False

        # 取消监控
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError as e:
                _log.debug("shell.stop: %s", e)
            self._monitor_task = None

        # 终止子进程
        self._kill_framework_process()

        # 停止 IPC Server
        if self._server:
            await self._server.stop()
            self._server = None

        logger.info("Shell: stopped")

    # ──────────────────────────────────────────────────────────────────
    # 框架子进程管理
    # ──────────────────────────────────────────────────────────────────

    def _start_framework_process(self) -> None:
        """启动框架子进程。"""
        cmd = [
            sys.executable, "-m", self._framework_package,
            "--ipc-mode",
            "--socket", self._socket_path,
            "--token", self._token,
        ]
        try:
            self._framework_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "QQLINKER_IPC_TOKEN": self._token},
            )
            logger.info(
                "Shell: Framework process started (pid=%d)",
                self._framework_process.pid,
            )
        except OSError as e:
            logger.error("Shell: Failed to start framework process: %s", e)
            self._framework_process = None

    def _kill_framework_process(self) -> None:
        """终止框架子进程。"""
        if self._framework_process is None:
            return
        if self._framework_process.poll() is None:
            self._framework_process.terminate()
            try:
                self._framework_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._framework_process.kill()
                self._framework_process.wait()
        self._framework_process = None

    async def _monitor_process(self) -> None:
        """监控框架子进程，异常退出时自动重启（最多 3 次）。"""
        while self._running:
            await asyncio.sleep(1.0)

            if self._framework_process is None:
                continue

            retcode = self._framework_process.poll()
            if retcode is None:
                continue  # 还在运行

            logger.warning(
                "Shell: Framework process exited with code %d", retcode
            )

            if not self._running:
                break

            # 尝试重启
            if self._restart_count >= _MAX_RESTART:
                logger.error(
                    "Shell: Max restart attempts (%d) reached, giving up",
                    _MAX_RESTART,
                )
                break

            self._restart_count += 1
            delay = _RESTART_DELAY * self._restart_count
            logger.info(
                "Shell: Restarting framework (attempt %d/%d) in %.1fs",
                self._restart_count, _MAX_RESTART, delay,
            )
            await asyncio.sleep(delay)
            self._start_framework_process()

    # ──────────────────────────────────────────────────────────────────
    # RPC 处理器注册
    # ──────────────────────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        """注册所有 RPC 方法处理器到 IPCServer。"""
        assert self._server is not None
        self._server.register("sendcmd", self._handle_sendcmd)
        self._server.register("sendcmd_raw", self._handle_sendcmd_raw)
        self._server.register("send_group_msg", self._handle_send_group_msg)
        self._server.register("send_private_msg", self._handle_send_private_msg)
        self._server.register("get_online_players", self._handle_get_online_players)
        self._server.register("player_list", self._handle_get_online_players)
        self._server.register("ping", self._handle_ping)
        self._server.register("auth", self._handle_auth)

    # ──────────────────────────────────────────────────────────────────
    # RPC 处理实现
    # ──────────────────────────────────────────────────────────────────

    def _handle_rpc(self, method: str, params: dict, mid: int) -> Any:
        """处理 RPC 请求 — 调用真正的 game_ctrl。

        这里是真正接触 game_ctrl 的唯一入口。
        """
        # 权限网关检查
        allowed, reason = self._gateway.check_command(method, params, mid)
        if not allowed:
            from .protocol import IPCError
            raise IPCError(-100, reason)

        # 分发到 game_ctrl
        if method == "sendcmd":
            cmd = params.get("cmd", "")
            return self.game_ctrl.sendcmd(cmd)
        elif method == "sendcmd_raw":
            cmd = params.get("cmd", "")
            return self.game_ctrl.sendcmd(cmd)
        elif method == "send_group_msg":
            group_id = params.get("group_id", 0)
            message = params.get("message", "")
            return self.game_ctrl.send_group_msg(group_id, message)
        elif method == "send_private_msg":
            user_id = params.get("user_id", 0)
            message = params.get("message", "")
            return self.game_ctrl.send_private_msg(user_id, message)
        elif method == "get_online_players":
            return self.game_ctrl.get_online_players()
        else:
            from .protocol import IPCError, ERR_METHOD_NOT_FOUND
            raise IPCError(ERR_METHOD_NOT_FOUND, f"Unknown method: {method}")

    def _handle_sendcmd(self, params: dict) -> Any:
        """处理 sendcmd RPC。"""
        mid = params.pop("_mid", 300)
        return self._handle_rpc("sendcmd", params, mid)

    def _handle_sendcmd_raw(self, params: dict) -> Any:
        """处理 sendcmd_raw RPC。"""
        mid = params.pop("_mid", 0)
        return self._handle_rpc("sendcmd_raw", params, mid)

    def _handle_send_group_msg(self, params: dict) -> Any:
        """处理 send_group_msg RPC。"""
        mid = params.pop("_mid", 300)
        return self._handle_rpc("send_group_msg", params, mid)

    def _handle_send_private_msg(self, params: dict) -> Any:
        """处理 send_private_msg RPC。"""
        mid = params.pop("_mid", 300)
        return self._handle_rpc("send_private_msg", params, mid)

    def _handle_get_online_players(self, params: dict) -> Any:
        """处理 get_online_players RPC。"""
        mid = params.pop("_mid", 400)
        return self._handle_rpc("get_online_players", params, mid)

    def _handle_ping(self, params: dict) -> dict:
        """心跳。"""
        # 设置连接事件
        if self._connected_event and not self._connected_event.is_set():
            self._connected_event.set()
        return {"pong": True}

    def _handle_auth(self, params: dict) -> dict:
        """认证请求 — 验证 token。"""
        token = params.get("token", "")
        if token == self._token:
            if self._connected_event and not self._connected_event.is_set():
                self._connected_event.set()
            return {"ok": True}
        from .protocol import IPCError
        raise IPCError(-401, "invalid token")
