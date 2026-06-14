"""工作流注册装饰器 — 声明式定义管理工具工作流

═══════════════════════════════════════════════════════════════════════════
 用法示例

   from .admin_tools import AdminToolManager, WorkflowStep, FailStrategy

   @admin_workflow(
       name="全服维护",
       description="踢出所有玩家、发公告、关服",
       steps=[
           WorkflowStep("踢出玩家", module="orion", method="kick_all", args_from_ctx=True),
           WorkflowStep("发送公告", module="message", method="broadcast", args={"msg": "服务器维护中..."}),
           WorkflowStep("关闭服务器", module="adapter", method="shutdown"),
       ],
       require_confirm=True,
   )
   async def maintenance(ctx):
       pass  # 函数体可为空，纯声明式定义
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from .admin_tools import AdminToolManager
from qqlinker_framework.managers.admin_tools.workflow_registry import WorkflowStep, FailStrategy, WorkflowDefinition

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 装饰器：admin_workflow
# ═══════════════════════════════════════════════════════════════

def admin_workflow(
    name: str,
    *,
    description: str = "",
    steps: List[Union[WorkflowStep, Dict[str, Any]]] = None,
    fail_strategy: Union[FailStrategy, str] = FailStrategy.STOP_ON_ERROR,
    require_confirm: bool = False,
    min_tier: str = "daemon",
    # ── 注入钩子: 允许函数体作为预执行钩子 ──
    pre_hook: bool = False,   # True 时函数体作为预执行钩子调用
    post_hook: bool = False,  # True 时函数体作为后执行钩子调用
):
    """声明式工作流装饰器 — 在模块 init 阶段自动注册到 AdminToolManager。

    Args:
        name: 工作流唯一名称
        description: 人类可读描述
        steps: 步骤列表
        fail_strategy: 失败策略
        require_confirm: 是否需要执行前确认
        min_tier: 最低允许执行层级
        pre_hook: 函数体是否为预执行钩子
        post_hook: 函数体是否为后执行钩子

    使用方式:
        @admin_workflow(name="维护", steps=[...], require_confirm=True)
        async def maintenance(ctx):
            pass

    被装饰的函数会在工作流注册时被关联，用于:
      - pre_hook=True: 在执行工作流前调用
      - post_hook=True: 在执行工作流后调用
      - 默认: 作为便捷入口，通过 管理工具.执行工作流 触发
    """
    steps = steps or []

    def decorator(func: Callable):
        """内部装饰器：附加工作流元信息。"""
        # 附加元数据到函数上
        func._workflow_info = {
            "name": name,
            "description": description,
            "steps": steps,
            "fail_strategy": fail_strategy,
            "require_confirm": require_confirm,
            "min_tier": min_tier,
            "pre_hook": pre_hook,
            "post_hook": post_hook,
        }

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            """包装后的函数 — 在模块加载时被转换为工作流注册。"""
            return await func(*args, **kwargs)

        wrapper._workflow_info = func._workflow_info
        return wrapper

    return decorator


# ═══════════════════════════════════════════════════════════════
# 便捷装饰器：admin_command
# ═══════════════════════════════════════════════════════════════

def admin_command(
    trigger: str,
    *,
    workflow_name: str = None,
    description: str = "",
    steps: List[Union[WorkflowStep, Dict[str, Any]]] = None,
    fail_strategy: Union[FailStrategy, str] = FailStrategy.STOP_ON_ERROR,
    require_confirm: bool = False,
    min_tier: str = "daemon",
    min_uid: int = 200,
    argument_hint: str = "",
    cooldown: float = 0.0,
):
    """组合装饰器: 同时注册为命令和关联工作流。

    当一个 @admin_command 装饰的函数被触发时:
      1. 查找关联的 admin_workflow
      2. 通过 AdminToolManager.execute_workflow 执行
      3. 返回格式化的结果

    Args:
        trigger: 命令触发词（如 ".全服维护"）
        workflow_name: 关联的工作流名（默认同 trigger）
        description: 命令/工作流描述
        steps: 工作流步骤
        fail_strategy: 失败策略
        require_confirm: 是否需要确认
        min_tier: 工作流最低 tier
        min_uid: 命令最低 UID
        argument_hint: 命令参数提示
        cooldown: 命令冷却秒
    """
    steps = steps or []
    wf_name = workflow_name or trigger.lstrip(".")
    
    # ── 导入所需的装饰器 ──
    try:
        from qqlinker_framework.core.kernel.decorators import command as _command_decorator
    except ImportError:
        from qqlinker_framework.core.kernel.decorators import command as _command_decorator

    def decorator(func: Callable):
        """双层装饰: 同时注册工作流和命令。"""
        # 1. 注册工作流元数据
        func._workflow_info = {
            "name": wf_name,
            "description": description,
            "steps": steps,
            "fail_strategy": fail_strategy,
            "require_confirm": require_confirm,
            "min_tier": min_tier,
            "pre_hook": False,
            "post_hook": False,
        }

        @functools.wraps(func)
        @_command_decorator(
            trigger, description=description,
            min_uid=min_uid, argument_hint=argument_hint,
            cooldown=cooldown,
        )
        async def wrapper(self, ctx):
            """命令处理器 — 委托给 AdminToolManager 执行工作流。"""
            # 从 services 获取 admin_tool 实例
            admin_tool: Optional[AdminToolManager] = None
            try:
                admin_tool = self.services.get("admin_tool")
            except Exception:
                pass

            if admin_tool is None:
                await ctx.reply("❌ 管理工具编排器未初始化")
                return

            # 处理确认参数
            args = getattr(ctx, 'args', []) or []
            bypass_confirm = "--confirm" in args

            # 获取调用方 UID
            caller_uid = getattr(self, 'uid', 400)

            # 执行前钩子
            if func._workflow_info.get("pre_hook"):
                try:
                    await func(self, ctx)
                except Exception as e:
                    await ctx.reply(f"❌ 预执行钩子失败: {e}")
                    return

            # 执行工作流
            result = await admin_tool.execute_workflow(
                wf_name, ctx,
                bypass_confirm=bypass_confirm,
                caller_uid=caller_uid,
            )

            # 后执行钩子
            if func._workflow_info.get("post_hook"):
                try:
                    await func(self, ctx)
                except Exception:
                    _log.exception("后执行钩子异常")

            # 格式化输出
            formatted = AdminToolManager.format_result(result)
            await ctx.reply(formatted)

        return wrapper

    return decorator


# ═══════════════════════════════════════════════════════════════
# 模块加载时的自动注册钩子
# ═══════════════════════════════════════════════════════════════

def register_decorated_workflows(module_instance, admin_tool_manager: AdminToolManager) -> int:
    """扫描模块实例中所有被 @admin_workflow / @admin_command 装饰的方法，
    自动注册到 AdminToolManager。

    在 FrameworkHost 的 register_default_capabilities 中调用。

    Args:
        module_instance: 模块实例
        admin_tool_manager: AdminToolManager 实例

    Returns:
        注册的工作流数量
    """
    import inspect

    count = 0
    for _, method in inspect.getmembers(
        module_instance,
        predicate=lambda m: inspect.ismethod(m) or inspect.isfunction(m)
    ):
        for attr_name in ('_workflow_info', '__wrapped__'):
            try:
                info = getattr(method, '_workflow_info', None)
                if info is None and hasattr(method, '__wrapped__'):
                    info = getattr(method.__wrapped__, '_workflow_info', None)
            except Exception:
                continue
            if info is None:
                continue

            wf = admin_tool_manager.register_workflow(
                name=info["name"],
                steps=info.get("steps", []),
                description=info.get("description", ""),
                fail_strategy=info.get("fail_strategy", FailStrategy.STOP_ON_ERROR),
                require_confirm=info.get("require_confirm", False),
                min_tier=info.get("min_tier", "daemon"),
                source="python",
            )
            if wf:
                count += 1
                _log.debug(
                    "已注册装饰器工作流: '%s' (%d 步)",
                    wf.name, len(wf.steps),
                )
            break  # 只处理第一个找到的属性

    return count
