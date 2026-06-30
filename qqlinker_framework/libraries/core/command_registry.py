import logging
import time
from typing import Any, Callable, Dict, List, Optional

from ..channel_host import Library

_log = logging.getLogger(__name__)


class CommandRegistry:
    """命令注册表 — 支持最长匹配优先 + 多变体。"""

    def __init__(self):
        self._commands: Dict[str, dict] = {}
        self._cooldowns: Dict[tuple, float] = {}

    def register(
        self,
        trigger: str,
        callback: Callable,
        *,
        cmd_type: str = "group",
        description: str = "",
        op_only: bool = False,
        required_role: str = "",
        argument_hint: str = "",
        cooldown: float = 0.0,
        min_uid: int = 400,
        plugin: str = "",
        method: str = "",
    ) -> None:
        """注册命令。"""
        self._commands[trigger] = {
            "trigger": trigger,
            "callback": callback,
            "type": cmd_type,
            "description": description,
            "op_only": op_only,
            "required_role": required_role,
            "argument_hint": argument_hint,
            "cooldown": cooldown,
            "min_uid": min_uid,
            "plugin": plugin,
            "method": method,
        }

    def unregister(self, trigger: str) -> None:
        """注销命令。"""
        self._commands.pop(trigger, None)

    def find_best_match(self, message: str) -> Optional[dict]:
        """最长匹配优先查找命令。"""
        best = None
        best_len = 0
        for trigger, info in self._commands.items():
            if message.startswith(trigger):
                if len(trigger) > best_len:
                    # 确保触发词后面是空格或字符串结束
                    rest = message[len(trigger):]
                    if rest == "" or rest[0] == " ":
                        best = info
                        best_len = len(trigger)
        return best

    def find_command(self, trigger: str) -> Optional[dict]:
        """精确查找命令。"""
        return self._commands.get(trigger)

    def get_group_commands(self) -> List[dict]:
        """获取所有群聊命令。"""
        return [c for c in self._commands.values() if c["type"] == "group"]

    def get_console_commands(self) -> List[dict]:
        """获取所有控制台命令。"""
        return [c for c in self._commands.values() if c["type"] == "console"]

    def check_cooldown(self, user_id: int, trigger: str, cooldown: float) -> bool:
        """冷却检查。返回 True 表示通过（可执行），False 表示冷却中。"""
        if cooldown <= 0:
            return True
        now = time.time()
        key = (user_id, trigger)
        last = self._cooldowns.get(key, 0)
        if now - last < cooldown:
            return False
        self._cooldowns[key] = now
        return True


class CommandRegistryLibrary(Library):
    """命令注册库。"""

    name = "command_registry"
    version = "1.6.0"
    dependencies: list = []

    async def mount(self) -> None:
        registry = CommandRegistry()
        self.services.register("command", registry, mid=300)

    async def unmount(self) -> None:
        pass
