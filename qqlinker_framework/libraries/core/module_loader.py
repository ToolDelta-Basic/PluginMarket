"""模块加载库 — 模块发现 + 拓扑排序 + @command 装饰器扫描 + scope 注入。

注册服务: "module_loader"
依赖: config_store, command_registry, message_queue
"""
import importlib
import importlib.util
import inspect
import json
import logging
import os
import pkgutil
import threading
from typing import Any, Dict, List, Optional, Set, Type

from ..channel_host import Library

_log = logging.getLogger(__name__)


class ModuleRegistry:
    """模块注册表 — JSON 文件管理模块启用状态。"""

    def __init__(self, data_path: str):
        self._path = os.path.join(data_path, "注册表", "模块注册表.json")
        self._lock = threading.Lock()
        self._entries: Dict[str, dict] = {}
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._load()

    def _load(self) -> None:
        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._entries = json.load(f).get("模块注册表", {})
            except Exception:
                self._entries = {}

    def _save(self) -> None:
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"模块注册表": self._entries}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except OSError:
            pass

    def is_enabled(self, name: str) -> bool:
        entry = self._entries.get(name)
        if entry is None:
            return True  # 未注册默认启用
        return entry.get("启用", True)

    def auto_register(self, names: list) -> Set[str]:
        new_set: Set[str] = set()
        with self._lock:
            for n in names:
                if n not in self._entries:
                    self._entries[n] = {"启用": True, "首次发现": "auto"}
                    new_set.add(n)
            if new_set:
                self._save()
        return new_set

    def stats(self) -> str:
        total = len(self._entries)
        enabled = sum(1 for e in self._entries.values() if e.get("启用", True))
        return f"{enabled}/{total} 已启用"


