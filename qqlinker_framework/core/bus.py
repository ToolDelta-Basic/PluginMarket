"""事件总线 (EventBus) —— 带递归深度保护 + 线程安全"""
import asyncio
import logging
import threading
import traceback
from contextvars import ContextVar
from typing import Callable, Any
from .events import BaseEvent

_recursion_depth: ContextVar[int] = ContextVar('event_recursion_depth', default=0)
MAX_EVENT_DEPTH = 10


class EventBus:
    """线程安全的发布-订阅事件总线，支持协程处理器。"""

    def __init__(self):
        """初始化事件总线。"""
        self._subscribers: dict[str, list[tuple[int, Callable]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Callable, priority: int = 0):
        """订阅事件。

        Args:
            event_type: 事件类名。
            handler: 处理函数，支持同步或异步。
            priority: 优先级，数值越大越先执行。
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append((priority, handler))
            self._subscribers[event_type].sort(key=lambda x: x[0], reverse=True)

    def unsubscribe(self, event_type: str, handler: Callable):
        """取消订阅。

        Args:
            event_type: 事件类名。
            handler: 要取消的处理函数。
        """
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    (p, h) for p, h in self._subscribers[event_type] if h != handler
                ]

    async def publish(self, event: BaseEvent):
        """发布事件，依次调用所有订阅的处理函数。

        Args:
            event: 事件实例。
        """
        depth = _recursion_depth.get()
        if depth >= MAX_EVENT_DEPTH:
            logging.getLogger(__name__).error(
                "事件 %s 达到最大递归深度 %d，已丢弃",
                type(event).__name__,
                MAX_EVENT_DEPTH,
            )
            return
        _recursion_depth.set(depth + 1)
        try:
            event_type = type(event).__name__
            with self._lock:
                handlers = list(self._subscribers.get(event_type, []))
            for _, handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logging.getLogger(__name__).error(
                        "事件处理异常 %s: %s\n%s",
                        event_type,
                        e,
                        traceback.format_exc(),
                    )
        finally:
            _recursion_depth.set(depth)

    def publish_sync(self, event: BaseEvent):
        """同步发布事件，用于非异步上下文（如广播回调）。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.publish(event))
            loop.close()
        else:
            asyncio.run_coroutine_threadsafe(self.publish(event), loop)
