"""信道协议 — 框架唯一的通信契约。

所有库通过这三个接口通信，没有其他隐式依赖。
信道本身不包含实现，只定义协议。
"""
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Type
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════
# 信道事件
# ═══════════════════════════════════════════════════════════

@dataclass
class ChannelEvent:
    """信道事件基类。所有事件必须继承此类。"""
    handled: bool = False
    _source_library: str = ""


# ═══════════════════════════════════════════════════════════
# ServiceBus — 服务总线协议
# ═══════════════════════════════════════════════════════════

class ServiceBus(Protocol):
    """服务总线：注册和获取库提供的服务。

    库通过 register() 暴露服务，通过 get() 消费其他库的服务。
    mid 是服务的权限等级（0=root, 100=daemon, 200=service, 300=app, 400=nobody）。
    """

    def register(self, name: str, instance: Any, *,
                 mid: int = 300, description: str = "") -> None:
        """注册一个服务。"""

    def get(self, name: str) -> Any:
        """获取已注册的服务。若未注册则抛出 KeyError。"""

    def try_get(self, name: str) -> Optional[Any]:
        """安全获取服务，不存在返回 None。"""

    def has(self, name: str) -> bool:
        """检查服务是否已注册。"""


# ═══════════════════════════════════════════════════════════
# EventPipe — 事件管道协议
# ═══════════════════════════════════════════════════════════

EventHandler = Callable[[ChannelEvent], Any]


class EventPipe(Protocol):
    """事件管道：库之间通过事件异步通信。

    发布者不关心谁在监听，订阅者不关心谁发的。
    """

    def subscribe(self, event_type: str, handler: EventHandler,
                  priority: int = 0) -> None:
        """订阅事件类型。priority 越大越早执行。"""

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """取消订阅。"""

    async def publish(self, event: ChannelEvent) -> None:
        """发布事件，按优先级顺序通知所有订阅者。"""


# ═══════════════════════════════════════════════════════════
# ConfigSource — 配置源协议
# ═══════════════════════════════════════════════════════════

class ConfigSource(Protocol):
    """配置源：库读写配置的通道。

    支持点号分隔的路径（如 "网络连接.地址"）。
    """

    def get(self, path: str, default: Any = None) -> Any:
        """读取配置值。"""

    def set(self, path: str, value: Any) -> None:
        """写入配置值。"""

    def register_section(self, section: str, defaults: dict) -> None:
        """注册一个配置节及其默认值。"""

    def load(self) -> None:
        """从持久化存储加载配置。"""

    def get_data_dir(self) -> str:
        """获取数据目录路径。"""


# ═══════════════════════════════════════════════════════════
# MessageBus — 消息总线协议
# ═══════════════════════════════════════════════════════════

class MessageBus(Protocol):
    """消息总线：向外部平台发送消息。

    封装了具体平台的消息发送方式。
    """

    async def send_group(self, group_id: int, message: str) -> bool:
        """发送群聊消息。"""

    async def send_private(self, user_id: int, message: str) -> bool:
        """发送私聊消息。"""


# ═══════════════════════════════════════════════════════════
# CommandRegistry — 命令注册协议
# ═══════════════════════════════════════════════════════════

class CommandRegistry(Protocol):
    """命令注册表：库注册自己能处理的命令。"""

    def register(self, trigger: str, callback: Callable, *,
                 cmd_type: str = "group", description: str = "",
                 op_only: bool = False, min_uid: int = 400,
                 cooldown: float = 0.0, plugin: str = "") -> None:
        """注册一条命令。"""

    def unregister(self, trigger: str) -> None:
        """注销一条命令。"""


# ═══════════════════════════════════════════════════════════
# Library — 库挂载协议
# ═══════════════════════════════════════════════════════════

class Library:
    """可挂载到信道的库。

    每个库通过 mount() 接入信道，通过 unmount() 卸载。

    通信通道（挂载后可用）:
      - self.services  → ServiceBus   (服务获取/注册)
      - self.events    → EventPipe    (事件发布/订阅)
      - self.config    → ConfigSource (配置读写)
      - self.messages  → MessageBus   (消息发送)
      - self.commands  → CommandRegistry (命令注册)
    """

    name: str = ""
    version: str = "0.0.0"
    dependencies: List[str] = []

    services: Optional[ServiceBus] = None
    events: Optional[EventPipe] = None
    config: Optional[ConfigSource] = None
    messages: Optional[MessageBus] = None
    commands: Optional[CommandRegistry] = None

    async def mount(self) -> None:
        """挂载库：注册服务、订阅事件、初始化资源。"""

    async def unmount(self) -> None:
        """卸载库：清理资源、取消订阅、关闭连接。"""
