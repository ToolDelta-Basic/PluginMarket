"""ChannelHost — 纯信道框架启动器 v1.6.0

框架 = 通信信道。ChannelHost 创建信道本体（ServiceRegistry + EventBus），
扫描库目录，拓扑排序后顺序挂载。

信道本体不是库——它是库运行的基础设施。
"""
import asyncio
import importlib
import importlib.util
import inspect
import logging
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

_log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 异常
# ═══════════════════════════════════════════════════════════

class BootstrapError(Exception):
    """核心库缺失或启动失败时抛出。"""


# ═══════════════════════════════════════════════════════════
# ServiceRegistry — 信道服务总线
# ═══════════════════════════════════════════════════════════

class ServiceRegistry:
    """线程安全的服务注册表（带 mid 权限层级）。

    库直接使用 registry.get() — 无权限限制（库互信）。
    模块通过 registry.scope(mid) 拿到受限视图。
    """

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._mids: Dict[str, int] = {}
        self._lock = threading.Lock()

    def register(self, name: str, instance: Any, mid: int = 300, **kwargs) -> None:
        """注册服务。mid 越小权限越高（0=kernel, 100=daemon, 300=app）。

        kwargs 兼容旧代码传入 uid/_caller/is_factory 等参数（忽略）。
        _trusted 标记为库级注册（跳过白名单检查）。
        """
        # 兼容: uid 别名
        if 'uid' in kwargs and mid == 300:
            mid = kwargs['uid']
        # 白名单保护: 模块不可覆盖核心服务
        trusted = kwargs.get('_trusted', False)
        if not trusted and name in PROTECTED_SERVICES:
            with self._lock:
                if name in self._services:
                    _log.warning(
                        "服务注册被拒绝: '%s' 是受保护的核心服务，模块不可覆盖", name
                    )
                    return
        with self._lock:
            self._services[name] = instance
            self._mids[name] = mid

    def get(self, name: str) -> Any:
        """获取服务（库级，无权限检查）。"""
        with self._lock:
            if name not in self._services:
                raise KeyError(f"服务 '{name}' 未注册")
            return self._services[name]

    def try_get(self, name: str) -> Optional[Any]:
        """安全获取服务，不存在返回 None。"""
        with self._lock:
            return self._services.get(name)

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._services

    def list_all(self) -> List[str]:
        with self._lock:
            return list(self._services.keys())

    def get_mid(self, name: str) -> int:
        """获取服务的 mid 等级。"""
        with self._lock:
            return self._mids.get(name, 300)

    def scope(self, caller_mid: int) -> "ScopedView":
        """返回绑定 caller_mid 的受限视图。"""
        return ScopedView(self, caller_mid)


class ScopedView:
    """ServiceRegistry 的受限视图 — 模块只能访问 mid >= caller_mid 的服务。

    模块拿不到原始 registry，无法绕过权限检查。
    """

    __slots__ = ("_registry", "_mid")

    def __init__(self, registry: ServiceRegistry, mid: int):
        self._registry = registry
        self._mid = mid

    def get(self, name: str) -> Any:
        """获取服务（权限检查：service_mid >= 0 时，caller_mid 必须 <= service_mid）。"""
        service_mid = self._registry.get_mid(name)
        if self._mid > service_mid:
            raise PermissionError(
                f"权限不足: caller_mid={self._mid} 无法访问服务 '{name}' (service_mid={service_mid})"
            )
        return self._registry.get(name)

    def try_get(self, name: str) -> Optional[Any]:
        """安全获取服务，权限不足或不存在返回 None。"""
        try:
            return self.get(name)
        except (KeyError, PermissionError):
            return None

    def register(self, name: str, instance: Any, mid: Optional[int] = None, **kwargs) -> None:
        """注册服务（使用 scope 的 mid 或指定 mid）。模块通过此方法注册。"""
        # 兼容: uid 别名
        if 'uid' in kwargs and mid is None:
            mid = kwargs['uid']
        effective_mid = mid if mid is not None else self._mid
        # ScopedView 注册视为模块级（非 trusted）
        self._registry.register(name, instance, mid=effective_mid)

    def has(self, name: str) -> bool:
        return self._registry.has(name)

    def list_all(self) -> List[str]:
        return self._registry.list_all()

    def scope(self, mid: int) -> "ScopedView":
        """返回更低权限的视图（或相同权限）。"""
        effective = max(self._mid, mid)  # 不能提权
        return ScopedView(self._registry, effective)

    @property
    def mid(self) -> int:
        return self._mid

    # ── 兼容旧 ServiceContainer 接口（模块代码零改动）──

    def register_required_services(self, mid: int, required: list) -> None:
        """兼容: 旧模块调用，实际为空操作（服务已由库注册）。"""

    def register_dependency(self, module_name: str, service_name: str) -> None:
        """兼容: 依赖声明（空操作）。"""

    def get_all_entries(self) -> list:
        """兼容: 返回空列表。"""
        return []

    def is_allowed(self, name: str, mid: int) -> bool:
        """兼容: 服务注册表检查（始终允许）。"""
        return True


