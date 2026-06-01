# pylint: disable=protected-access
"""模块管理器 – 注册、约定执行、依赖排序、生命周期调度及热插拔"""
import asyncio
import inspect
import logging
from typing import Type, List, Optional
from ..core.module import Module
from ..core.error_hints import hint
from ..core.containment import safe_handler


class ModuleManager:
    """负责模块的注册、约定执行、依赖排序、生命周期调度及热插拔。"""

    def __init__(self, host):
        self.host = host
        self.services = host.services
        self.event_bus = host.event_bus
        self._module_classes: List[Type[Module]] = []
        self._loaded_modules: dict[str, Module] = {}
        self._lock = asyncio.Lock()

    def register(self, module_cls: Type[Module]):
        """注册模块类，若已存在则跳过。"""
        if module_cls not in self._module_classes:
            self._module_classes.append(module_cls)

    # ═══════════════════════════════════════════════════════════
    # 批量初始化
    # ═══════════════════════════════════════════════════════════

    async def initialize_all(self) -> List[Module]:
        """批量初始化所有已注册模块，执行三阶段加载。"""
        logger = logging.getLogger(__name__)
        modules: List[Module] = []

        # Phase 1: 实例化 + 装饰器扫描
        async with self._lock:
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
                self._scan_all_decorators(mod)
                modules.append(mod)
                self._loaded_modules[mod.name] = mod

        # Phase 2: on_init（约定已执行）
        for mod in modules:
            try:
                mod._apply_conventions()
                if not mod.enabled:
                    logger.info("模块 '%s' 已禁用，跳过初始化", mod.name)
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

            except Exception as e:
                logger.error(
                    "模块 '%s' 初始化失败: %s。%s",
                    mod.name, e, hint["MODULE_INIT_FAILED"],
                )
                await self._rollback_module(mod)
                continue

        # Phase 3: on_start
        started_modules = []
        async with self._lock:
            for mod in modules:
                if mod.name not in self._loaded_modules:
                    continue
                try:
                    await mod.on_start()
                    started_modules.append(mod)
                except Exception as e:
                    logger.error(
                        "模块 '%s' 启动失败: %s。%s",
                        mod.name, e, hint["MODULE_START_FAILED"],
                    )
                    self._loaded_modules.pop(mod.name, None)

        logger.info("成功加载 %d 个模块", len(started_modules))
        return started_modules

    # ═══════════════════════════════════════════════════════════
    # 热插拔
    # ═══════════════════════════════════════════════════════════

    async def unload_module(self, module_name: str) -> bool:
        """热卸载指定名称的模块。"""
        logger = logging.getLogger(__name__)
        async with self._lock:
            mod = self._loaded_modules.pop(module_name, None)
        if not mod:
            logger.warning("卸载模块失败：'%s' 未加载", module_name)
            return False

        await mod.on_stop()
        await self._rollback_module(mod)
        logger.info("模块 '%s' 卸载成功", module_name)
        return True

    async def load_module(self, module_cls: Type[Module]) -> Optional[Module]:
        """热加载一个新的模块类。"""
        logger = logging.getLogger(__name__)
        try:
            temp_mod = module_cls(self.services, self.event_bus)
        except Exception as e:
            logger.error(
                "模块 '%s' 实例化失败: %s。%s",
                getattr(module_cls, 'name', module_cls.__name__), e,
                hint["MODULE_INSTANTIATE_FAILED"],
            )
            return None

        async with self._lock:
            if temp_mod.name in self._loaded_modules:
                logger.warning("模块 '%s' 已加载，跳过", temp_mod.name)
                return None
            self._loaded_modules[temp_mod.name] = temp_mod

        self._scan_all_decorators(temp_mod)

        try:
            temp_mod._apply_conventions()
            if not temp_mod.enabled:
                logger.info("模块 '%s' 已禁用，跳过加载", temp_mod.name)
                async with self._lock:
                    self._loaded_modules.pop(temp_mod.name, None)
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
            async with self._lock:
                self._loaded_modules.pop(temp_mod.name, None)
            return None

        try:
            await temp_mod.on_start()
        except Exception as e:
            logger.error(
                "模块 '%s' 启动失败: %s。%s",
                temp_mod.name, e, hint["MODULE_START_FAILED"],
            )
            await self._rollback_module(temp_mod)
            async with self._lock:
                self._loaded_modules.pop(temp_mod.name, None)
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
        async with self._lock:
            self._loaded_modules.pop(mod.name, None)

    # ═══════════════════════════════════════════════════════════
    # 装饰器扫描
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _scan_all_decorators(mod: Module):
        """扫描 @command / @listen / @tool / @schedule 装饰器。"""
        for _, method in inspect.getmembers(mod, predicate=inspect.ismethod):
            if hasattr(method, '_command_info'):
                info = method._command_info
                mod.register_command(
                    info['trigger'], method,
                    cmd_type=info.get('type', 'group'),
                    description=info.get('description', ''),
                    op_only=info.get('op_only', False),
                    required_role=info.get('required_role', ''),
                    argument_hint=info.get('argument_hint', ''),
                    cooldown=info.get('cooldown'),
                )
            if hasattr(method, '_event_info'):
                info = method._event_info
                mod.listen(info['event_type'], method, info.get('priority', 0))
            if hasattr(method, '_tool_info'):
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