class ModuleLoaderLibrary(Library):
    """模块加载库。"""

    name = "module_loader"
    version = "1.6.0"
    dependencies = ["config_store", "command_registry", "message_queue"]

    async def mount(self) -> None:
        data_path = self.services.get("_data_path")
        self._loaded: Dict[str, Any] = {}
        registry = ModuleRegistry(data_path)
        self.services.register("module_registry", registry, mid=100)
        self.services.register("module_loader", self, mid=100)
        self.services.register("modules", ModulesService(self), mid=300)

        # 发现模块
        from qqlinker_framework.core.module import Module
        modules_package = "qqlinker_framework.modules"

        try:
            classes = self._discover_from_package(modules_package, Module)
        except Exception as e:
            _log.error("模块发现失败: %s", e)
            classes = []

        if not classes:
            _log.warning("未发现任何模块")
            return

        # 自动注册
        names = [getattr(cls, 'name', '') for cls in classes if getattr(cls, 'name', '')]
        registry.auto_register(names)

        # 拓扑排序
        sorted_classes = self._sort_by_deps(classes, Module)

        # 实例化 + 装饰器扫描 + 初始化
        command_mgr = self.services.get("command")
        loaded_count = 0

        for cls in sorted_classes:
            mod_name = getattr(cls, 'name', '') or cls.__name__
            if not registry.is_enabled(mod_name):
                _log.debug("模块 '%s' 已禁用，跳过", mod_name)
                continue

            try:
                # 创建 scope 视图
                # 解析 mid: 模块自身声明 > 包组声明 > 默认300
                mid = self._resolve_mid(cls)
                scoped = self.services.scope(mid)

                # 实例化（传入 scoped services + event_bus）
                mod = cls(services=scoped, event_bus=self.events)

                # 约定注入（default_config 注册、config_schema 初始化等）
                if hasattr(mod, '_apply_conventions'):
                    mod._apply_conventions()

                # 装饰器扫描 — 注册命令到全局 CommandRegistry
                self._scan_decorators(mod, command_mgr)

                # 调用 on_init
                if hasattr(mod, 'on_init'):
                    await mod.on_init()

                # on_init 后执行约定（工具注册 + 定时任务启动）
                if hasattr(mod, '_post_init_conventions'):
                    await mod._post_init_conventions()

                self._loaded[mod_name] = mod
                loaded_count += 1
                _log.debug("模块加载成功: %s (mid=%d)", mod_name, mid)

            except Exception as e:
                _log.error("模块 '%s' 加载失败: %s", mod_name, e)

        _log.info("模块加载完成: %d/%d", loaded_count, len(sorted_classes))

        # 同步到 host.module_mgr._loaded_modules（兼容 kernel_cmds 等模块）
        host_module_mgr = self.services.try_get("_host_module_mgr")
        if host_module_mgr and hasattr(host_module_mgr, '_loaded_modules'):
            host_module_mgr._loaded_modules = dict(self._loaded)

    async def unmount(self) -> None:
        pass

    def _discover_from_package(self, package_name: str, base_class: type) -> List[type]:
        """递归扫描包，收集 Module 子类。"""
        result: List[type] = []
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            return result
        self._walk_package(package, package_name, base_class, result)
        return result

    def _walk_package(self, package, package_name: str, base_class: type, result: list):
        prefix = package_name + "."
        for _, modname, ispkg in pkgutil.iter_modules(package.__path__, prefix=prefix):
            if ispkg:
                try:
                    sub_pkg = importlib.import_module(modname)
                    self._walk_package(sub_pkg, modname, base_class, result)
                except Exception as e:
                    _log.debug("导入子包 %s 失败: %s", modname, e)
            else:
                try:
                    mod = importlib.import_module(modname)
                except Exception as e:
                    _log.debug("导入模块 %s 失败: %s", modname, e)
                    continue
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, base_class)
                        and attr is not base_class
                        and getattr(attr, "name", None)
                    ):
                        result.append(attr)

    def _sort_by_deps(self, classes: list, base_class: type) -> list:
        """按 dependencies 拓扑排序。"""
        name_map = {getattr(c, 'name', ''): c for c in classes if getattr(c, 'name', '')}
        in_degree = {n: 0 for n in name_map}
        graph = {n: [] for n in name_map}

        for cls in classes:
            name = getattr(cls, 'name', '')
            if not name:
                continue
            for dep in getattr(cls, 'dependencies', []):
                if dep in name_map:
                    graph[dep].append(name)
                    in_degree[name] += 1

        queue = [n for n, d in in_degree.items() if d == 0]
        sorted_names = []
        while queue:
            n = queue.pop(0)
            sorted_names.append(n)
            for neighbor in graph.get(n, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        result = [name_map[n] for n in sorted_names if n in name_map]
        # 追加未排序的（循环依赖）
        for cls in classes:
            if cls not in result:
                result.append(cls)
        return result

    def _resolve_mid(self, cls: type) -> int:
        """解析模块的 mid 值。"""
        import sys
        cls_dict = cls.__dict__
        # 显式声明
        if 'mid' in cls_dict:
            return cls_dict['mid']
        if 'uid' in cls_dict and not isinstance(cls_dict.get('uid'), property):
            return cls_dict['uid']
        if 'tier' in cls_dict and not isinstance(cls_dict.get('tier'), property):
            return cls_dict['tier']
        # 从包 MODULE_GROUP 继承
        try:
            pkg_name = cls.__module__.rsplit('.', 1)[0]
            parent_pkg = sys.modules.get(pkg_name)
            if parent_pkg and hasattr(parent_pkg, 'MODULE_GROUP'):
                grp = parent_pkg.MODULE_GROUP
                if 'mid' in grp:
                    return grp['mid']
        except Exception:
            pass
        return 300

    def _scan_decorators(self, mod, command_mgr) -> None:
        """扫描 @command / @listen / @tool / @schedule 装饰器，注册到对应管理器。"""
        for _, method in inspect.getmembers(mod, predicate=inspect.ismethod):
            if hasattr(method, '_command_info'):
                info = method._command_info
                min_uid = info.get('min_uid', 400)
                # 安全校验：非 root 模块不能注册比自己权限更高的命令
                if mod.mid > 0 and min_uid < mod.mid:
                    _log.warning(
                        "模块 '%s' (mid=%d) 命令 '%s' (min_uid=%d) 被拒绝",
                        mod.name, mod.mid, info.get('trigger', '?'), min_uid
                    )
                    continue

                # 多变体支持
                variants = info.get('variants', [info.get('trigger', '')])
                sub = info.get('sub', '')
                for variant in variants:
                    trigger = f"{variant} {sub}".strip() if sub else variant
                    command_mgr.register(
                        trigger, method,
                        cmd_type=info.get('type', 'group'),
                        description=info.get('description', ''),
                        op_only=info.get('op_only', False),
                        required_role=info.get('required_role', ''),
                        argument_hint=info.get('argument_hint', ''),
                        cooldown=info.get('cooldown') or 0.0,
                        min_uid=min_uid,
                        plugin=getattr(mod, 'name', ''),
                    )

            # @listen 装饰器扫描：注册事件监听器
            if hasattr(method, '_event_info'):
                info = method._event_info
                event_type = info.get('event_type', '')
                priority = info.get('priority', 0)
                if not event_type:
                    continue
                # 权限检查：非 root 模块只能订阅白名单事件
                _ALLOWED = {'GroupMessageEvent', 'PlayerJoinEvent',
                            'PlayerLeaveEvent', 'GameChatEvent',
                            'PrivateMessageEvent', 'ConfigReloadEvent'}
                if mod.mid > 0 and event_type not in _ALLOWED:
                    _log.warning(
                        "模块 '%s' (mid=%d) 装饰器声明订阅受限事件 '%s'，已拒绝",
                        mod.name, mod.mid, event_type,
                    )
                    continue
                # 通过 Module.listen() 注册（包含群级过滤包装）
                mod.listen(event_type, method, priority)

            # @tool 装饰器扫描：收集工具定义到 mod.tools
            if hasattr(method, '_tool_info'):
                tool_info = method._tool_info
                # 安全校验：非 root 模块工具 uid 下限
                tool_uid = tool_info.get('uid', 300)
                if mod.mid > 0 and tool_uid < mod.mid:
                    _log.warning(
                        "模块 '%s' (mid=%d) 装饰器声明工具 '%s' (uid=%d) 被拒绝",
                        mod.name, mod.mid,
                        tool_info.get('name', '<unnamed>'), tool_uid,
                    )
                    continue
                mod.tools.append(tool_info)

            # @schedule / @every / @cron 装饰器扫描：收集定时任务到 mod.scheduled
            if hasattr(method, '_schedule_info'):
                from qqlinker_framework.core.module import ScheduledTask
                info = method._schedule_info
                mod.scheduled.append(ScheduledTask(
                    name=info['name'],
                    handler=method,
                    interval=info.get('interval'),
                    cron=info.get('cron'),
                    run_on_start=info.get('run_on_start', False),
                    enabled=info.get('enabled', True),
                ))
                _log.debug(
                    "模块 '%s' 扫描到定时任务: %s",
                    getattr(mod, 'name', '?'), info['name'],
                )


# ═══════════════════════════════════════════════════════════
# ModulesService — 模块管理公共接口
# ═══════════════════════════════════════════════════════════

class ModulesService:
    """模块管理服务 — 模块通过 services.get("modules") 使用。"""

    def __init__(self, loader: "ModuleLoaderLibrary"):
        self._loader = loader

    def list_loaded(self) -> Dict[str, Any]:
        """列出已加载的模块 {name: instance}。"""
        return dict(self._loader._loaded)

    def get(self, name: str) -> Optional[Any]:
        """获取已加载的模块实例。"""
        return self._loader._loaded.get(name)

    async def freeze(self, name: str) -> bool:
        """冻结模块（从已加载列表移除）。"""
        if name in self._loader._loaded:
            mod = self._loader._loaded.pop(name)
            if hasattr(mod, 'on_stop'):
                try:
                    await mod.on_stop()
                except Exception:
                    pass
            return True
        return False

    async def unload(self, name: str) -> bool:
        """卸载模块。"""
        return await self.freeze(name)

    async def thaw(self, name: str) -> bool:
        """解冻模块（暂不支持热加载）。"""
        return False

    def count(self) -> int:
        return len(self._loader._loaded)
