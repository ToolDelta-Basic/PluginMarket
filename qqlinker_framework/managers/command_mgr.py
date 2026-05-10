# managers/command_mgr.py
"""命令注册管理器"""
from typing import Callable, Dict, List, Optional

class CommandManager:
    """统一管理命令的注册、注销与查询。"""
    def __init__(self):
        """初始化命令字典。"""
        self._commands: Dict[str, dict] = {}

    def register(self, trigger: str, callback: Callable, *,
                 cmd_type: str = "group",
                 description: str = "",
                 op_only: bool = False,
                 argument_hint: str = "",
                 plugin_name: str = "core"):
        """注册一条命令。

        Args:
            trigger: 命令触发词。
            callback: 回调函数。
            cmd_type: 类型 (group/console)。
            description: 描述。
            op_only: 是否仅管理员。
            argument_hint: 参数提示。
            plugin_name: 所属模块名。
        """
        info = {
            "trigger": trigger,
            "callback": callback,
            "type": cmd_type,
            "description": description,
            "op_only": op_only,
            "argument_hint": argument_hint,
            "plugin": plugin_name
        }
        self._commands[trigger] = info
    def unregister(self, trigger: str):
        """注销指定触发词对应的命令。

        Args:
            trigger: 命令触发词。
        """
        self._commands.pop(trigger, None)

    def get_group_commands(self) -> List[dict]:
        """获取所有群聊命令信息列表。"""
        return [cmd for cmd in self._commands.values() if cmd["type"] == "group"]

    def get_console_commands(self) -> List[dict]:
        """获取所有控制台命令信息列表。"""
        return [cmd for cmd in self._commands.values() if cmd["type"] == "console"]

def find_command(self, trigger: str) -> Optional[Dict]:
        """按触发词查找命令信息。

        Args:
            trigger: 触发词。

        Returns:
            命令字典或 None。
        """
        return self._commands.get(trigger)