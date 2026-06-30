from __future__ import annotations

import asyncio
import logging
from typing import Optional

_log = logging.getLogger(__name__)


class PriorityEventQueue:
    """优先级事件队列。

    特性：
    - 同一优先级内严格 FIFO
    - 高优先级事件优先出队
    - 可配置最大容量，满时触发背压策略
    """

    def __init__(self, max_size: int = 1000):
        self._queues: dict[int, asyncio.Queue] = {}
        self._max_size = max_size
        self._cond = asyncio.Condition()

    async def put(self, event, priority: int = 0) -> bool:
        """放入事件。

        Returns:
            True 表示放入成功，False 表示队列已满。
        """
        if priority not in self._queues:
            self._queues[priority] = asyncio.Queue(maxsize=self._max_size)

        q = self._queues[priority]
        if q.full():
            return False
        await q.put(event)
        # 唤醒所有 get() 中的等待者
        async with self._cond:
            self._cond.notify_all()
        return True

    def put_nowait(self, event, priority: int = 0) -> bool:
        """同步放入事件（不阻塞）。

        Returns:
            True 表示放入成功，False 表示队列已满。
        """
        if priority not in self._queues:
            self._queues[priority] = asyncio.Queue(maxsize=self._max_size)

        q = self._queues[priority]
        if q.full():
            return False
        q.put_nowait(event)
        # 唤醒所有 get() 中的等待者
        # put_nowait 是同步调用，不能使用 async with
        # 但我们可以在没有竞争的情况下通知
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(self._cond_notify)
        except RuntimeError:
            pass
        return True

    def _cond_notify(self):
        """线程安全的 notify_all 回调。"""
        # 创建即时任务来通知
        asyncio.create_task(self._notify_waiters())

    async def _notify_waiters(self):
        async with self._cond:
            self._cond.notify_all()

    async def get(self):
        """从最高优先级队列取事件，同优先级 FIFO。

        如果所有队列都空，阻塞等待。使用 asyncio.Condition 而非 busy-wait。
        """
        while True:
            # 从高到低遍历优先级
            for p in sorted(self._queues.keys(), reverse=True):
                q = self._queues[p]
                try:
                    return q.get_nowait()
                except asyncio.QueueEmpty:
                    continue
            # 全空 → 等待通知
            async with self._cond:
                # 双重检查——可能在获取锁期间有新数据到来
                for p in sorted(self._queues.keys(), reverse=True):
                    q = self._queues[p]
                    try:
                        return q.get_nowait()
                    except asyncio.QueueEmpty:
                        continue
                await self._cond.wait()

    def empty(self) -> bool:
        """所有优先级队列是否都为空。"""
        return all(q.empty() for q in self._queues.values())

    def qsize(self) -> int:
        """队列中事件总数。"""
        return sum(q.qsize() for q in self._queues.values())

    @property
    def max_size(self) -> int:
        return self._max_size
