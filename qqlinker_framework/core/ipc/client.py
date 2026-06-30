from __future__ import annotations

import asyncio
import logging
_log = logging.getLogger(__name__)
from typing import Any

from .protocol import (
    ERR_DISCONNECTED,
    ERR_TIMEOUT,
    IPCError,
    _decode_line,
    _encode_message,
    make_error,
    make_event,
    make_request,
)

logger = logging.getLogger(__name__)

MAX_RECONNECT = 3
RECONNECT_DELAY = 0.5  # 秒


class IPCClient:
    """异步 Unix socket 客户端."""

    def __init__(self, socket_path: str) -> None:
        self._path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._recv_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._connected = False

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """建立连接，必要时重试."""
        for attempt in range(1, MAX_RECONNECT + 2):
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(self._path),
                    timeout=5.0,
                )
                self._connected = True
                self._recv_task = asyncio.create_task(self._recv_loop())
                logger.info("IPCClient connected to %s (attempt %d)", self._path, attempt)
                return
            except (OSError, asyncio.TimeoutError) as exc:
                logger.warning("IPCClient connect attempt %d failed: %s", attempt, exc)
                if attempt > MAX_RECONNECT:
                    raise IPCError(ERR_DISCONNECTED, f"Cannot connect to {self._path} after {attempt} attempts") from exc
                await asyncio.sleep(RECONNECT_DELAY * attempt)

    async def close(self) -> None:
        """关闭连接."""
        self._connected = False
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError as e:
                _log.debug("client.close: %s", e)
            self._recv_task = None
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
        self._reader = None
        # 拒绝所有等待中的 future
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(IPCError(ERR_DISCONNECTED, "Connection closed"))
        self._pending.clear()

    async def ensure_connected(self) -> None:
        """确保已连接，否则自动连接."""
        if not self._connected:
            async with self._lock:
                if not self._connected:
                    await self.connect()

    # ------------------------------------------------------------------
    # 接收循环
    # ------------------------------------------------------------------

    async def _recv_loop(self) -> None:
        """持续读取响应并分发到对应 future."""
        assert self._reader
        while self._connected:
            try:
                line = await asyncio.wait_for(self._reader.readline(), timeout=300)
            except asyncio.TimeoutError:
                continue
            except OSError:
                logger.warning("recv loop: read error, disconnecting")
                self._connected = False
                break
            if not line:
                logger.warning("recv loop: EOF, disconnecting")
                self._connected = False
                break
            try:
                msg = _decode_line(line.decode("utf-8").strip())
            except IPCError:
                continue
            msg_id = msg.get("id")
            if msg_id and msg_id in self._pending:
                fut = self._pending.pop(msg_id)
                if not fut.done():
                    if "error" in msg:
                        err = msg["error"]
                        fut.set_exception(IPCError(err["code"], err["message"]))
                    else:
                        fut.set_result(msg.get("result"))

    # ------------------------------------------------------------------
    # 发请求
    # ------------------------------------------------------------------

    async def call(self, method: str, params: dict | None = None, timeout: float = 10.0) -> Any:
        """发送请求并等待响应.

        Raises:
            IPCError: 超时或服务端返回错误.
        """
        await self.ensure_connected()
        req = make_request(method, params)
        req_id = req["id"]
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        try:
            self._writer.write(_encode_message(req))  # type: ignore[union-attr]
            await self._writer.drain()  # type: ignore[union-attr]
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise IPCError(ERR_TIMEOUT, f"Call '{method}' timed out after {timeout}s")

    async def notify(self, event: str, data: dict | None = None) -> None:
        """发送推送事件（不等待响应）."""
        await self.ensure_connected()
        msg = make_event(event, data)
        self._writer.write(_encode_message(msg))  # type: ignore[union-attr]
        await self._writer.drain()  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "IPCClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
