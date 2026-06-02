"""命令注册管理器"""
from typing import Callable, Dict, List, Optional


class CommandManager:
    """统一管理命令的注册、注销与查询。"""

    def __init__(self):
        self._commands: Dict[str, dict] = {}

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
        min_uid: int = 3000,
        plugin_name: str = "core",
    ):
        """注册一条命令。"""
        info = {
            "trigger": trigger,
            "callback": callback,
            "type": cmd_type,
            "description": description,
            "op_only": op_only,
            "required_role": required_role,
            "argument_hint": argument_hint,
            "cooldown": cooldown,
            "min_uid": min_uid,
            "plugin": plugin_name,
        }
        self._commands[trigger] = info

    def unregister(self, trigger: str):
        """注销指定触发词对应的命令。"""
        self._commands.pop(trigger, None)

    def get_group_commands(self) -> List[dict]:
        """获取所有群聊命令信息列表。"""
        return [
            cmd for cmd in self._commands.values() if cmd["type"] == "group"
        ]

    def get_console_commands(self) -> List[dict]:
        """获取所有控制台命令信息列表。"""
        return [
            cmd
            for cmd in self._commands.values()
            if cmd["type"] == "console"
        ]

    def find_command(self, trigger: str) -> Optional[Dict]:
        """按触发词查找命令信息。"""
        return self._commands.get(trigger)
