"""模块基类"""
from abc import ABC, abstractmethod
from typing import Callable
from .services import ServiceContainer
from .bus import EventBus

class Module(ABC):
    name: str = ""
    version: tuple = (0, 0, 1)
    dependencies: list[str] = []
    required_services: list[str] = []

    def __init__(self, services: ServiceContainer, event_bus: EventBus):
        self.services = services
        self.event_bus = event_bus
        for srv_name in self.required_services:
            if not services.has(srv_name):
                raise RuntimeError(f"模块 {self.name} 需要服务 '{srv_name}'，但未注册")
            setattr(self, srv_name, services.get(srv_name))
        self._commands: dict[str, dict] = {}
        self._event_handlers: list[tuple] = []
        self._tools: list[dict] = []

    @abstractmethod
    async def on_init(self): ...

    async def on_start(self): pass
    async def on_stop(self): pass

    def register_command(self, trigger: str, callback: Callable, *,
                         cmd_type: str = "group", description: str = "",
                         op_only: bool = False, argument_hint: str = ""):
        self._commands[trigger] = {
            "trigger": trigger,
            "cmd_type": cmd_type,
            "callback": callback,
            "description": description,
            "op_only": op_only,
            "argument_hint": argument_hint
        }

    def listen(self, event_type: str, handler: Callable, priority: int = 0):
        self.event_bus.subscribe(event_type, handler, priority)
        self._event_handlers.append((event_type, handler, priority))

    def register_tool(self, tool_definition: dict):
        self._tools.append(tool_definition)