# core/services.py
"""服务容器 (ServiceContainer)"""
from typing import Any, Callable

class ServiceContainer:
    def __init__(self):
        self._services: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}

    def register(self, name: str, instance_or_factory: Any):
        if callable(instance_or_factory):
            self._factories[name] = instance_or_factory
        else:
            self._services[name] = instance_or_factory

    def get(self, name: str) -> Any:
        if name in self._services:
            return self._services[name]
        if name in self._factories:
            instance = self._factories[name]()
            self._services[name] = instance
            return instance
        raise KeyError(f"服务 '{name}' 未注册")

    def has(self, name: str) -> bool:
        return name in self._services or name in self._factories