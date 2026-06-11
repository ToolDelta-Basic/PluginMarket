# pylint: disable=protected-access
"""模块管理器 – 注册、约定执行、依赖排序、生命周期调度及热插拔

v1.2 — 新增启动依赖检查（服务存在性 + 循环依赖检测）
v7.0 — 注册表允则机制: 模块加载唯一权威来源 = 模块注册表 JSON
       只有注册表中明确标记"启用"的模块才运行，
       新发现的模块默认写入注册表并自动启用
"""
import asyncio
import inspect
import logging
import contextvars
from typing import Type, List, Optional, Set, Dict
from ..core.module import Module
from ..core.kernel.error_hints import hint
from ..core.kernel.prioritized_lock import PrioritizedLock
from ..core.drivers.registry import ModuleRegistry

# ── 递归深度防护 ──────────────────────────────────────────
_module_mgr_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    'module_mgr_recursion_depth', default=0
)
MAX_MODULE_MGR_DEPTH = 10


class ModuleManager:
    """负责模块的注册、约定执行、依赖排序、生命周期调度及热插拔。

    v1.1: 使用 PrioritizedLock 替代 asyncio.Lock，支持:
      - 优先级供给（UID 越小越优先获得锁）
      - 递归深度防护（深度 > 10 时拒绝操作）
      - 获取超时保护（默认 5s）
    """

    def __init__(self, host, registry: ModuleRegistry = None):
        self.host = host
        self.services = host.services
        self.event_bus = host.event_bus
        self._module_classes: List[Type[Module]] = []
        self._loaded_modules: dict[str, Module] = {}
        self._lock = PrioritizedLock(name="module_mgr")
        # 读路径上的轻量级保护
        self._read_lock = asyncio.Lock()
        # v7: 模块注册表 — 允则逻辑的唯一权威来源
        self.registry = registry

    def _check_depth(self) -> None:
        """递归深度检查，超限抛出 RecursionError。"""
        depth = _module_mgr_depth.get()
        if depth >= MAX_MODULE_MGR_DEPTH:
            raise RecursionError(
                f"ModuleManager 递归深度超限 ({depth} >= {MAX_MODULE_MGR_DEPTH})。"
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

    def register(self, module_cls: Type[Module]):
        """注册模块类，若已存在则跳过。"""
        if module_cls not in self._module_classes:
            self._module_classes.append(module_cls)

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

    def check_circular_dependencies(self, mods: List[Module]) -> List[str]:
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
                modules.append(mod)
                self._loaded_modules[mod.name] = mod
                # 注册模块间依赖关系（用于拓扑排序）
                for dep_name in mod.required_services:
                    self.services.register_dependency(mod.name, dep_name)

            # ── v1.2: 循环依赖检测 ──
            circular = self.check_circular_dependencies(modules)
            if circular:
                logger.warning(
                    "⚠ 检测到 %d 个模块涉及循环依赖: %s。"
                    "这些模块将按原始注册顺序加载，可能导致初始化顺序不符合预期。",
                    len(circular), ", ".join(circular),
                )
        finally:
            self._release_lock()

        # Phase 2: 按依赖拓扑排序后执行 on_init
        # 有依赖的模块会在其所依赖的模块之后初始化
        sorted_names = self.services.resolve_order()
        # 将模块按 resolve_order 重排（保留原 modules 中不在排序结果中的模块）
        name_to_mod = {m.name: m for m in modules}
        ordered_modules: List[Module] = []
        seen: set = set()
        for name in sorted_names:
            if name in name_to_mod and name not in seen:
                ordered_modules.append(name_to_mod[name])
                seen.add(name)
        # 追加任何不在依赖图中的模块（按原始注册顺序）
        for mod in modules:
            if mod.name not in seen:
                ordered_modules.append(mod)
                seen.add(mod.name)
        modules = ordered_modules

        # ── v5: 模块健康状态初始化 ──
        degradation = getattr(self.host, 'degradation', None)

        for mod in modules:
            # ── v5: 级联故障隔离 ── 单个模块异常仅影响自身
            try:
                mod._apply_conventions()
                if not mod.enabled:
                    logger.info("模块 '%s' 已禁用，跳过初始化", mod.name)
                    self._set_module_health(mod.name, "healthy")
                    continue
                await mod.on_init()

                if mod.tools:
                    for tool_def in mod.tools:
                        self.host.tool_mgr.register_tool(tool_def)
                for tool_def in mod._tool_defs:
                    self.host.tool_mgr.register_tool(tool_def)
                for cmd_info in mod._commands.values():
                    self.host.command_mgr.register(**cmd_info)
                await mod._post_init_conventions()
                self._set_module_health(mod.name, "healthy")

            except Exception as e:
                logger.error(
                    "模块 '%s' 初始化失败: %s。%s",
                    mod.name, e, hint["MODULE_INIT_FAILED"],
                )
                self._set_module_health(mod.name, "dead", str(e))
                await self._rollback_module(mod)
                # ── v5: 级联隔离 ── 通知降级引擎，不影响其他模块
                if degradation:
                    degradation.on_module_fail(mod.name, str(e), e)
                # 移除已注册的模块间依赖
                for dep_name in getattr(mod, 'required_services', []):
                    self.services.unregister_dependency(mod.name, dep_name)
                continue

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
            logger.warning("卸载模块失败：'%s' 未加载", module_name)
            return False

        await mod.on_stop()
        await self._rollback_module(mod)
        logger.info("模块 '%s' 卸载成功", module_name)
        return True

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

    async def reload_module(self, module_name: str) -> bool:
        """重载指定模块（先卸载再加载）。"""
        mod = self._loaded_modules.get(module_name)
        if not mod:
            return False
        module_cls = type(mod)
        if await self.unload_module(module_name):
            return await self.load_module(module_cls) is not None
        return False

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
                from ..core.module import _ALLOWED_EVENTS_FOR_MODULE
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
                from ..core.module import ScheduledTask
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