# ═══════════════════════════════════════════════════════════
# EventBus — 信道事件管道
# ═══════════════════════════════════════════════════════════

EventCallback = Callable[..., Any]


class EventBus:
    """线程安全的事件发布订阅总线。"""

    def __init__(self):
        self._handlers: Dict[str, List[tuple]] = defaultdict(list)
        self._lock = threading.Lock()
        self._depth = 0
        self._max_depth = 10

    def subscribe(self, event_type: str, callback: EventCallback, priority: int = 0):
        """订阅事件。priority 越大越早执行。"""
        with self._lock:
            self._handlers[event_type].append((priority, callback))
            self._handlers[event_type].sort(key=lambda x: -x[0])

    def unsubscribe(self, event_type: str, callback: EventCallback):
        """取消订阅。"""
        with self._lock:
            self._handlers[event_type] = [
                (p, cb) for p, cb in self._handlers[event_type]
                if cb is not callback
            ]

    async def publish(self, event_type: str, event: Any = None, source: str = ""):
        """发布事件，按优先级通知所有订阅者。

        如果 event 对象有 handled 属性且被设为 True，后续 handler 不再执行。

        Args:
            event_type: 事件类型名称字符串（如 "GroupMessageEvent"）
            event: 事件对象
            source: 发布来源标识
        """
        if self._depth >= self._max_depth:
            _log.warning("事件 %s 达到最大递归深度 %d，已丢弃。"
                         "事件触发链达到最大深度限制（%d层），已自动截断。"
                         "请检查是否有模块在处理 A 事件时又发布 A 事件。",
                         event_type, self._max_depth, self._max_depth)
            return
        self._depth += 1
        try:
            handlers = list(self._handlers.get(event_type, []))
            for _, callback in handlers:
                # 检查 event.handled — 若已标记则停止传播
                if event is not None and getattr(event, 'handled', False):
                    break
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    _log.error("事件处理异常 [%s]: %s", event_type, e)
        finally:
            self._depth -= 1


# ═══════════════════════════════════════════════════════════
# Library 基类
# ═══════════════════════════════════════════════════════════

class Library:
    """可挂载到信道的库。

    ChannelHost 挂载前注入 services/events。
    库通过这两个属性与其他库通信。
    """

    name: str = ""
    version: str = "0.0.0"
    dependencies: List[str] = []

    # ChannelHost 挂载前注入
    services: Optional[ServiceRegistry] = None
    events: Optional[EventBus] = None

    async def mount(self) -> None:
        """挂载库。"""

    async def unmount(self) -> None:
        """卸载库。"""


# ═══════════════════════════════════════════════════════════
# ChannelHost — 框架启动器
# ═══════════════════════════════════════════════════════════

# 核心库名称列表 — 缺失任何一个则拒绝启动
CORE_LIBRARIES = frozenset([
    "config_store",
    "group_config",
    "command_registry",
    "message_queue",
    "ws_client",
    "adapter_bridge",
    "module_loader",
    "event_router",
    "gatekeeper",
    "protocol",
    "audit",
    "security_tools",
])


