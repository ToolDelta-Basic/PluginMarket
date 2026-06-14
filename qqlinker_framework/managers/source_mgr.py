# pylint: disable=protected-access
"""加载源管理器 – 统一管理所有扫描/发现/加载/注册入口

从 ModuleManager 重构而来 (v8.0):
  - 统一模块发现: discover_from_package / discover_from_files
  - 统一工具扫描: scan_tool_directory / register_tool / get_ai_tools / get_admin_tools
  - 统一工作流扫描: scan_workflow_directory / register_workflow / get_workflows
  - 统一配置注册: register_config_section
  - 统一包管理: install_package / list_packages
  - 保留模块注册表（允则）

v1.2 — 新增启动依赖检查（服务存在性 + 循环依赖检测）
v7.0 — 注册表允则机制: 模块加载唯一权威来源 = 模块注册表 JSON
       只有注册表中明确标记"启用"的模块才运行，
       新发现的模块默认写入注册表并自动启用
v8.0 — 重构为 SourceManager，统一所有加载源
"""
import asyncio
import importlib
import inspect
import logging
import os as _os
import contextvars
from typing import Type, List, Optional, Set, Dict
from qqlinker_framework.core.module import Module, FrozenState
from qqlinker_framework.core.kernel.error_hints import hint
from qqlinker_framework.core.kernel.prioritized_lock import PrioritizedLock
from qqlinker_framework.core.drivers.registry import ModuleRegistry

# ── 递归深度防护 ──────────────────────────────────────────
_module_mgr_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    'module_mgr_recursion_depth', default=0
)
MAX_MODULE_MGR_DEPTH = 10


