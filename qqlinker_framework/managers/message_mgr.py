import asyncio
import time
import logging
_log = logging.getLogger(__name__)
from enum import IntEnum
from typing import Optional

from qqlinker_framework.core.kernel.error_hints import hint

# 单条消息发送超时（秒）
DISPATCH_TIMEOUT = 5.0


class SendPriority(IntEnum):
    """消息发送优先级枚举。"""

    HIGH = 0
    NORMAL = 1
    LOW = 2


class MessageManager:
    """基于令牌桶的削峰填谷消息队列管理器。

    v2.0: _dispatch 加 asyncio.wait_for(timeout=5.0) 超时保护。
    """

    def __init__(self, adapter):
        """初始化消息管理器。"""
        self._adapter = adapter
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._rate_limit = 20
        self._max_burst = self._rate_limit * 3
        self._tokens = self._max_burst
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def start(self):
        """启动后台发送协程。"""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        """停止后台协程，排空队列中的高优先级消息。"""
        self._running = False
        if self._worker_task:
            # 排空队列中已有的高优先级消息（最多排空 50 条）
            drained = 0
            while drained < 50 and not self._queue.empty():
                try:
                    task = self._queue.get_nowait()
                    await self._dispatch(task)
                    drained += 1
                except Exception:
                    break
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError as e:
                _log.debug("message_mgr.stop: %s", e)

    async def send_group(
        self,
        group_id: int,
        message: str,
        priority: SendPriority = SendPriority.NORMAL,
    ):
        """将群消息推入发送队列。"""
        await self._queue.put((priority, ("group", group_id, message)))

    async def send_private(
        self,
        user_id: int,
        message: str,
        priority: SendPriority = SendPriority.NORMAL,
    ):
        """将私聊消息推入发送队列。"""
        await self._queue.put((priority, ("private", user_id, message)))

    async def _worker(self):
        """后台工作协程，不断从队列取任务并限流发送。"""
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
                logger.error("消息发送异常: %s。%s", e, hint["WS_SEND_FAILED"])

    async def _dispatch(self, task: tuple):
        """执行实际发送操作（v2.0: 超时保护）。"""
        _, (msg_type, target, text) = task
        loop = asyncio.get_running_loop()
        try:
            if msg_type == "group":
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None, self._adapter.send_group_msg, target, text
                    ),
                    timeout=DISPATCH_TIMEOUT,
                )
            elif msg_type == "private":
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None, self._adapter.send_private_msg, target, text
                    ),
                    timeout=DISPATCH_TIMEOUT,
                )
        except asyncio.TimeoutError:
            logging.getLogger(__name__).warning(
                "消息发送超时 (%d秒): type=%s, target=%s, text[:80]=%s。跳过",
                DISPATCH_TIMEOUT, msg_type, target,
                str(text)[:80],
            )

    async def _wait_for_token(self):
        """令牌桶限流等待。"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._max_burst,                    # 限制突发
                self._tokens + elapsed * self._rate_limit,
            )
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            wait_time = (1 - self._tokens) / self._rate_limit
            self._tokens = 0
        await asyncio.sleep(wait_time)
