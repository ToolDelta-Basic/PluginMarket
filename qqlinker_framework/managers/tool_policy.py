"""工具注册：ToolPolicy（白名单/黑名单模式）与工具过滤逻辑。

每个模块引用 AI 引擎时可以声明自己的工具策略，引擎根据 caller_uid
和策略过滤返回的 tools schema 列表。

用法:
  - 模块创建 ToolPolicy 并注册到引擎
  - 调用 chat() 时传递 caller_uid，引擎自动过滤工具
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── 工具策略模式 ───────────────────────────────────────────────


@dataclass
class ToolPolicy:
    """模块级工具策略 — 控制 AI 引擎为该模块提供哪些工具。

    Attributes:
        mode: "all"（所有可用工具）、"whitelist"（仅白名单）、"blacklist"（黑名单除外）
        tools: 白名单或黑名单工具名列表
    """
    mode: str = "all"          # "all" | "whitelist" | "blacklist"
    tools: List[str] = field(default_factory=list)


# ── 默认策略注册表 ─────────────────────────────────────────────
# key: caller_uid → ToolPolicy
# 未注册的 caller_uid 默认使用 "all" 模式

_policy_registry: Dict[int, ToolPolicy] = {}


def register_policy(caller_uid: int, policy: ToolPolicy) -> None:
    """为一个调用方 UID 注册工具策略。

    Args:
        caller_uid: 调用方模块的 UID
        policy: ToolPolicy 实例
    """
    _policy_registry[caller_uid] = policy


def unregister_policy(caller_uid: int) -> None:
    """移除调用方的工具策略。"""
    _policy_registry.pop(caller_uid, None)


def get_policy(caller_uid: int) -> ToolPolicy:
    """获取调用方的工具策略，未注册时返回默认 'all'。"""
    return _policy_registry.get(caller_uid, ToolPolicy(mode="all"))


def filter_tools(tools_schema: List[dict], caller_uid: int) -> List[dict]:
    """根据 caller_uid 的工具策略过滤 tools schema 列表。

    引擎查询 min_uid 后的可用工具列表传入此函数，
    函数再按模块策略做二次过滤。

    Args:
        tools_schema: 引擎基础可用工具 schema 列表
        caller_uid: 调用方模块的 UID

    Returns:
        过滤后的 tools schema 列表
    """
    policy = get_policy(caller_uid)

    if policy.mode == "all":
        return tools_schema

    if policy.mode == "whitelist":
        return [
            t for t in tools_schema
            if t["function"]["name"] in policy.tools
        ]

    if policy.mode == "blacklist":
        blacklist = set(policy.tools)
        return [
            t for t in tools_schema
            if t["function"]["name"] not in blacklist
        ]

    # 未知模式 → 全部放行（安全默认）
    return tools_schema


# ── 预定义策略常量 ─────────────────────────────────────────────

# 只读策略：只给 AI 信息获取工具，不给发送/操作权限
READONLY_POLICY = ToolPolicy(
    mode="whitelist",
    tools=["get_recent_memory", "get_long_memory", "get_persona",
           "search_web", "fetch_url", "finish", "reject_service"],
)

# 无工具策略：纯对话，不暴露任何工具
NO_TOOLS_POLICY = ToolPolicy(
    mode="whitelist",
    tools=[],
)
