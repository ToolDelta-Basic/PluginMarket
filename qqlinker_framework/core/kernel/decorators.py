# pylint: disable=protected-access
"""声明式装饰器 — 支持命令、事件、工具、定时任务的声明式注册。"""
from typing import Any, Callable


# ── @exec_exposed 装饰器 ───────────────────────────────────

def exec_exposed(func):
    """标记方法可通过 .exec 命令调用。

    只有标记了此装饰器的方法才能被 root 通过 .exec 调用。
    攻击面限制在明确标记为安全的公开方法上。
    """
    func._exec_exposed = True
    return func


def is_exec_exposed(method) -> bool:
    """检查方法是否标记了 @exec_exposed。"""
    return getattr(method, '_exec_exposed', False)


def command(
    trigger: str,
    *,
    sub: str = "",
    cmd_type: str = "group",
    description: str = "",
    op_only: bool = False,
    required_role: str = "",
    argument_hint: str = "",
    cooldown: float | None = None,
    min_uid: int = 400,
):
    """标记方法为命令处理器。

    支持多变体和子命令：
      @command(".规则 | /规则")              → .规则 和 /规则 都触发
      @command(".规则 | /规则", sub="创建")  → .规则 创建 触发

    Args:
        trigger: 命令触发词，用 | 分隔多个变体（如 ".帮助 | /帮助 | 帮助"）。
        sub: 子命令名（如 "创建"）。空串表示主命令。
        cooldown: 冷却秒。None 取模块 default_cooldown。
        required_role: 需要的角色名，空串不限制。
        min_uid: 最低 UID 等级。默认 400 (nobody)。
    """

    def decorator(func: Callable):
        """内部装饰器：附加命令元信息。"""
        # 解析 | 分隔的多变体
        variants = [t.strip() for t in trigger.split("|") if t.strip()]
        primary = variants[0] if variants else trigger.strip()
        func._command_info = {
            "trigger": primary,
            "variants": variants,
            "sub": sub,
            "type": cmd_type,
            "description": description,
            "op_only": op_only,
            "required_role": required_role,
            "argument_hint": argument_hint,
            "cooldown": cooldown,
            "min_uid": min_uid,
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
        """内部装饰器: 将事件元信息附加到函数 _event_info 属性。"""
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
        """内部装饰器: 将工具元信息附加到函数 _tool_info 属性。"""
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
        """内部装饰器: 将定时任务元信息附加到函数 _schedule_info 属性。"""
        func._schedule_info = {
            "name": name or func.__name__,
            "interval": interval,
            "cron": cron,
            "run_on_start": run_on_start,
            "enabled": enabled,
        }
        return func
    return decorator


# ═══════════════════════════════════════════════════════════════
# 简化装饰器 — 模块顶层函数可直接使用的 @every / @cron
# ═══════════════════════════════════════════════════════════════

def every(seconds: float, *, run_on_start: bool = False, name: str = None):
    """模块内使用 @every(seconds=N) 标记定时任务。

    用法:
        class MyMod(Module):
            @every(30)
            async def heartbeat(self):
                self.game.cmd("/say tick")

    等价于手写 ScheduledTask。
    """
    return schedule(name=name, interval=seconds, run_on_start=run_on_start)


def cron(expr: str, *, run_on_start: bool = False, name: str = None):
    """模块内使用 @cron("0 * * * *") 标记 cron 定时任务。

    用法:
        class MyMod(Module):
            @cron("0 * * * *")
            async def hourly(self):
                self.qq.send_group(12345, "整点报时")

    等价于手写 ScheduledTask with cron。
    """
    return schedule(name=name, cron=expr, run_on_start=run_on_start)
