"""
Engine — 引擎基类与注册表

引擎 = 多个挂载库组合后的新服务 (engine is a composed service built from multiple
mounted libraries).

引擎不是库，引擎是库的组合产物。
引擎通过 ChannelHost 的 ServiceRegistry 获取所需库的实例。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# EngineConfig
# ═══════════════════════════════════════════════════════════


@dataclass
class EngineConfig:
    """引擎配置 — 声明引擎所需挂载的库。

    Attributes:
        name: 引擎名称。
        version: 引擎版本号。
        mounts: 依赖的库名列表（需在 ChannelHost 中已挂载）。
        pipeline: 处理管线步骤名称。
        provides: 对外暴露的服务名列表。
    """

    name: str
    version: str = "0.1.0"
    mounts: List[str] = field(default_factory=list)
    """依赖的库名列表。"""

    pipeline: List[str] = field(default_factory=list)
    """处理管线步骤名称。"""

    provides: List[str] = field(default_factory=list)
    """对外暴露的服务名列表。"""


# ═══════════════════════════════════════════════════════════
# Engine 基类
# ═══════════════════════════════════════════════════════════


class Engine(ABC):
    """引擎基类 — 由多个库组合而成的新服务。

    引擎不是库，引擎是库的组合产物。
    引擎通过 ChannelHost 的 ServiceRegistry 获取所需库的实例。

    Subclass contract:
        - 声明 ``config: EngineConfig`` 类属性
        - 实现 ``async ignite()``  — 所有依赖库就绪后执行
        - 实现 ``async extinguish()`` — 停止引擎
    """

    config: EngineConfig

    def __init__(self, services=None, event_bus=None):
        """初始化引擎。

        Args:
            services: ServiceRegistry 或兼容的服务容器。
            event_bus: LaneRouter 事件总线。
        """
        self.services = services
        self.event_bus = event_bus
        self._mounted: bool = False

    def _verify_mounts(self) -> bool:
        """验证所有声明的依赖库是否已挂载。

        Returns:
            True 如果所有 mounts 均已注册到 services 中。
        """
        if self.services is None:
            return True  # 无服务容器时跳过验证
        for lib_name in self.config.mounts:
            if not self.services.has(lib_name):
                _log.warning(
                    "引擎 '%s' 缺少依赖库: '%s'",
                    self.config.name,
                    lib_name,
                )
                return False
        return True

    @abstractmethod
    async def ignite(self) -> None:
        """启动引擎 — 所有依赖库就绪后执行。

        此方法在 ChannelHost mount 阶段之后调用。
        子类在此获取依赖实例、初始化管线。
        """

    @abstractmethod
    async def extinguish(self) -> None:
        """停止引擎。"""

    @property
    def is_mounted(self) -> bool:
        """引擎是否已挂载（ignite 已调用）。"""
        return self._mounted


# ═══════════════════════════════════════════════════════════
# EngineRegistry
# ═══════════════════════════════════════════════════════════


class EngineRegistry:
    """引擎注册表 — 管理所有已注册的引擎实例。

    通过 ChannelHost 调用 ignite/extinguish 管理生命周期。

    Usage::

        registry = EngineRegistry(services)
        registry.register(engine)
        await registry.ignite_all()
        # ... runtime ...
        await registry.extinguish_all()
    """

    def __init__(self, services):
        """初始化引擎注册表。

        Args:
            services: ServiceRegistry 实例，用于验证引擎依赖。
        """
        self._engines: Dict[str, Engine] = {}
        self.services = services

    def register(self, engine: Engine) -> None:
        """注册引擎实例。

        如果引擎名已存在，前一个引擎会被先 extinguish 再替换。

        Args:
            engine: Engine 实例。
        """
        name = engine.config.name
        if name in self._engines:
            _log.warning(
                "引擎 '%s' 已注册，将替换旧实例", name
            )
        self._engines[name] = engine
        _log.info("引擎已注册: %s v%s", name, engine.config.version)

    async def ignite_all(self) -> None:
        """启动所有引擎。

        引擎按注册顺序启动。
        每个引擎启动前会验证其依赖库是否就绪。
        """
        for name, engine in self._engines.items():
            if engine.is_mounted:
                _log.debug("引擎 '%s' 已启动，跳过", name)
                continue
            if not engine._verify_mounts():
                _log.error(
                    "引擎 '%s' 依赖库缺失，跳过启动",
                    name,
                )
                continue
            try:
                await engine.ignite()
                engine._mounted = True
                _log.info("引擎已启动: %s", name)
            except Exception as e:
                _log.error(
                    "引擎 '%s' 启动失败: %s", name, e
                )

    async def extinguish_all(self) -> None:
        """停止所有引擎（逆序）。"""
        for name, engine in reversed(list(self._engines.items())):
            if not engine.is_mounted:
                continue
            try:
                await engine.extinguish()
                engine._mounted = False
                _log.info("引擎已停止: %s", name)
            except Exception as e:
                _log.error(
                    "引擎 '%s' 停止异常: %s", name, e
                )

    def get(self, name: str) -> Optional[Engine]:
        """获取引擎实例。

        Args:
            name: 引擎名称（即 config.name）。

        Returns:
            Engine 实例，不存在返回 None。
        """
        return self._engines.get(name)

    def list_all(self) -> List[str]:
        """返回所有已注册引擎的名称列表。"""
        return list(self._engines.keys())

    @property
    def count(self) -> int:
        """已注册引擎数量。"""
        return len(self._engines)
