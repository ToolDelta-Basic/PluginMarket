"""IPCServer — 异步 Unix socket 服务端.

特性:
    - 监听 unix socket (asyncio.start_server)
    - register(method, handler) 注册处理器
    - 并发连接，每个请求独立 task
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Awaitable

from qqlinker_framework.core.ipc.protocol import (
    ERR_INTERNAL,
    ERR_METHOD_NOT_FOUND,
    IPCError,
    REGISTRY,
    _decode_line,
    _encode_message,
    is_request,
)

logger = logging.getLogger(__name__)

Handler = Callable[[dict], Awaitable[Any]]


class IPCServer:
    """异步 Unix socket IPC 服务端."""

    def __init__(self, socket_path: str) -> None:
        self._path = socket_path
        self._server: asyncio.AbstractServer | None = None
        self._handlers: dict[str, Handler] = {}
        self._connections: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def register(self, method: str, handler: Handler) -> None:
        """注册方法处理器."""
        self._handlers[method] = handler
        REGISTRY[method] = handler

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动服务器."""
        # 清理旧的 socket 文件
        try:
            os.unlink(self._path)
        except OSError:
            pass
        self._server = await asyncio.start_unix_server(
            self._handle_client, self._path
        )
        os.chmod(self._path, 0o600)
        logger.info("IPCServer listening on %s", self._path)

    async def stop(self) -> None:
        """停止服务器."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        try:
            os.unlink(self._path)
        except OSError:
            pass
        for task in self._connections:
            task.cancel()
        if self._connections:
            await asyncio.gather(*self._connections, return_exceptions=True)
        self._connections.clear()
        logger.info("IPCServer stopped")

    # ------------------------------------------------------------------
    # 连接处理
    # ------------------------------------------------------------------

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """处理单个客户端连接."""
        peer = writer.get_extra_info("socket")
        logger.debug("New connection: %s", peer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                msg = _decode_line(line.decode("utf-8").strip())
                if is_request(msg):
                    task = asyncio.create_task(self._dispatch(msg, writer))
                    self._connections.add(task)
                    task.add_done_callback(self._connections.discard)
        except IPCError:
            pass
        except OSError:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except OSError:
                pass
            logger.debug("Connection closed: %s", peer)

    async def _dispatch(self, msg: dict, writer: asyncio.StreamWriter) -> None:
        """分发请求到注册的处理器."""
        req_id = msg["id"]
        method = msg["method"]
        params = msg.get("params", {})
        handler = self._handlers.get(method)
        if handler is None:
            resp = {
                "id": req_id,
                "error": {"code": ERR_METHOD_NOT_FOUND, "message": f"Method not found: {method}"},
            }
        else:
            try:
                import inspect
                result = handler(params)
                if inspect.isawaitable(result):
                    result = await result
                resp = {"id": req_id, "result": result}
            except IPCError as exc:
                resp = {"id": req_id, "error": {"code": exc.code, "message": exc.raw_message}}
            except Exception as exc:
                logger.exception("Handler '%s' error", method)
                resp = {
                    "id": req_id,
                    "error": {"code": ERR_INTERNAL, "message": str(exc)},
                }
        try:
            writer.write(_encode_message(resp))
            await writer.drain()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "IPCServer":
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.stop()
