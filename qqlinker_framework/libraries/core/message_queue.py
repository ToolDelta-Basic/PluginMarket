"""消息队列库 — 令牌桶削峰 + 异步发送队列。

注册服务: "message"
依赖: 无
"""
import asyncio
import logging
import time
from typing import Optional

from ..channel_host import Library

_log = logging.getLogger(__name__)


class RateLimiter:
    """令牌桶限流器。"""

    def __init__(self, rate: int = 20, per_seconds: float = 60.0):
        self._rate = rate
        self._interval = per_seconds / rate
        self._tokens = float(rate)
        self._last = time.monotonic()

    def acquire(self) -> bool:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(float(self._rate), self._tokens + elapsed / self._interval)
        self._last = now
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False


class MessageQueue:
    """异步消息队列 — 令牌桶削峰后通过回调发出。"""

    def __init__(self, rate: int = 20, per_seconds: float = 60.0):
        self._limiter = RateLimiter(rate, per_seconds)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._send_callback = None  # 由 adapter_bridge 设置

    def set_send_callback(self, callback):
        """设置实际发送回调（由适配器桥接库调用）。"""
        self._send_callback = callback

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._drain())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def send_group(self, group_id: int, message: str, **kwargs) -> None:
        """发送群消息（入队）。

        kwargs 允许传入 requester_uid 等元数据（兼容旧代码）。
        """
        await self._queue.put(("group", group_id, message))

    async def send_private(self, user_id: int, message: str, **kwargs) -> None:
        """发送私聊消息（入队）。

        kwargs 允许传入 requester_uid 等元数据（兼容旧代码）。
        """
        await self._queue.put(("private", user_id, message))

    async def _drain(self) -> None:
        while self._running:
            try:
                msg_type, target, text = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                while not self._limiter.acquire():
                    await asyncio.sleep(0.1)
                if self._send_callback:
                    try:
                        self._send_callback(msg_type, target, text)
                    except Exception as e:
                        _log.error("消息发送失败: %s", e)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("消息队列异常")


class MessageQueueLibrary(Library):
    """消息队列库。"""

    name = "message_queue"
    version = "1.6.0"
    dependencies: list = []

    async def mount(self) -> None:
        queue = MessageQueue()
        await queue.start()
        self.services.register("message", queue, mid=300)
        self._queue = queue

    async def unmount(self) -> None:
        if hasattr(self, "_queue"):
            await self._queue.stop()
