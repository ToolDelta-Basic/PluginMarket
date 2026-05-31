"""事件总线 (EventBus) —— 带递归深度保护 + 线程安全 + 输入防御"""
import asyncio
import logging
import threading
import traceback
from contextvars import ContextVar
from typing import Callable, Any
from .events import BaseEvent
from .defguard import safe_event_message, safe_player_name
from .error_hints import hint

_recursion_depth: ContextVar[int] = ContextVar('event_recursion_depth', default=0)
MAX_EVENT_DEPTH = 10


def _sanitize_event(event: BaseEvent) -> None:
    """防御层: 在 publish 入口对所有事件做安全标准化。

    确保所有下游处理器收到的数据已经过验证：
    - message → 安全的字符串（绝不 None）
    - player_name → 安全的字符串（绝不 None）
    - 其他字段 → 按需处理
    """
    # GroupMessageEvent / PrivateMessageEvent: message
    if hasattr(event, 'message') and event.message is not None:
        event.message = safe_event_message(event.message)
    elif hasattr(event, 'message'):
        event.message = ""

    # GameChatEvent: message + player_name
    if hasattr(event, 'player_name'):
        event.player_name = safe_player_name(event.player_name)

    # PlayerJoinEvent / PlayerLeaveEvent: player_name
    if hasattr(event, 'player_name') and not hasattr(event, 'message'):
        event.player_name = safe_player_name(event.player_name)


class EventBus:
    """线程安全的发布-订阅事件总线，支持协程处理器。"""

    def __init__(self):
        """初始化事件总线，创建专用后台事件循环。"""
        self._subscribers: dict[str, list[tuple[int, Callable]]] = {}
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
        """订阅事件。"""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append((priority, handler))
            self._subscribers[event_type].sort(key=lambda x: x[0], reverse=True)

    def unsubscribe(self, event_type: str, handler: Callable):
        """取消订阅。"""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    (p, h) for p, h in self._subscribers[event_type] if h != handler
                ]

    async def publish(self, event: BaseEvent):
        """发布事件，依次调用所有订阅的处理函数。

        入口防御: 对事件的 message/player_name 字段做安全标准化处理，
        确保所有处理器收到的都是合法值。
        """
        depth = _recursion_depth.get()
        if depth >= MAX_EVENT_DEPTH:
            logging.getLogger(__name__).error(
                "事件 %s 达到最大递归深度 %d，已丢弃。%s",
                type(event).__name__,
                MAX_EVENT_DEPTH,
                hint.EVENT_RECURSION_LIMIT,
            )
            return

        # ── 防御层: 标准化事件数据 ──
        _sanitize_event(event)

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
                        "事件处理异常 %s: %s。%s\n%s",
                        event_type,
                        e,
                        hint.EVENT_HANDLER_FAILED,
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