class SourceManager:
    """加载源管理器 — 统一管理所有扫描/发现/加载/注册入口。

    职责（代替原先分散在 ~20 处的扫描/加载/注册入口）:
      - 模块发现与三阶段加载
      - 工具扫描与注册（AI 工具 + 管理工具）
      - 工作流扫描与注册
      - 配置节注册
      - 包管理与依赖安装
      - 模块注册表（允则权威来源）

    v1.1: 使用 PrioritizedLock 替代 asyncio.Lock，支持:
      - 优先级供给（UID 越小越优先获得锁）
      - 递归深度防护（深度 > 10 时拒绝操作）
      - 获取超时保护（默认 5s）
    v8.0: 从 ModuleManager 重构为 SourceManager
    """

    def __init__(self, host,
                 registry: ModuleRegistry = None,
                 tool_mgr=None,
                 admin_tool_mgr=None,
                 package_mgr=None):
        self.host = host
        self.services = host.services
        self.event_bus = host.event_bus
        self._module_classes: List[Type[Module]] = []
        self._loaded_modules: dict[str, Module] = {}
        self._lock = PrioritizedLock(name="source_mgr")
        # 读路径上的轻量级保护
        self._read_lock = asyncio.Lock()
        # v7: 模块注册表 — 允则逻辑的唯一权威来源
        self._registry = registry
        # v8: 注入子管理器引用
        self._tool_mgr = tool_mgr
        self._admin_tool_mgr = admin_tool_mgr
        self._package_mgr = package_mgr
        # v8: 懒加载模块类注册表（background=False 的模块）
        self._lazy_classes: dict[str, Type[Module]] = {}

    @staticmethod
    def _check_depth() -> None:
        """递归深度检查，超限抛出 RecursionError。"""
        depth = _module_mgr_depth.get()
        if depth >= MAX_MODULE_MGR_DEPTH:
            raise RecursionError(
                f"SourceManager 递归深度超限 ({depth} >= {MAX_MODULE_MGR_DEPTH})。"
                f"{hint.get('UNEXPECTED_ERROR', '')}"
            )

    async def _acquire_lock(self, uid: int = 400, timeout: float = 5.0):
        """获取优先级锁（带递归深度检查）。

        获取成功后递增深度计数器，释放时递减。
        """
        self._check_depth()
        _module_mgr_depth.set(_module_mgr_depth.get() + 1)
        try:
            return await self._lock._acquire(uid, timeout)
        except Exception:
            _module_mgr_depth.set(_module_mgr_depth.get() - 1)
            raise

    def _release_lock(self) -> None:
        """释放锁并递减深度计数器。"""
        self._lock.release()
        _module_mgr_depth.set(max(0, _module_mgr_depth.get() - 1))

    def register_module(self, module_cls: Type[Module]):
        """注册模块类，若已存在则跳过（public API）。"""
        if module_cls not in self._module_classes:
            self._module_classes.append(module_cls)

    # 保留 register() 作为别名（向后兼容）
    def register(self, module_cls: Type[Module]):
        """注册模块类（向后兼容别名，等同于 register_module）。"""
        return self.register_module(module_cls)

    # ═══════════════════════════════════════════════════════════
    # v1.2: 启动依赖检查
    # ═══════════════════════════════════════════════════════════

    def validate_dependencies(self, mod: Module) -> tuple:
        """验证模块的 required_services 中的服务是否已注册。

        Returns:
            (ok: bool, missing: List[str], circular: List[str])
            - ok: True 表示所有依赖满足
            - missing: 缺失的服务列表
            - circular: 涉及循环依赖的模块列表
        """
        logger = logging.getLogger(__name__)
        missing: List[str] = []

        # ── 1. 检查 required_services 中的服务是否已注册 ──
        for srv_name in getattr(mod, 'required_services', []):
            if not self.services.has(srv_name):
                missing.append(srv_name)

        if missing:
            logger.error(
                "⛔ 模块 '%s' 依赖检查失败: 缺失服务 %s",
                mod.name, ", ".join(missing),
            )
            logger.error(
                "   已知服务: %s",
                ", ".join(sorted(self.services.list_accessible().keys()))
                if hasattr(self.services, 'list_accessible')
                else "(无法列出)",
            )
            return False, missing, []

        return True, [], []

    @staticmethod
    def check_circular_dependencies(mods: List[Module]) -> List[str]:
        """检测模块间的循环依赖（A 依赖 B，B 依赖 A）。

        使用 "类名 → required_services" 的边关系构建有向图，
        DFS 检测环。

        Returns:
            涉及循环依赖的所有模块名列表（空表示无环）。
        """
        logger = logging.getLogger(__name__)

        # 构建依赖图: module_name → set of depended_module_names
        dep_graph: Dict[str, Set[str]] = {}
        name_map: Dict[str, Module] = {}

        # 先完整构建 name_map，再构建依赖图
        for mod in mods:
            name = getattr(mod, 'name', mod.__class__.__name__)
            name_map[name] = mod
            dep_graph[name] = set()

        for mod in mods:
            name = getattr(mod, 'name', mod.__class__.__name__)
            for srv_name in getattr(mod, 'required_services', []):
                # 服务名可能与模块名相同（如 "message", "command"）
                if srv_name in name_map:
                    dep_graph[name].add(srv_name)
            for dep_name in getattr(mod, 'dependencies', []):
                if dep_name in name_map:
                    dep_graph[name].add(dep_name)

        # DFS 检测环
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {name: WHITE for name in dep_graph}
        cycle_nodes: Set[str] = set()

        def dfs(node: str, path: List[str]) -> bool:
            """DFS 遍历，返回是否发现环。"""
            color[node] = GRAY
            path.append(node)
            for neighbor in dep_graph.get(node, set()):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # 发现环: path 中从 neighbor 开始的部分
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:]
                    cycle_nodes.update(cycle)
                    logger.error(
                        "⛔ 检测到循环依赖: %s → %s（通过 %s）",
                        node, neighbor, " → ".join(cycle),
                    )
                    return True
                if color[neighbor] == WHITE:
                    if dfs(neighbor, path):
                        # 继续 DFS 以发现所有环
                        pass
            path.pop()
            color[node] = BLACK
            return False

        for node in list(dep_graph.keys()):
            if color.get(node) == WHITE:
                dfs(node, [])

        if cycle_nodes:
            logger.warning(
                "循环依赖涉及模块: %s。这些模块将按原始顺序加载。",
                ", ".join(sorted(cycle_nodes)),
            )

        return list(cycle_nodes)

    # ═══════════════════════════════════════════════════════════
    # v7: 注册表允则机制 — 模块加载唯一权威来源
    # ═══════════════════════════════════════════════════════════
    # 不再使用旧的 白名单/黑名单 配置项。
    # 改用 模块注册表 JSON 作为允则来源：
    #   - 注册表中明确标记 "启用": true → 允许加载
    #   - 注册表中标记 "启用": false 或不在注册表中 → 拒绝加载
    #   - 扫描到新模块时自动注册并默认启用

    def _is_module_loadable(self, name: str) -> bool:
        """判断模块是否应该被加载（v7: 注册表允则）。

        只有注册表中明确标记 "启用": true 的模块才允许加载。
        注册表为空时降级为全部加载（首次启动/文件损坏兜底）。
        """
        if self.registry is None:
            return True
        # 注册表为空 → 降级全部加载
        if not self.registry.get_all_entries():
            return True
        return self.registry.is_enabled(name)

    def _auto_register_new_modules(self, module_names: list) -> Set[str]:
        """自动注册新发现的模块到注册表（默认启用）。

        Returns:
            本次新注册的模块名集合。
        """
        if self.registry is None:
            return set()
        result = self.registry.auto_register(module_names)
        # 防御：如果注册表为空且刚追加了新模块，确保文件写盘
        all_enabled = self.registry.get_all_enabled()
        if not all_enabled and module_names:
            # 注册表为空 → 降级为全部加载（可能是文件写入失败）
            _log = logging.getLogger(__name__)
            _log.warning("注册表为空，降级为全部加载 (%d 个模块)", len(module_names))
            self.registry.auto_register(module_names)
        return result

    # ═══════════════════════════════════════════════════════════
    # 批量初始化
    # ═══════════════════════════════════════════════════════════

    async def initialize_all(self) -> List[Module]:
        """批量初始化所有已注册模块，执行三阶段加载。

        使用优先级锁（UID=0, kernel 优先）。
        """
        logger = logging.getLogger(__name__)
        modules: List[Module] = []

        # ── v7: 注册表允则 — 自动注册新发现的模块 ──
        all_module_names = [
            getattr(cls, 'name', cls.__name__)
            for cls in self._module_classes
        ]
        self._auto_register_new_modules(all_module_names)

        # Phase 1: 实例化 + 装饰器扫描 + 依赖声明
        # v8: 分流 — background=True 完整初始化，False 仅扫描装饰器注册命令后丢弃
        self._check_depth()
        await self._acquire_lock(uid=0, timeout=30.0)
        try:
            for cls in self._module_classes:
                try:
                    mod = cls(self.services, self.event_bus)
                except Exception as e:
                    logger.error(
                        "模块 '%s' 实例化失败: %s。%s",
                        getattr(cls, 'name', cls.__name__), e,
                        hint["MODULE_INSTANTIATE_FAILED"],
                    )
                    continue
                # ── v7: 注册表允则检查 ──
                if not self._is_module_loadable(mod.name):
                    logger.info(
                        "模块 '%s' 未在注册表中启用，跳过加载", mod.name
                    )
                    continue
                # ── v1.2: 启动依赖检查 ──
                ok, missing, _ = self.validate_dependencies(mod)
                if not ok:
                    logger.error(
                        "⛔ 拒绝加载模块 '%s': 缺失服务 %s。"
                        "请确保所有 required_services 中的服务在模块初始化前已注册。",
                        mod.name, ", ".join(missing),
                    )
                    continue

                self._scan_all_decorators(mod)

                # ── v8: 懒加载分流 ──
                if getattr(cls, 'background', False):
                    # 预加载：完整初始化
                    modules.append(mod)
                    self._loaded_modules[mod.name] = mod
                    for dep_name in mod.required_services:
                        self.services.register_dependency(mod.name, dep_name)
                    logger.debug("模块 '%s' 预加载（background=True）", mod.name)
                else:
                    # 懒加载：装饰器已扫描。把命令注册到全局 CommandManager，
                    # callback 用闭包包装——首次调用时自动激活模块。
                    for trigger, cmd_info in mod._commands.items():
                        lazy_info = dict(cmd_info)
                        method_name = cmd_info["callback"].__name__
                        lazy_info["method"] = method_name
                        lazy_info["callback"] = self._make_lazy_callback(
                            mod.name, cls, method_name, trigger
                        )
                        self.host.command_mgr.register(**lazy_info)
                    # 仅保留类引用，消息到达时通过 _lazy_classes 恢复
                    self._lazy_classes[mod.name] = cls
                    logger.debug("模块 '%s' 懒加载（%d 条命令已注册，按需激活）",
                                 mod.name, len(mod._commands))

            # ── v1.2: 循环依赖检测（仅预加载模块） ──
            circular = self.check_circular_dependencies(modules)
            if circular:
                logger.warning(
                    "⚠ 检测到 %d 个模块涉及循环依赖: %s。"
                    "这些模块将按原始注册顺序加载，可能导致初始化顺序不符合预期。",
                    len(circular), ", ".join(circular),
                )
        finally:
            self._release_lock()
            self._release_lock()

        # Phase 2 — v6: 并行分层初始化
        # 按 required_services 依赖关系分层：同一层的模块无互相依赖，可并行 on_init。
        # 层间严格串行，每层内所有模块的超时互不影响。
        degradation = getattr(self.host, 'degradation', None)

        # 构建依赖图：{模块名 → {依赖的模块名}}
        deps = {}
        for mod in modules:
            deps[mod.name] = set()
            for srv in mod.required_services:
                for other in modules:
                    if other.name == srv:
                        deps[mod.name].add(srv)
                        break

        # 拓扑分层（Kahn 算法变体）
        layers = []
        remaining = {m.name for m in modules}
        name_to_mod = {m.name: m for m in modules}

        while remaining:
            layer = []
            for name in sorted(remaining):
                if all(d not in remaining for d in deps.get(name, set())):
                    layer.append(name_to_mod[name])
            if not layer:
                layer = [name_to_mod[n] for n in sorted(remaining)]
            for mod in layer:
                remaining.discard(mod.name)
            layers.append(layer)

        logger.info(
            "Phase 2: %d 个模块分 %d 层初始化",
            len(modules), len(layers),
        )
        for li, layer in enumerate(layers):
            logger.debug("  Layer %d: %s", li + 1,
                         ', '.join(m.name for m in layer))

        for layer in layers:
            # 层内并行 on_init
            async def _init_one(mod):
                try:
                    mod._apply_conventions()
                    if not mod.enabled:
                        self._set_module_health(mod.name, "healthy")
                        return (mod, None)
                    await asyncio.wait_for(mod.on_init(), timeout=30.0)
                    return (mod, None)
                except asyncio.TimeoutError:
                    return (mod, "on_init 超时 (30s)")
                except Exception as e:
                    return (mod, str(e))

            results = await asyncio.gather(
                *[_init_one(mod) for mod in layer]
            )

            for mod, error_msg in results:
                if error_msg:
                    logger.error(
                        "模块 '%s' 初始化失败: %s。%s",
                        mod.name, error_msg, hint["MODULE_INIT_FAILED"],
                    )
                    self._set_module_health(mod.name, "dead", error_msg)
                    await self._rollback_module(mod)
                    if degradation:
                        degradation.on_module_fail(mod.name, error_msg)
                    for dep_name in getattr(mod, 'required_services', []):
                        self.services.unregister_dependency(mod.name, dep_name)
                    continue

                if not mod.enabled:
                    continue

                # 注册工具和命令
                if mod.tools:
                    for tool_def in mod.tools:
                        self.host.tool_mgr.register_tool(tool_def)
                for tool_def in mod._tool_defs:
                    self.host.tool_mgr.register_tool(tool_def)
                for cmd_info in mod._commands.values():
                    self.host.command_mgr.register(**cmd_info)
                await mod._post_init_conventions()
                self._set_module_health(mod.name, "healthy")
        # Phase 3: on_start — 级联故障隔离：单个模块异常不传播
        started_modules = []
        await self._acquire_lock(uid=0, timeout=30.0)
        try:
            for mod in modules:
                if mod.name not in self._loaded_modules:
                    continue
                # 跳过已标记为 dead 的模块（Phase 2 失败）
                health = self._get_module_health(mod.name)
                if health == "dead":
                    logger.debug("模块 '%s' 已标记为 dead，跳过 Phase 3", mod.name)
                    continue
                try:
                    await mod.on_start()
                    started_modules.append(mod)
                    self._set_module_health(mod.name, "healthy")
                except Exception as e:
                    logger.error(
                        "模块 '%s' 启动失败: %s。%s",
                        mod.name, e, hint["MODULE_START_FAILED"],
                    )
                    self._set_module_health(mod.name, "degraded", str(e))
                    await self._rollback_module(mod)
                    # ── v5: 级联隔离 ── 单个 on_start 失败，回滚模块资源
                    # （本次任务要求在 on_start 异常时主动回滚模块）
                    if degradation:
                        degradation.on_module_fail(mod.name, f"on_start: {e}", e)
        finally:
            self._release_lock()

        logger.info("成功加载 %d 个模块", len(started_modules))
        return started_modules

    # ═══════════════════════════════════════════════════════════
    # 热插拔
    # ═══════════════════════════════════════════════════════════

    async def unload_module(self, module_name: str) -> bool:
        """热卸载指定名称的模块（带优先级锁 + 递归深度防护）。"""
        logger = logging.getLogger(__name__)
        self._check_depth()
        await self._acquire_lock(uid=100, timeout=10.0)
        try:
            mod = self._loaded_modules.pop(module_name, None)
        finally:
            self._release_lock()
        if not mod:
            # ── v8: 懒加载模块可能只在 _lazy_classes 中 ──
            lazy_cls = self._lazy_classes.pop(module_name, None)
            if lazy_cls:
                logger.info("懒加载模块 '%s' 已注销（未激活）", module_name)
                return True
            logger.warning("卸载模块失败：'%s' 未加载", module_name)
            return False

        await mod.on_stop()
        await self._rollback_module(mod)
        logger.info("模块 '%s' 卸载成功", module_name)
        return True

    def _make_lazy_callback(self, module_name: str, cls, method_name: str, trigger: str):
        """创建懒加载命令的 callback 闭包。

        首次调用时自动激活模块，然后路由到真正的命令方法。
        后续调用直接走已激活模块（callback 会被 command_mgr 自动更新）。
        """
        async def _lazy_handler(ctx):
            mod = self._loaded_modules.get(module_name)
            if mod is None:
                # 首次调用：激活模块
                mod = await self._activate_lazy_module(module_name)
                if mod is None:
                    await ctx.reply(
                        f"⚠️ 模块 '{module_name}' 激活失败，请稍后再试或联系管理员。"
                    )
                    return
                # 激活成功后，用真正的 callback 替换 command_mgr 中的闭包
                cmd_info = self.host.command_mgr.find_command(trigger)
                if cmd_info:
                    method = getattr(mod, method_name, None)
                    if method:
                        cmd_info["callback"] = method
                        cmd_info["module"] = mod
            # 执行真正的命令方法
            method = getattr(mod, method_name, None)
            if method:
                await method(ctx)
            else:
                await ctx.reply(
                    f"⚠️ 模块 '{module_name}' 方法 '{method_name}' 未找到"
                )
        return _lazy_handler

    async def _activate_lazy_module(self, module_name: str) -> Optional[Module]:
        """激活一个懒加载模块（background=False，首次 .命令 触发时调用）。

        从 _lazy_classes 中取出类 → 实例化 → on_init → on_start → 返回。
        如果模块已激活或不存在，返回 None。
        """
        logger = logging.getLogger(__name__)
        cls = self._lazy_classes.pop(module_name, None)
        if cls is None:
            # 可能已经在 loaded_modules 中（热加载激活了）
            return self._loaded_modules.get(module_name)

        logger.info("激活懒加载模块: '%s'", module_name)
        mod = await self.load_module(cls)
        if mod is not None:
            logger.info("模块 '%s' 懒加载激活成功", module_name)
        return mod

    async def load_module(self, module_cls: Type[Module]) -> Optional[Module]:
        """热加载一个新的模块类（带优先级锁 + 递归深度防护 + v7 注册表允则）。"""
        logger = logging.getLogger(__name__)
        self._check_depth()
        try:
            temp_mod = module_cls(self.services, self.event_bus)
        except Exception as e:
            logger.error(
                "模块 '%s' 实例化失败: %s。%s",
                getattr(module_cls, 'name', module_cls.__name__), e,
                hint["MODULE_INSTANTIATE_FAILED"],
            )
            return None

        # ── v7: 注册表允则检查 ──
        if not self._is_module_loadable(temp_mod.name):
            logger.info(
                "模块 '%s' 未在注册表中启用，拒绝热加载", temp_mod.name
            )
            return None

        await self._acquire_lock(uid=100, timeout=10.0)
        try:
            if temp_mod.name in self._loaded_modules:
                logger.warning("模块 '%s' 已加载，跳过", temp_mod.name)
                return None
            self._loaded_modules[temp_mod.name] = temp_mod
        finally:
            self._release_lock()

        self._scan_all_decorators(temp_mod)

        try:
            temp_mod._apply_conventions()
            if not temp_mod.enabled:
                logger.info("模块 '%s' 已禁用，跳过加载", temp_mod.name)
                await self._acquire_lock(uid=100, timeout=10.0)
                try:
                    self._loaded_modules.pop(temp_mod.name, None)
                finally:
                    self._release_lock()
                return None

            await temp_mod.on_init()

            if temp_mod.tools:
                for tool_def in temp_mod.tools:
                    self.host.tool_mgr.register_tool(tool_def)
            for tool_def in temp_mod._tool_defs:
                self.host.tool_mgr.register_tool(tool_def)
            for cmd_info in temp_mod._commands.values():
                self.host.command_mgr.register(**cmd_info)

            await temp_mod._post_init_conventions()

        except Exception as e:
            logger.error(
                "模块 '%s' 初始化失败: %s。%s",
                temp_mod.name, e, hint["MODULE_INIT_FAILED"],
            )
            await self._rollback_module(temp_mod)
            await self._acquire_lock(uid=100, timeout=10.0)
            try:
                self._loaded_modules.pop(temp_mod.name, None)
            finally:
                self._release_lock()
            return None

        try:
            await temp_mod.on_start()
        except Exception as e:
            logger.error(
                "模块 '%s' 启动失败: %s。%s",
                temp_mod.name, e, hint["MODULE_START_FAILED"],
            )
            await self._rollback_module(temp_mod)
            await self._acquire_lock(uid=100, timeout=10.0)
            try:
                self._loaded_modules.pop(temp_mod.name, None)
            finally:
                self._release_lock()
            return None

        logger.info("模块 '%s' 加载成功", temp_mod.name)
        return temp_mod

    # ═══════════════════════════════════════════════════════════
    # v1.5: 热重载 dry-run 安全保证
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _dry_run_import(module_cls: Type[Module]) -> Optional[Type[Module]]:
        """Dry-run 导入检查：验证模块类是否可以安全加载。

        不将模块注册到任何总线，仅做如下检查：
        1. import 代码本身（已通过 class 引用传入，跳过）
        2. 检查类的 required_services 格式
        3. 检查类的 config_schema / default_config 格式
        4. 尝试实例化（不调用 on_init/on_start）

        Args:
            module_cls: 模块类引用
        Returns:
            模块类本身（检查通过），或 None（检查失败）
        """
        logger = logging.getLogger(__name__)

        # 1. 检查 required_services 格式
        required = getattr(module_cls, 'required_services', None)
        if required is not None:
            if not isinstance(required, (list, tuple)):
                logger.error(
                    "❌ 模块 '%s': required_services 必须是 list/tuple，实际 %s",
                    getattr(module_cls, 'name', module_cls.__name__),
                    type(required).__name__,
                )
                return None
            for srv in required:
                if not isinstance(srv, str):
                    logger.error(
                        "❌ 模块 '%s': required_services 中的元素必须是 str，实际 %s",
                        getattr(module_cls, 'name', module_cls.__name__),
                        type(srv).__name__,
                    )
                    return None

        # 2. 检查 config_schema / default_config 格式
        config_schema = getattr(module_cls, 'config_schema', None)
        default_config = getattr(module_cls, 'default_config', None)
        if config_schema is not None:
            if not isinstance(config_schema, dict):
                logger.error(
                    "❌ 模块 '%s': config_schema 必须是 dict，实际 %s",
                    getattr(module_cls, 'name', module_cls.__name__),
                    type(config_schema).__name__,
                )
                return None
        if default_config is not None:
            if not isinstance(default_config, dict):
                logger.error(
                    "❌ 模块 '%s': default_config 必须是 dict，实际 %s",
                    getattr(module_cls, 'name', module_cls.__name__),
                    type(default_config).__name__,
                )
                return None

        # 3. 检查类是否继承自 Module
        try:
            if not issubclass(module_cls, Module):
                logger.error(
                    "❌ 模块 '%s': 必须是 Module 的子类",
                    getattr(module_cls, 'name', module_cls.__name__),
                )
                return None
        except TypeError:
            logger.error(
                "❌ 模块 '%s': 不是有效的类",
                getattr(module_cls, 'name', module_cls.__name__),
            )
            return None

        # 4. 尝试实例化（使用 __new__ 来捕获 ImportError/SyntaxError 等）
        try:
            _ = module_cls.__new__(module_cls)
        except Exception as e:
            logger.error(
                "❌ 模块 '%s': 实例化失败: %s (%s)",
                getattr(module_cls, 'name', module_cls.__name__),
                e, type(e).__name__,
            )
            return None

        logger.info(
            "✅ dry-run 通过: 模块 '%s' (required=%s)",
            getattr(module_cls, 'name', module_cls.__name__),
            required if required else '[]',
        )
        return module_cls

    def validate_module_dependencies(self, cls: Type[Module]) -> tuple:
        """验证模块类的依赖是否满足。

        检查:
        1. cls.required_services 中的服务是否已在 services 中注册
        2. 循环依赖检测（基于已加载模块和待加载类）

        Args:
            cls: 待验证的模块类
        Returns:
            (ok: bool, error_message: str)
        """
        logger = logging.getLogger(__name__)
        mod_name = getattr(cls, 'name', cls.__name__)

        # 1. 检查 required_services 服务可用性
        required = getattr(cls, 'required_services', [])
        missing: List[str] = []
        for srv_name in required:
            if not self.services.has(srv_name):
                missing.append(srv_name)

        if missing:
            msg = f"缺失服务: {', '.join(missing)}"
            logger.error(
                "❌ 模块 '%s' 依赖验证失败: %s。"
                "已知服务: %s",
                mod_name, msg,
                ", ".join(sorted(self.services.list_accessible().keys()))
                if hasattr(self.services, 'list_accessible')
                else "(无法列出)",
            )
            return False, msg

        # 2. 循环依赖检测
        all_mods: List[Module] = list(self._loaded_modules.values())
        try:
            temp_mod = cls(self.services, self.event_bus)
        except Exception as e:
            err_msg = f"实例化失败: {e}"
            logger.error("❌ 模块 '%s' 依赖验证失败: %s", mod_name, err_msg)
            return False, err_msg

        all_mods.append(temp_mod)
        circular = self.check_circular_dependencies(all_mods)

        if mod_name in circular:
            msg = f"检测到循环依赖（涉及: {', '.join(circular)}）"
            logger.warning("⚠ 模块 '%s': %s", mod_name, msg)
            return False, msg

        logger.info("✅ 模块 '%s' 依赖验证通过", mod_name)
        return True, ""

    async def reload_module(self, module_name: str) -> bool:
        """重载指定模块（dry-run 安全保证 + 回滚）。

        流程:
        1. 找到旧模块类
        2. Dry-run 导入新代码，验证依赖
        3. 卸载旧模块
        4. 加载新模块
        5. 失败时回滚到旧模块
        """
        logger = logging.getLogger(__name__)

        # Phase 1: 找到模块类
        old_mod = self._loaded_modules.get(module_name)
        if not old_mod:
            logger.warning("重载失败: 模块 '%s' 未加载", module_name)
            return False
        old_cls = type(old_mod)

        # Phase 2: dry-run — 预检新代码
        new_cls = self._dry_run_import(old_cls)
        if new_cls is None:
            logger.error("⛔ 重载预检失败: 模块 '%s' 新代码校验未通过", module_name)
            return False

        # 验证依赖
        ok, err = self.validate_module_dependencies(new_cls)
        if not ok:
            logger.error(
                "⛔ 重载预检失败: 模块 '%s' 依赖不满足: %s",
                module_name, err,
            )
            return False

        # Phase 3: 卸载旧模块
        logger.info("卸载旧模块 '%s'...", module_name)
        unloaded = await self.unload_module(module_name)
        if not unloaded:
            logger.error("⛔ 重载失败: 无法卸载模块 '%s'", module_name)
            return False

        # Phase 4: 加载新模块
        try:
            logger.info("加载新模块 '%s'...", module_name)
            result = await self.load_module(new_cls)
            if result is not None:
                logger.info("✅ 模块 '%s' 重载成功", module_name)
                return True
            else:
                raise RuntimeError("load_module 返回 None")
        except Exception as e:
            # Phase 5: 回滚 — 重新加载旧模块
            logger.error(
                "⛔ 新模块加载失败: %s，回滚到旧版本", e
            )
            try:
                await self.load_module(old_cls)
                logger.info("🔄 模块 '%s' 已回滚到旧版本", module_name)
            except Exception as rollback_err:
                logger.critical(
                    "💀 模块 '%s' 回滚也失败了: %s。模块已丢失！",
                    module_name, rollback_err,
                )
            return False

    # ═══════════════════════════════════════════════════════════
    # v6: FREEZE / THAW — 模块冻结与解冻
    # ═══════════════════════════════════════════════════════════

    async def freeze_module(self, module_name: str) -> bool:
        """冻结指定模块：保留实例但取消事件/命令注册。

        kernel 组 (uid=0) 模块不可冻结。

        Returns:
            True 表示冻结成功，False 表示失败（模块不存在/不可冻结/已冻结）。
        """
        logger = logging.getLogger(__name__)
        mod = self._loaded_modules.get(module_name)
        if mod is None:
            logger.warning("冻结失败: 模块 '%s' 未加载", module_name)
            return False

        # kernel 组不可冻结
        if getattr(mod, 'uid', 400) == 0:
            logger.warning("冻结失败: 模块 '%s' 是 kernel 组，不可冻结", module_name)
            return False

        # 已冻结 → 幂等返回 True
        if getattr(mod, 'frozen', False):
            logger.info("模块 '%s' 已冻结，跳过", module_name)
            return True

        try:
            # 调用模块自身 on_freeze 钩子
            await mod.on_freeze()

            # 从 EventBus 取消该模块的所有事件订阅
            if self.event_bus and hasattr(mod, '_event_handlers'):
                for event_type, handler, _priority in mod._event_handlers:
                    self.event_bus.unsubscribe(event_type, handler)
                logger.debug(
                    "模块 '%s': 已取消 %d 个事件订阅",
                    module_name, len(mod._event_handlers),
                )

            # 从 CommandManager 取消该模块的所有命令注册
            if hasattr(self.host, 'command_mgr'):
                for trigger in list(getattr(mod, '_commands', {}).keys()):
                    self.host.command_mgr.unregister(trigger)
                logger.debug(
                    "模块 '%s': 已取消 %d 个命令注册",
                    module_name, len(getattr(mod, '_commands', {})),
                )

            # 标记为已冻结
            mod.frozen = True

            # 通知 HealthScorer（不计入降分，标记为 SUSPENDED）
            health_scorer = getattr(self.host, 'health_scorer', None)
            if health_scorer and hasattr(health_scorer, 'on_module_frozen'):
                health_scorer.on_module_frozen(module_name)

            logger.info("模块 '%s' 已冻结", module_name)
            return True

        except Exception as e:
            logger.error("冻结模块 '%s' 失败: %s", module_name, e)
            return False

    async def thaw_module(self, module_name: str) -> bool:
        """解冻指定模块：重新注册事件/命令。

        Returns:
            True 表示解冻成功，False 表示失败（模块不存在/未冻结）。
        """
        logger = logging.getLogger(__name__)
        mod = self._loaded_modules.get(module_name)
        if mod is None:
            logger.warning("解冻失败: 模块 '%s' 未加载", module_name)
            return False

        # 未冻结 → 幂等返回 True
        if not getattr(mod, 'frozen', False):
            logger.info("模块 '%s' 未冻结，跳过", module_name)
            return True

        try:
            # 重新注册事件订阅
            if self.event_bus and hasattr(mod, '_event_handlers'):
                for event_type, handler, priority in mod._event_handlers:
                    if event_type == "GroupMessageEvent":
                        # 重新包装群过滤器
                        original = handler
                        module_name_inner = mod.name
                        group_filter_inner = getattr(mod, 'group_filter', None)

                        async def _rebuilt_handler(event,
                                                   _orig=original,
                                                   _mn=module_name_inner,
                                                   _gf=group_filter_inner):
                            if _gf is None:
                                await _orig(event)
                                return
                            if _gf.is_module_enabled(event.group_id, _mn):
                                await _orig(event)

                        wrapped = _rebuilt_handler
                        self.event_bus.subscribe(event_type, wrapped, priority)
                    else:
                        self.event_bus.subscribe(event_type, handler, priority)
                logger.debug(
                    "模块 '%s': 已重新注册 %d 个事件订阅",
                    module_name, len(mod._event_handlers),
                )

            # 重新注册命令
            if hasattr(self.host, 'command_mgr'):
                for cmd_info in getattr(mod, '_commands', {}).values():
                    self.host.command_mgr.register(**cmd_info)
                logger.debug(
                    "模块 '%s': 已重新注册 %d 个命令",
                    module_name, len(getattr(mod, '_commands', {})),
                )

            # 调用模块自身 on_thaw 钩子
            await mod.on_thaw()

            # 标记为已解冻
            mod.frozen = False

            # 通知 HealthScorer
            health_scorer = getattr(self.host, 'health_scorer', None)
            if health_scorer and hasattr(health_scorer, 'on_module_thawed'):
                health_scorer.on_module_thawed(module_name)

            logger.info("模块 '%s' 已解冻", module_name)
            return True

        except Exception as e:
            logger.error("解冻模块 '%s' 失败: %s", module_name, e)
            return False

    def list_frozen(self) -> list:
        """返回已冻结的模块名称列表。"""
        return [
            name for name, mod in self._loaded_modules.items()
            if getattr(mod, 'frozen', False)
        ]

    def is_frozen(self, module_name: str) -> bool:
        """检查指定模块是否已冻结。"""
        mod = self._loaded_modules.get(module_name)
        if mod is None:
            return False
        return getattr(mod, 'frozen', False)

    # ═══════════════════════════════════════════════════════════
    # 回滚
    # ═══════════════════════════════════════════════════════════

    async def _rollback_module(self, mod: Module):
        """回滚模块: 清理事件订阅、命令、工具和定时任务。"""
        for event_type, handler, _ in mod._event_handlers:
            self.event_bus.unsubscribe(event_type, handler)
        mod._event_handlers.clear()
        for trigger in list(mod._commands.keys()):
            self.host.command_mgr.unregister(trigger)
        mod._commands.clear()

        all_tools = list(mod.tools) + list(mod._tool_defs)
        for tool_def in all_tools:
            tool_name = tool_def.get("name")
            if tool_name:
                self.host.tool_mgr.unregister_tool(tool_name)
        mod.tools.clear()
        mod._tool_defs.clear()

        await getattr(mod, '_cleanup_conventions', lambda: None)()

    # ═══════════════════════════════════════════════════════════
    # 装饰器扫描
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _scan_all_decorators(mod: Module):
        """扫描 @command / @listen / @tool / @schedule 装饰器。

        沙箱: 对装饰器声明的元数据做二次校验，拒绝非 root 模块越权声明。
        """
        logger = logging.getLogger(__name__)
        for _, method in inspect.getmembers(mod, predicate=lambda m: inspect.ismethod(m) or inspect.isfunction(m)):
            if hasattr(method, '_command_info'):
                info = method._command_info
                min_uid = info.get('min_uid', 400)
                # ── 二次校验: 非 root 模块命令 min_uid 不能低于模块自身 uid ──
                if mod.uid > 0 and min_uid < mod.uid:
                    logger.warning(
                        "模块 '%s' (uid=%d) 装饰器声明命令 '%s' (min_uid=%d < %d)，已拒绝",
                        mod.name, mod.uid, info.get('trigger', '?'), min_uid, mod.uid,
                    )
                    continue
                mod.register_command(
                    info['trigger'], method,
                    cmd_type=info.get('type', 'group'),
                    description=info.get('description', ''),
                    op_only=info.get('op_only', False),
                    required_role=info.get('required_role', ''),
                    argument_hint=info.get('argument_hint', ''),
                    cooldown=info.get('cooldown'),
                    min_uid=min_uid,
                )
            if hasattr(method, '_event_info'):
                info = method._event_info
                event_type = info.get('event_type', '')
                # ── 二次校验: 非 root 模块事件白名单 ──
                from qqlinker_framework.core.module import _ALLOWED_EVENTS_FOR_MODULE
                if mod.uid > 0 and event_type not in _ALLOWED_EVENTS_FOR_MODULE:
                    logger.warning(
                        "模块 '%s' (uid=%d) 装饰器声明订阅受限事件 '%s'，已拒绝",
                        mod.name, mod.uid, event_type,
                    )
                    continue
                mod.listen(info['event_type'], method, info.get('priority', 0))
            if hasattr(method, '_tool_info'):
                tool_info = method._tool_info
                tool_uid = tool_info.get('uid', 300)
                # ── 二次校验: 非 root 模块工具 uid 下限 ──
                if mod.uid > 0 and tool_uid < mod.uid:
                    logger.warning(
                        "模块 '%s' (uid=%d) 装饰器声明工具 '%s' (uid=%d < %d)，已拒绝",
                        mod.name, mod.uid,
                        tool_info.get('name', '<unnamed>'), tool_uid, mod.uid,
                    )
                    continue
                mod.tools.append(method._tool_info)
            if hasattr(method, '_schedule_info'):
                from qqlinker_framework.core.module import ScheduledTask
                info = method._schedule_info
                mod.scheduled.append(ScheduledTask(
                    name=info['name'],
                    handler=method,
                    interval=info['interval'],
                    cron=info['cron'],
                    run_on_start=info['run_on_start'],
                    enabled=info['enabled'],
                ))
                mod.logger.debug("扫描到定时任务: %s", info['name'])

    def get_loaded_modules(self) -> List[str]:
        """返回所有已加载模块的名称列表。"""
        return list(self._loaded_modules.keys())

    # ═══════════════════════════════════════════════════════════
    # v8: 统一扫描 / 发现入口
    # ═══════════════════════════════════════════════════════════

    @property
    def registry(self):
        """模块注册表（允则权威来源）。"""
        return self._registry

    @registry.setter
    def registry(self, value):
        """设置模块注册表引用。"""
        self._registry = value

    # ── 模块扫描 ──

    def discover_from_package(self, package_name: str = "qqlinker_framework.modules"):
        """从 Python 包自动发现并注册模块。"""
        from qqlinker_framework.core.drivers.autodiscover import (
            discover_modules as _discover_from_pkg,
            sort_by_dependencies,
        )
        logger = logging.getLogger(__name__)
        classes = _discover_from_pkg(package_name)
        if not classes:
            logger.warning("未发现任何模块")
            return
        for cls in sort_by_dependencies(classes):
            self.register_module(cls)
        logger.info(
            "从 '%s' 自动发现并注册了 %d 个模块", package_name, len(classes))

    def discover_from_files(self, data_path: str):
        """从外部目录扫描并注册模块。"""
        from qqlinker_framework.core.drivers.autodiscover import (
            discover_from_files,
            sort_by_dependencies,
        )
        logger = logging.getLogger(__name__)
        classes = discover_from_files(data_path)
        if not classes:
            logger.debug("未发现外部模块")
            return
        for cls in sort_by_dependencies(classes):
            self.register_module(cls)
        logger.info(
            "从外部目录发现并注册了 %d 个模块", len(classes))

    # ── 工具扫描 ──

    def scan_tool_directory(self, directory_path: str, tool_type: Optional[str] = None) -> int:
        """扫描指定目录下所有 JSON 文件，注册工具。

        Args:
            directory_path: 要扫描的目录路径。
            tool_type: 过滤工具类型（'ai' / 'admin'），None 加载全部。
        Returns:
            成功注册的工具数量。
        """
        if self._tool_mgr is None:
            logging.getLogger(__name__).warning("ToolManager 未注入，跳过工具扫描")
            return 0
        return self._tool_mgr.scan_directory(directory_path, tool_type)

    def register_tool(self, tool_def: dict) -> bool:
        """注册一个工具（通过 ToolManager）。"""
        if self._tool_mgr is None:
            logging.getLogger(__name__).warning("ToolManager 未注入，无法注册工具")
            return False
        return self._tool_mgr.register_tool(tool_def)

    def get_ai_tools(self) -> list:
        """获取所有 AI 类型工具。"""
        if self._tool_mgr is None:
            return []
        return self._tool_mgr.get_ai_tools()

    def get_admin_tools(self) -> list:
        """获取所有管理类型工具。"""
        if self._tool_mgr is None:
            return []
        return self._tool_mgr.get_admin_tools()

    def init_tool_scanner(self, data_dir: str) -> None:
        """一次性扫描 AI + 管理工具目录。

        扫描顺序:
          1. 数据/工具/AI工具/ — AI function calling 工具
          2. 数据/工具/管理工具/ — 管理编排工具
        """
        logger = logging.getLogger(__name__)
        if self._tool_mgr is None:
            logger.warning("ToolManager 未注入，跳过工具扫描")
            return

        ai_dir = _os.path.join(data_dir, "工具", "AI工具")
        admin_dir = _os.path.join(data_dir, "工具", "管理工具")

        ai_count = 0
        admin_count = 0
        if _os.path.isdir(ai_dir):
            ai_count = self._tool_mgr.scan_directory(ai_dir, tool_type="ai")
        if _os.path.isdir(admin_dir):
            admin_count = self._tool_mgr.scan_directory(admin_dir, tool_type="admin")

        logger.info("工具扫描完成: AI=%d, 管理=%d", ai_count, admin_count)

    # ── 工作流扫描 ──

    def scan_workflow_directory(self, path: str) -> int:
        """扫描指定目录下的 JSON 工作流定义。"""
        if self._admin_tool_mgr is None:
            logging.getLogger(__name__).warning("AdminToolManager 未注入，跳过工作流扫描")
            return 0
        # 设置扫描目录并触发扫描
        self._admin_tool_mgr._json_scan_dir = path
        _os.makedirs(path, exist_ok=True)
        return self._admin_tool_mgr._scan_json_workflows()

    def register_workflow(self, name: str, steps: list, **kwargs) -> any:
        """注册一个工作流。"""
        if self._admin_tool_mgr is None:
            logging.getLogger(__name__).warning("AdminToolManager 未注入，无法注册工作流")
            return None
        return self._admin_tool_mgr.register_workflow(name=name, steps=steps, **kwargs)

    def get_workflows(self, caller_uid: int = 400) -> list:
        """获取所有已注册的工作流。"""
        if self._admin_tool_mgr is None:
            return []
        return self._admin_tool_mgr.list_workflows(caller_uid=caller_uid)

    def init_workflow_scanner(self, data_dir: str) -> None:
        """一次性扫描工作流目录（数据/管理工具/）。"""
        if self._admin_tool_mgr is None:
            logging.getLogger(__name__).warning("AdminToolManager 未注入，跳过工作流扫描")
            return
        wf_dir = _os.path.join(data_dir, "管理工具")
        _os.makedirs(wf_dir, exist_ok=True)
        count = self._admin_tool_mgr._scan_json_workflows()
        logging.getLogger(__name__).info("工作流扫描完成: %d 个", count)

    # ── 配置注册表 ──

    def register_config_section(self, name: str, defaults: dict):
        """注册一个配置节（通过 host.config_mgr）。"""
        self.host.config_mgr.register_section(name, defaults, caller_uid=0)

    # ── 包管理 ──

    def install_package(self, name: str, version: str = None) -> bool:
        """安装一个 Python 包。"""
        if self._package_mgr is None:
            logging.getLogger(__name__).warning("PackageManager 未注入，无法安装包")
            return False
        self._package_mgr.register_requirement(name)
        return self._package_mgr.install_packages([name])

    def list_packages(self) -> list:
        """列出所有注册的依赖包。"""
        if self._package_mgr is None:
            return []
        return list(self._package_mgr._requirements.keys())

    # ═══════════════════════════════════════════════════════════
    # v5: 模块健康状态追踪（级联故障隔离）
    # ═══════════════════════════════════════════════════════════

    def _set_module_health(self, module_name: str, status: str, reason: str = "") -> None:
        """更新模块健康状态（写入 host._module_health_status）。

        Args:
            module_name: 模块名
            status: "healthy" / "degraded" / "dead"
            reason: 降级/死亡原因（可选）
        """
        if hasattr(self.host, '_module_health_status'):
            self.host._module_health_status[module_name] = status
        logger = logging.getLogger(__name__)
        level = logging.INFO if status == "healthy" else logging.WARNING
        msg = f"模块健康状态: {module_name} → {status}"
        if reason and status != "healthy":
            msg += f" ({reason})"
        logger.log(level, msg)

    def _get_module_health(self, module_name: str) -> str:
        """获取模块健康状态。"""
        if hasattr(self.host, '_module_health_status'):
            return self.host._module_health_status.get(module_name, "unknown")
        return "unknown"

    def get_module_health_summary(self) -> dict:
        """返回所有模块的健康状态摘要。"""
        if hasattr(self.host, '_module_health_status'):
            return dict(self.host._module_health_status)
        return {}