class ChannelHost:
    """纯信道框架启动器。

    1. 创建信道本体（ServiceRegistry + EventBus）
    2. 扫描库目录
    3. 校验核心库完整性
    4. 拓扑排序
    5. 顺序 mount
    """

    def __init__(self, adapter=None, data_path: str = "."):
        self._data_path = os.path.abspath(data_path)
        self._adapter = adapter
        self._registry = ServiceRegistry()
        self._event_bus = EventBus()
        self._libraries: List[Library] = []
        self._sorted: List[Library] = []

        # 注册信道本体为服务（供库查询）
        self._registry.register("_registry", self._registry, mid=0)
        self._registry.register("_event_bus", self._event_bus, mid=0)
        self._registry.register("_data_path", self._data_path, mid=0)
        if adapter is not None:
            self._registry.register("adapter", adapter, mid=300)

        # 兼容属性（旧代码通过 host.xxx 访问）
        self.services = self._registry
        self.event_bus = self._event_bus
        self.package_mgr = _DummyPackageManager(self._data_path)
        self.module_mgr = _DummyModuleManager()
        # 注册 module_mgr 供 module_loader 同步已加载模块
        self._registry.register("_host_module_mgr", self.module_mgr, mid=0)
        self._registry.register("_host", self, mid=0)

    def register_modules_from_package(self, package_name: str = "qqlinker_framework.modules") -> None:
        """兼容: 模块发现（实际由 module_loader 库在 start() 时处理）。"""
        self._modules_package = package_name

    def register_external_modules(self) -> None:
        """兼容: 外部模块发现（空操作）。"""

    async def unload_module(self, module_name: str) -> bool:
        """兼容: 卸载模块（委托给 module_mgr）。"""
        return await self.module_mgr.freeze_module(module_name)

    async def reload_module(self, module_name: str) -> bool:
        """兼容: 重载模块。"""
        return False

    async def load_module(self, module_cls):
        """兼容: 加载模块。"""
        mod_name = getattr(module_cls, 'name', '') or module_cls.__name__
        try:
            mid = getattr(module_cls, 'mid', None) or getattr(module_cls, 'uid', None) or getattr(module_cls, 'tier', None) or 300
            scoped = self._registry.scope(mid)
            mod = module_cls(services=scoped, event_bus=self._event_bus)
            if hasattr(mod, '_apply_conventions'):
                mod._apply_conventions()
            if hasattr(mod, 'on_init'):
                await mod.on_init()
            self.module_mgr._loaded_modules[mod_name] = mod
            return mod
        except Exception as e:
            _log.error("加载模块 '%s' 失败: %s", mod_name, e)
            return None

    @property
    def data_path(self) -> str:
        return self._data_path

    @property
    def adapter(self):
        return self._adapter

    async def start(self) -> None:
        """启动框架。"""
        logger = _log

        # 1. 创建目录结构
        for d in ["模块", "工具", "工具/工具数据", "第三方库", "注册表", "日志"]:
            os.makedirs(os.path.join(self._data_path, d), exist_ok=True)

        # 2. 扫描库
        core_dir = os.path.join(os.path.dirname(__file__), "core")
        optional_dir = os.path.join(os.path.dirname(__file__), "optional")

        core_libs = self._scan_directory(core_dir)
        optional_libs = self._scan_directory(optional_dir)
        self._libraries = core_libs + optional_libs

        # 3. 校验核心库完整性
        found_names = {lib.name for lib in self._libraries}
        missing = CORE_LIBRARIES - found_names
        if missing:
            raise BootstrapError(
                f"核心库缺失，拒绝启动: {', '.join(sorted(missing))}"
            )

        # 4. 拓扑排序
        self._sorted = self._topo_sort(self._libraries)

        # 5. 顺序 mount
        for lib in self._sorted:
            lib.services = self._registry
            lib.events = self._event_bus
            logger.info("挂载库: %s v%s", lib.name, lib.version)
            try:
                await lib.mount()
            except Exception as e:
                if lib.name in CORE_LIBRARIES:
                    raise BootstrapError(
                        f"核心库 '{lib.name}' 挂载失败: {e}"
                    ) from e
                logger.error("可选库 '%s' 挂载失败（跳过）: %s", lib.name, e)

        logger.info("框架启动完成 (%d 个库)", len(self._sorted))

    async def stop(self) -> None:
        """停止框架（逆序卸载）。"""
        for lib in reversed(self._sorted):
            try:
                await lib.unmount()
                _log.info("卸载库: %s", lib.name)
            except Exception as e:
                _log.error("卸载库 '%s' 异常: %s", lib.name, e)

    # ── 内部方法 ──────────────────────────────────────────

    def _scan_directory(self, directory: str) -> List[Library]:
        """扫描目录下所有 .py 文件，找到 Library 子类并实例化。"""
        results: List[Library] = []
        if not os.path.isdir(directory):
            return results

        # 确定包导入路径
        # libraries/core/ -> qqlinker_framework.libraries.core
        # libraries/optional/ -> qqlinker_framework.libraries.optional
        dir_name = os.path.basename(directory)
        package_prefix = f"qqlinker_framework.libraries.{dir_name}"

        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            module_name = f"{package_prefix}.{filename[:-3]}"

            try:
                mod = importlib.import_module(module_name)

                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, Library)
                        and attr is not Library
                        and getattr(attr, "name", "")
                    ):
                        instance = attr()
                        results.append(instance)
            except Exception as e:
                _log.warning("扫描库文件失败 [%s]: %s", module_name, e)

        return results

    def _topo_sort(self, libraries: List[Library]) -> List[Library]:
        """拓扑排序（按 dependencies）。"""
        name_to_lib = {lib.name: lib for lib in libraries}
        in_degree: Dict[str, int] = {lib.name: 0 for lib in libraries}
        graph: Dict[str, List[str]] = {lib.name: [] for lib in libraries}

        for lib in libraries:
            for dep in lib.dependencies:
                if dep in name_to_lib:
                    graph[dep].append(lib.name)
                    in_degree[lib.name] += 1
                # 依赖不在已发现的库中 → 忽略（可选库可能缺失）

        queue = [n for n, d in in_degree.items() if d == 0]
        result: List[Library] = []

        while queue:
            name = queue.pop(0)
            result.append(name_to_lib[name])
            for neighbor in graph[name]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 循环依赖检测
        if len(result) != len(libraries):
            remaining = [lib.name for lib in libraries if lib not in result]
            _log.error("循环依赖: %s（强制追加）", remaining)
            result.extend(lib for lib in libraries if lib not in result)

        return result


