"""消息管理器"""
import asyncio
import time
import logging
from enum import IntEnum
from typing import Optional


class SendPriority(IntEnum):
    HIGH = 0
    NORMAL = 1
    LOW = 2


class MessageManager:
    """基于令牌桶的削峰填谷消息队列管理器。"""

    def __init__(self, adapter):
        self._adapter = adapter
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._rate_limit = 20
        self._tokens = self._rate_limit
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def start(self):
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def send_group(
        self,
        group_id: int,
        message: str,
        priority: SendPriority = SendPriority.NORMAL,
    ):
        await self._queue.put((priority, ("group", group_id, message)))

    async def send_private(
        self,
        user_id: int,
        message: str,
        priority: SendPriority = SendPriority.NORMAL,
    ):
        await self._queue.put((priority, ("private", user_id, message)))

    async def _worker(self):
        logger = logging.getLogger(__name__)
        while self._running:
            try:
                task = await self._queue.get()
                await self._wait_for_token()
                await self._dispatch(task)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("消息发送异常: %s", e)

    async def _dispatch(self, task: tuple):
        _, (msg_type, target, text) = task
        loop = asyncio.get_running_loop()
        if msg_type == "group":
            await loop.run_in_executor(
                None, self._adapter.send_group_msg, target, text
            )
        elif msg_type == "private":
            await loop.run_in_executor(
                None, self._adapter.send_private_msg, target, text
            )

    async def _wait_for_token(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._rate_limit,
                self._tokens + elapsed * self._rate_limit,
            )
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            wait_time = (1 - self._tokens) / self._rate_limit
            self._tokens = 0
        await asyncio.sleep(wait_time)
