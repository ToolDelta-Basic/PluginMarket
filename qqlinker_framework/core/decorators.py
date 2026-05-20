# pylint: disable=protected-access
"""声明式装饰器 — 支持命令、事件、工具、定时任务的声明式注册。"""
from typing import Any, Callable


def command(
    trigger: str,
    *,
    cmd_type: str = "group",
    description: str = "",
    op_only: bool = False,
    argument_hint: str = "",
    cooldown: float | None = None,
):
    """标记方法为命令处理器。

    Args:
        trigger: 命令触发词（如 ".帮助"）。
        cooldown: 冷却秒。None 取模块 default_cooldown。
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
    """标记方法为事件监听器。

    Args:
        event_type: 事件类名（如 "GroupMessageEvent"）。
        priority: 优先级，数值越高越早执行。
    """

    def decorator(func: Callable):
        func._event_info = {
            "event_type": event_type,
            "priority": priority,
        }
        return func
    return decorator


def tool(
    name: str,
    description: str,
    parameters: dict | None = None,
    *,
    timeout: int = 30,
    enabled: bool = True,
    risk_level: str = "low",
    admin_only: bool = False,
    category: str = "general",
    required_config_keys: list[str] | None = None,
):
    """标记方法为 AI 可调用的工具。

    方法签名可为:
      async def handler(self, params, context) -> str
      async def handler(self, params, context, tool_config) -> str

    Args:
        name: 工具唯一名称。
        description: 工具描述。
        parameters: OpenAI JSON Schema properties 字典。
        timeout: 执行超时秒数。
        admin_only: 是否仅管理员可用。
        category: 工具分类。
        required_config_keys: API 提供者名称列表。
    """

    def decorator(func: Callable):
        func._tool_info = {
            "name": name,
            "description": description,
            "parameters": parameters or {},
            "callback": func,
            "timeout": timeout,
            "enabled": enabled,
            "risk_level": risk_level,
            "admin_only": admin_only,
            "category": category,
            "required_config_keys": required_config_keys or [],
        }
        return func
    return decorator


def schedule(
    name: str | None = None,
    *,
    interval: float | None = None,
    cron: str | None = None,
    run_on_start: bool = False,
    enabled: bool = True,
):
    """标记方法为定时任务。

    支持两种模式:
      · interval 模式: 每 N 秒执行一次
      · cron 模式: 按自然分钟触发（简化版，每60秒检查一次）

    Args:
        name: 任务名称（默认取方法名）。
        interval: 间隔秒数。
        cron: cron 表达式（暂支持每分钟轮询）。
        run_on_start: 是否启动时立即执行一次。
        enabled: 是否启用。
    """

    def decorator(func: Callable):
        func._schedule_info = {
            "name": name or func.__name__,
            "interval": interval,
            "cron": cron,
            "run_on_start": run_on_start,
            "enabled": enabled,
        }
        return func
    return decorator