# ═══════════════════════════════════════════════════════════
# 兼容对象 — 旧 FrameworkHost 接口模拟
# ═══════════════════════════════════════════════════════════

class _DummyPackageManager:
    """包管理器（自动安装缺失依赖）。"""

    def __init__(self, data_path: str = "."):
        self._requirements: Dict[str, str] = {}
        self._target_dir = os.path.join(data_path, "第三方库")
        os.makedirs(self._target_dir, exist_ok=True)
        # 确保 target_dir 在 sys.path 中
        import sys
        if self._target_dir not in sys.path:
            sys.path.insert(0, self._target_dir)

    def register_requirements(self, reqs: dict) -> None:
        self._requirements.update(reqs)

    def check_missing(self) -> dict:
        """检查缺失的 Python 包。"""
        missing = {}
        for pkg_name, import_name in self._requirements.items():
            try:
                importlib.import_module(import_name)
            except ImportError:
                missing[pkg_name] = import_name
        return missing

    def install_missing(self) -> bool:
        """自动安装缺失的包。"""
        import sys
        import subprocess
        import shutil

        missing = self.check_missing()
        if not missing:
            return True

        _log.info("自动安装缺失依赖: %s", ", ".join(missing.keys()))

        pyexec = sys.executable
        if "py" not in pyexec.lower():
            pyexec = shutil.which("python3") or shutil.which("python") or sys.executable

        mirrors = [
            "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple",
            "https://mirrors.aliyun.com/pypi/simple/",
            "https://pypi.org/simple/",
        ]

        for pkg_name in missing.keys():
            installed = False
            for mirror in mirrors:
                try:
                    cmd = [
                        pyexec, "-m", "pip", "install",
                        "--target", self._target_dir,
                        "-i", mirror,
                        "--no-deps",
                        pkg_name,
                    ]
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=60
                    )
                    if result.returncode == 0:
                        _log.info("✅ 已安装: %s", pkg_name)
                        installed = True
                        break
                except Exception as e:
                    continue
            if not installed:
                _log.error("❌ 安装失败: %s", pkg_name)
                return False
        return True

    def set_target_dir(self, path: str) -> None:
        self._target_dir = path
        os.makedirs(path, exist_ok=True)
        import sys
        if path not in sys.path:
            sys.path.insert(0, path)


class _DummyModuleManager:
    """模块管理器占位（提供 module_mgr._loaded_modules 兼容接口）。"""

    def __init__(self):
        self._loaded_modules: Dict[str, Any] = {}
        self.registry = None

    async def freeze_module(self, name: str) -> bool:
        if name in self._loaded_modules:
            del self._loaded_modules[name]
            return True
        return False

    async def thaw_module(self, name: str) -> bool:
        return False

    async def unload_module(self, name: str) -> bool:
        return await self.freeze_module(name)

    async def reload_module(self, name: str) -> bool:
        return False

    def get_loaded_modules(self) -> dict:
        return dict(self._loaded_modules)


# ═══════════════════════════════════════════════════════════
# 服务注册白名单
# ═══════════════════════════════════════════════════════════

# 框架核心服务 — 只有库（libraries/）可注册，模块不可覆盖
PROTECTED_SERVICES = frozenset([
    "config", "group_config", "command", "message", "ws_client",
    "protocol", "audit", "security", "modules", "gatekeeper",
    "uid_lookup", "module_registry", "module_loader", "dedup",
    "recovery", "framework_restart",
    "_registry", "_event_bus", "_data_path", "_host", "_host_module_mgr",
])
