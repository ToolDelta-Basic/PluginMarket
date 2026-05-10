"""声明式装饰器"""
from typing import Callable

def command(trigger: str, *, cmd_type: str = "group",
            description: str = "", op_only: bool = False,
            argument_hint: str = ""):
    """标记一个方法为命令处理器。

    Args:
        trigger: 命令触发词。
        cmd_type: 类型，group 或 console。
        description: 命令描述。
        op_only: 是否仅管理员可用。
        argument_hint: 参数提示。
    """
    def decorator(func: Callable):
        func._command_info = {
            "trigger": trigger,
            "type": cmd_type,
            "description": description,
            "op_only": op_only,
            "argument_hint": argument_hint
        }
        return func
    return decorator

def listen(event_type: str, priority: int = 0):
    """标记一个方法为事件监听器。

    Args:
        event_type: 事件类名。
        priority: 优先级。
    """
    def decorator(func: Callable):
        func._event_info = {
            "event_type": event_type,
            "priority": priority
        }
        return func
    return decorator