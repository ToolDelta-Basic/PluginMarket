"""信道核心实现 — 服务注册 + 事件发布订阅。

这是信道本身的实现。不依赖任何框架旧代码。
其他所有库通过此信道通信。
"""
import asyncio
import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from ..core.channel import ChannelEvent, Library


class ServiceRegistry:
    """线程安全的服务注册表。纯信道，无关框架历史。"""

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def register(self, name: str, instance: Any) -> None:
        with self._lock:
            self._services[name] = instance

    def get(self, name: str) -> Any:
        with self._lock:
            if name not in self._services:
                raise KeyError(f"服务 '{name}' 未注册")
            return self._services[name]

    def try_get(self, name: str) -> Optional[Any]:
        with self._lock:
            return self._services.get(name)

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._services

    def list_all(self) -> List[str]:
        with self._lock:
            return list(self._services.keys())


EventCallback = Callable[[ChannelEvent], Any]


class EventBus:
    """线程安全的事件发布订阅。"""

    def __init__(self):
        self._handlers: Dict[str, List[tuple[int, EventCallback]]] = defaultdict(list)
        self._lock = threading.Lock()
        self._publish_depth = 0
        self._max_depth = 10

    def subscribe(self, event_type: str, callback: EventCallback, priority: int = 0):
        with self._lock:
            self._handlers[event_type].append((priority, callback))
            self._handlers[event_type].sort(key=lambda x: -x[0])

    def unsubscribe(self, event_type: str, callback: EventCallback):
        with self._lock:
            self._handlers[event_type] = [
                (p, cb) for p, cb in self._handlers[event_type]
                if cb is not callback
            ]

    async def publish(self, event: ChannelEvent, source: str = ""):
        if self._publish_depth >= self._max_depth:
            return
        self._publish_depth += 1
        try:
            event._source_library = source
            for _, callback in list(self._handlers.get(type(event).__name__, [])):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception:
                    pass
        finally:
            self._publish_depth -= 1


class CoreLibrary(Library):
    """信道核心库 — 总是第一个挂载。"""

    name = "core"
    version = "1.0.0"
    dependencies = []

    async def mount(self) -> None:
        registry = ServiceRegistry()
        bus = EventBus()

        # 暴露信道
        self._services = registry
        self._events = bus
        self.services = registry
        self.events = bus

        # 信道自己注册到信道（让其他库也能拿到 services/events）
        registry.register("services", registry)
        registry.register("events", bus)

    async def unmount(self) -> None:
        pass
