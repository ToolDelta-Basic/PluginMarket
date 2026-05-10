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
):
    """标记一个方法为命令处理器。"""

    def decorator(func: Callable):
        """将命令信息附加到函数上。"""
        func._command_info = {
            "trigger": trigger,
            "type": cmd_type,
            "description": description,
            "op_only": op_only,
            "argument_hint": argument_hint,
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
