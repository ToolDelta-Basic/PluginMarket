"""事件总线 (EventBus) —— 递归深度保护 + 线程安全 + 输入防御 + Copy-on-Write"""
import asyncio
import logging
import threading
import traceback
from contextvars import ContextVar
from typing import Callable, Tuple
from .events import BaseEvent
from .defguard import safe_event_message, safe_player_name
from .error_hints import hint

_recursion_depth: ContextVar[int] = ContextVar('event_recursion_depth', default=0)
MAX_EVENT_DEPTH = 10

# 不可变处理器元组类型 (priority, handler)
Subscriber = Tuple[int, Callable]


def _sanitize_event(event: BaseEvent) -> None:
    """防御层: 在 publish 入口对所有事件做安全标准化。"""
    if hasattr(event, 'message') and event.message is not None:
        event.message = safe_event_message(event.message)
    elif hasattr(event, 'message'):
        event.message = ""
    if hasattr(event, 'player_name'):
        event.player_name = safe_player_name(event.player_name)


class EventBus:
    """线程安全的发布-订阅事件总线，Copy-on-Write 高性能发布。

    publish() 高频路径零拷贝：读取处理器时只持锁取引用，
    不需要 list() 复制。subscribe/unsubscribe 时重建不可变 tuple。
    """

    def __init__(self):
        self._subscribers: dict[str, Tuple[Subscriber, ...]] = {}
        self._lock = threading.Lock()
        self._sync_loop = asyncio.new_event_loop()
        self._sync_thread = threading.Thread(
            target=self._run_sync_loop, daemon=True
        )
        self._sync_thread.start()

    def _run_sync_loop(self):
        """后台线程的事件循环。"""
        asyncio.set_event_loop(self._sync_loop)
        self._sync_loop.run_forever()

    def subscribe(self, event_type: str, handler: Callable, priority: int = 0):
        """订阅事件（CoW 写路径：重建 tuple）。"""
        with self._lock:
            current = list(self._subscribers.get(event_type, ()))
            current.append((priority, handler))
            current.sort(key=lambda x: x[0], reverse=True)
            self._subscribers[event_type] = tuple(current)

    def unsubscribe(self, event_type: str, handler: Callable):
        """取消订阅（CoW 写路径：重建 tuple）。"""
        with self._lock:
            current = self._subscribers.get(event_type, ())
            filtered = tuple((p, h) for p, h in current if h != handler)
            self._subscribers[event_type] = filtered

    async def publish(self, event: BaseEvent):
        """发布事件（CoW 读路径：无复制，直接引用 tuple）。"""
        depth = _recursion_depth.get()
        if depth >= MAX_EVENT_DEPTH:
            logging.getLogger(__name__).error(
                "事件 %s 达到最大递归深度 %d，已丢弃。%s",
                type(event).__name__, MAX_EVENT_DEPTH,
                hint["EVENT_RECURSION_LIMIT"],
            )
            return

        _sanitize_event(event)
        _recursion_depth.set(depth + 1)
        try:
            event_type = type(event).__name__
            with self._lock:
                handlers = self._subscribers.get(event_type, ())
                # handlers 是 tuple，不可变，安全解锁后直接遍历
            for _, handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logging.getLogger(__name__).error(
                        "事件处理异常 %s: %s。%s\n%s",
                        event_type, e,
                        hint["EVENT_HANDLER_FAILED"],
                        traceback.format_exc(),
                    )
        finally:
            _recursion_depth.set(depth)

    def publish_sync(self, event: BaseEvent):
        """同步发布事件，使用后台专用事件循环。"""
        asyncio.run_coroutine_threadsafe(self.publish(event), self._sync_loop)

    def shutdown(self):
        """停止后台事件循环并等待线程退出。"""
        if self._sync_loop and self._sync_loop.is_running():
            self._sync_loop.call_soon_threadsafe(self._sync_loop.stop)
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5)
