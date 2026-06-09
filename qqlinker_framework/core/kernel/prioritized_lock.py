"""优先级锁 (PrioritizedLock) — 锁竞争防御

UID 越小优先级越高，同等级随机获取。

特性:
  - 等待队列按优先级排序（UID 越小越优先）
  - 同优先级的等待者随机选取（防饥饿）
  - 可配置等待超时（默认 5s）
  - 递归深度计数器防止死循环
"""
import asyncio
import logging
import random
import time
from .services import UID_NOBODY
from dataclasses import dataclass, field
from typing import Optional

_log = logging.getLogger(__name__)

# ── 默认配置 ──────────────────────────────────────────────

DEFAULT_LOCK_TIMEOUT = 5.0       # 默认获取超时（秒）
MAX_RECURSION_DEPTH = 10         # 最大递归深度


@dataclass(order=True)
class _Waiter:
    """锁等待者，按 (priority, random_key, timestamp) 排序。"""
    priority: int
    random_key: float = field(compare=True)
    timestamp: float = field(compare=False)
    event: asyncio.Event = field(compare=False, default_factory=asyncio.Event)


class PrioritizedLock:
    """优先级 asyncio 锁。

    等待者按 UID 从小到大排序（越小权限越高），同等级随机选取。

    用法:
        lock = PrioritizedLock()
        async with lock.acquire(uid=100):
            ...

    或带超时:
        try:
            async with lock.acquire(uid=100, timeout=2.0):
                ...
        except asyncio.TimeoutError:
            # 处理超时
    """

    def __init__(self, name: str = ""):
        self._name = name or "unnamed"
        self._locked = False
        self._waiters: list[_Waiter] = []
        self._recursion_depth = 0
        self._lock = asyncio.Lock()  # 保护内部状态

    def acquire(self, uid: int = UID_NOBODY, timeout: float = DEFAULT_LOCK_TIMEOUT):
        """返回异步上下文管理器，在退出时释放锁。

        Args:
            uid: 调用方 UID（越小优先级越高）。
            timeout: 获取超时秒数。

        Raises:
            asyncio.TimeoutError: 超时未获取锁。
        """
        return _PrioritizedLockContext(self, uid, timeout)

    async def _acquire(self, uid: int, timeout: float):
        """内部获取实现。"""
        # 递归深度检查
        async with self._lock:
            if self._recursion_depth >= MAX_RECURSION_DEPTH:
                _log.error(
                    "PrioritizedLock '%s': 递归深度超限 (%d)，拒绝获取。"
                    "UID=%d 可能陷入递归死循环。",
                    self._name, self._recursion_depth, uid,
                )
                raise RecursionError(
                    f"PrioritizedLock '{self._name}': "
                    f"max recursion depth ({MAX_RECURSION_DEPTH}) exceeded"
                )

        deadline = time.monotonic() + timeout

        # 创建等待者
        waiter = _Waiter(
            priority=uid,
            random_key=random.random(),
            timestamp=time.monotonic(),
        )

        async with self._lock:
            if not self._locked:
                self._locked = True
                self._recursion_depth += 1
                return

            self._waiters.append(waiter)

        # 等待被唤醒或超时
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError(
                    f"PrioritizedLock '{self._name}': acquire timed out"
                )

            await asyncio.wait_for(waiter.event.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            # 超时：从等待队列移除
            async with self._lock:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
            raise

    def _release(self):
        """释放锁，唤醒下一个等待者。"""
        # 等待者按优先级排序，同优先级随机
        self._waiters.sort(key=lambda w: (w.priority, w.random_key))
        if self._waiters:
            next_waiter = self._waiters.pop(0)
            next_waiter.event.set()
        else:
            self._locked = False
            self._recursion_depth = 0

    def release(self):
        """手动释放锁。"""
        self._recursion_depth = max(0, self._recursion_depth - 1)
        self._release()

    @property
    def locked(self) -> bool:
        return self._locked

    @property
    def waiters_count(self) -> int:
        return len(self._waiters)


class _PrioritizedLockContext:
    """PrioritizedLock 的异步上下文管理器。"""

    def __init__(self, lock: PrioritizedLock, uid: int, timeout: float):
        self._lock = lock
        self._uid = uid
        self._timeout = timeout

    async def __aenter__(self):
        await self._lock._acquire(self._uid, self._timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
        return False
