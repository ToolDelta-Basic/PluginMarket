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
        argument_hint: str = "",
        plugin_name: str = "core",
    ):
        info = {
            "trigger": trigger,
            "callback": callback,
            "type": cmd_type,
            "description": description,
            "op_only": op_only,
            "argument_hint": argument_hint,
            "plugin": plugin_name,
        }
        self._commands[trigger] = info

    def unregister(self, trigger: str):
        self._commands.pop(trigger, None)

    def get_group_commands(self) -> List[dict]:
        return [
            cmd for cmd in self._commands.values() if cmd["type"] == "group"
        ]

    def get_console_commands(self) -> List[dict]:
        return [
            cmd
            for cmd in self._commands.values()
            if cmd["type"] == "console"
        ]

    def find_command(self, trigger: str) -> Optional[Dict]:
        return self._commands.get(trigger)
