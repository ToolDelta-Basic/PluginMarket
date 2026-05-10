"""模块基类"""
from abc import ABC, abstractmethod
from typing import Callable
from .services import ServiceContainer
from .bus import EventBus

class Module(ABC):
    """所有业务模块的抽象基类。

    Attributes:
        name: 模块名称，必须唯一。
        version: 版本元组。
        dependencies: 依赖的其他模块名列表。
        required_services: 所需的服务名称列表，会自动注入为属性。
    """
    name: str = ""
    version: tuple = (0, 0, 1)
    dependencies: list[str] = []
    required_services: list[str] = []

    def __init__(self, services: ServiceContainer, event_bus: EventBus):
        """初始化模块并注入所需服务。

        Args:
            services: 服务容器。
            event_bus: 事件总线。

        Raises:
            RuntimeError: 如果缺少必需的服务。
        """
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
    async def on_init(self):
        """模块初始化逻辑（抽象方法）。"""
        ...

    async def on_start(self):
        """模块启动时的额外逻辑（可选）。"""
        pass

    async def on_stop(self):
        """模块停止时的清理逻辑（可选）。"""
        pass

    def register_command(self, trigger: str, callback: Callable, *,
                         cmd_type: str = "group", description: str = "",
                         op_only: bool = False, argument_hint: str = ""):
        """注册一条命令。

        Args:
            trigger: 命令触发词。
            callback: 异步回调函数，接收 CommandContext。
            cmd_type: 命令类型（group/console）。
            description: 命令描述。
            op_only: 是否仅管理员可用。
            argument_hint: 参数提示文本。
        """
        self._commands[trigger] = {
            "trigger": trigger,
            "cmd_type": cmd_type,
            "callback": callback,
            "description": description,
            "op_only": op_only,
            "argument_hint": argument_hint
        }

    def listen(self, event_type: str, handler: Callable, priority: int = 0):
        """订阅事件。

        Args:
            event_type: 事件类名。
            handler: 处理函数。
            priority: 优先级。
        """
        self.event_bus.subscribe(event_type, handler, priority)
        self._event_handlers.append((event_type, handler, priority))

    def register_tool(self, tool_definition: dict):
        """注册工具定义。

        Args:
            tool_definition: 工具字典，需包含 'name' 等字段。
        """
        self._tools.append(tool_definition)