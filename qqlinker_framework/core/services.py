"""服务容器 (ServiceContainer)"""
from typing import Any, Callable


class ServiceContainer:
    """简单的服务注册与获取容器，支持单例和工厂延迟创建。"""

    def __init__(self):
        """初始化空容器。"""
        self._services: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}

    def register(self, name: str, instance_or_factory: Any):
        """注册服务实例或工厂函数。

        Args:
            name: 服务名称。
            instance_or_factory: 实例或可调用工厂。
        """
        if callable(instance_or_factory):
            self._factories[name] = instance_or_factory
        else:
            self._services[name] = instance_or_factory

    def get(self, name: str) -> Any:
        """获取服务实例，如为工厂则调用并缓存。

        Args:
            name: 服务名称。

        Returns:
            服务实例。

        Raises:
            KeyError: 服务未注册。
        """
        if name in self._services:
            return self._services[name]
        if name in self._factories:
            instance = self._factories[name]()
            self._services[name] = instance
            return instance
        raise KeyError(f"服务 '{name}' 未注册")

    def has(self, name: str) -> bool:
        """检查服务是否已注册。

        Args:
            name: 服务名称。

        Returns:
            是否存在。
        """
        return name in self._services or name in self._factories
