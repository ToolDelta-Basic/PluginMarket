# pylint: disable=protected-access
"""模块管理器 – 负责模块的注册、依赖排序、生命周期调度及热插拔"""
import asyncio
import inspect
import logging
from typing import Type, List, Optional
from ..core.module import Module


class ModuleManager:
    """负责模块的注册、依赖排序、生命周期调度及热插拔。"""

    def __init__(self, host):
        """初始化模块管理器。"""
        self.host = host
        self.services = host.services
        self.event_bus = host.event_bus
        self._module_classes: List[Type[Module]] = []
        self._loaded_modules: dict[str, Module] = {}
        self._lock = asyncio.Lock()

    def register(self, module_cls: Type[Module]):
        """注册模块类（去重）。"""
        if module_cls not in self._module_classes:
            self._module_classes.append(module_cls)

    async def initialize_all(self) -> List[Module]:
        """实例化、扫描装饰器、依次执行 on_init 和 on_start。"""
        logger = logging.getLogger(__name__)
        modules: List[Module] = []
        async with self._lock:
            for cls in self._module_classes:
                try:
                    mod = cls(self.services, self.event_bus)
                except Exception as e:
                    logger.error(
                        "模块 '%s' 实例化失败: %s，已跳过",
                        getattr(cls, 'name', cls.__name__),
                        e,
                    )
                    continue
                self._scan_decorators(mod)
                modules.append(mod)
                self._loaded_modules[mod.name] = mod

        for mod in modules:
            try:
                await mod.on_init()
                for tool_def in mod._tools:
                    self.host.tool_mgr.register_tool(tool_def)
                for cmd_info in mod._commands.values():
                    self.host.command_mgr.register(**cmd_info)
            except Exception as e:
                logger.error(
                    "模块 '%s' 初始化失败: %s，已跳过启动", mod.name, e
                )
                # 回滚：取消已订阅的事件
                for event_type, handler, _ in mod._event_handlers:
                    self.event_bus.unsubscribe(event_type, handler)
                mod._event_handlers.clear()
                async with self._lock:
                    self._loaded_modules.pop(mod.name, None)
                for trigger in mod._commands:
                    self.host.command_mgr.unregister(trigger)
                for tool_def in mod._tools:
                    tool_name = tool_def.get("name")
                    if tool_name:
                        self.host.tool_mgr.unregister_tool(tool_name)
                continue

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
                        "模块 '%s' 启动失败: %s，已跳过", mod.name, e
                    )
                    self._loaded_modules.pop(mod.name, None)

        logger.info("成功加载 %d 个模块", len(started_modules))
        return started_modules

    async def unload_module(self, module_name: str) -> bool:
        """卸载模块，清理事件订阅、命令和工具。"""
        logger = logging.getLogger(__name__)
        async with self._lock:
            mod = self._loaded_modules.pop(module_name, None)
        if not mod:
            logger.warning("卸载模块失败：模块 '%s' 未加载", module_name)
            return False
        await mod.on_stop()
        for event_type, handler, _ in mod._event_handlers:
            self.event_bus.unsubscribe(event_type, handler)
        mod._event_handlers.clear()
        for trigger in list(mod._commands.keys()):
            self.host.command_mgr.unregister(trigger)
        mod._commands.clear()
        for tool_def in mod._tools:
            tool_name = tool_def.get("name")
            if tool_name:
                self.host.tool_mgr.unregister_tool(tool_name)
        mod._tools.clear()
        logger.info("模块 '%s' 卸载成功", module_name)
        return True

    async def load_module(
        self, module_cls: Type[Module]
    ) -> Optional[Module]:
        """动态加载一个新模块实例。"""
        logger = logging.getLogger(__name__)
        try:
            temp_mod = module_cls(self.services, self.event_bus)
        except Exception as e:
            logger.error(
                "模块 '%s' 实例化失败: %s",
                getattr(module_cls, 'name', module_cls.__name__),
                e,
            )
            return None
        async with self._lock:
            if temp_mod.name in self._loaded_modules:
                logger.warning(
                    "模块 '%s' 已加载，跳过重复加载", temp_mod.name
                )
                return None
            self._loaded_modules[temp_mod.name] = temp_mod
        self._scan_decorators(temp_mod)
        try:
            await temp_mod.on_init()
            for tool_def in temp_mod._tools:
                self.host.tool_mgr.register_tool(tool_def)
            for cmd_info in temp_mod._commands.values():
                self.host.command_mgr.register(**cmd_info)
        except Exception as e:
            logger.error("模块 '%s' 初始化失败: %s", temp_mod.name, e)
            async with self._lock:
                self._loaded_modules.pop(temp_mod.name, None)
            return None
        try:
            await temp_mod.on_start()
        except Exception as e:
            logger.error("模块 '%s' 启动失败: %s", temp_mod.name, e)
            async with self._lock:
                self._loaded_modules.pop(temp_mod.name, None)
            return None
        logger.info("模块 '%s' 加载成功", temp_mod.name)
        return temp_mod

    async def reload_module(self, module_name: str) -> bool:
        """重载模块（先卸载再加载）。"""
        mod = self._loaded_modules.get(module_name)
        if not mod:
            return False
        module_cls = type(mod)
        success = await self.unload_module(module_name)
        if not success:
            return False
        new_mod = await self.load_module(module_cls)
        return new_mod is not None

    @staticmethod
    def _scan_decorators(mod: Module):
        """扫描模块方法上的装饰器信息并注册命令/事件。"""
        for _, method in inspect.getmembers(
            mod, predicate=inspect.ismethod
        ):
            if hasattr(method, '_command_info'):
                info = method._command_info
                mod.register_command(
                    info['trigger'],
                    method,
                    cmd_type=info.get('type', 'group'),
                    description=info.get('description', ''),
                    op_only=info.get('op_only', False),
                    argument_hint=info.get('argument_hint', ''),
                )
            if hasattr(method, '_event_info'):
                info = method._event_info
                mod.listen(
                    info['event_type'], method, info.get('priority', 0)
                )

    def get_loaded_modules(self) -> List[str]:
        """获取已加载的模块名称列表。"""
        return list(self._loaded_modules.keys())
