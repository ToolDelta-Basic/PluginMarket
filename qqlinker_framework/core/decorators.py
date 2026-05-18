# pylint: disable=protected-access
"""声明式装饰器"""
from typing import Callable


def command(
    trigger: str,
    *,
    cmd_type: str = "group",
    description: str = "",
    op_only: bool = False,
    argument_hint: str = "",
    cooldown: float = 0.0,
):
    """标记方法为命令处理器。

    Args:
        trigger: 命令触发词（如 ".帮助"）。
        cmd_type: 命令类型，通常为 "group"。
        description: 帮助文本中的描述。
        op_only: 是否仅管理员可用。
        argument_hint: 用法提示（如 "<玩家名>"）。
        cooldown: 每用户冷却时间（秒），0 表示无冷却。
    """

    def decorator(func: Callable):
        func._command_info = {
            "trigger": trigger,
            "type": cmd_type,
            "description": description,
            "op_only": op_only,
            "argument_hint": argument_hint,
            "cooldown": cooldown,
        }
        return func

    return decorator


def listen(event_type: str, priority: int = 0):
    """标记一个方法为事件监听器。"""

    def decorator(func: Callable):
        """将事件监听信息附加到函数上。"""
        func._event_info = {
            "event_type": event_type,
            "priority": priority,
        }
        return func

    return decorator
