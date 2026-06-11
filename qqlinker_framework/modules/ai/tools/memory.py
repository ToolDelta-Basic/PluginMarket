"""AI 记忆工具 — 让 AI 通过工具自主获取上下文，而非预加载。

v1.4.3: 工具驱动上下文。AI 收到消息后先调用这些工具获取需要的信息，
然后才回复。这大幅减少了每次请求的 token 消耗。

工具:
  get_recent_memory  — 获取最近的对话历史
  get_long_memory    — 搜索长期记忆中的内容
  get_persona        — 获取当前用户的角色设定
"""

import logging

_log = logging.getLogger(__name__)


def register_tools(tool_manager):
    """注册记忆相关工具到 ToolManager。

    工具通过闭包访问 AICore 实例，在 AI 工具调用时动态获取数据，
    而不是在构建 messages 时预加载。

    Args:
        tool_manager: ToolManager 实例。
    """
    # 获取 AICore 引用
    try:
        services = tool_manager._root_services
        ai_core = services.get("ai_core")
    except (KeyError, AttributeError):
        _log.warning("记忆工具: 无法获取 ai_core 服务，跳过注册")
        return

    async def _get_recent_memory(params: dict, context, tool_config):
        """获取指定群最近 N 条对话历史。

        参数:
          limit: 最多返回条数（默认 10，最大 50）
        """
        group_id = context.get("group_id", 0) if isinstance(context, dict) else getattr(context, "group_id", 0)
        if not group_id:
            return "无法确定群 ID"

        limit = min(int(params.get("limit", 10)), 50)
        history = await ai_core._get_group_history(group_id)

        if not history:
            return "暂无对话历史"

        recent = history[-limit:]
        lines = [f"[{m.get('role', '?')}] {m.get('content', '')[:500]}" for m in recent]
        return "\n".join(lines)

    async def _get_long_memory(params: dict, context, tool_config):
        """搜索长期记忆中的相关内容。

        参数:
          query: 搜索关键词
          limit: 最多返回条数（默认 5）
        """
        group_id = context.get("group_id", 0) if isinstance(context, dict) else getattr(context, "group_id", 0)
        query = params.get("query", "")
        if not query:
            return "请提供搜索关键词"

        limit = min(int(params.get("limit", 5)), 20)
        history = await ai_core._get_group_history(group_id)

        if not history:
            return "暂无长期记忆"

        # 简单关键词匹配
        query_lower = query.lower()
        matched = []
        for m in history:
            content = m.get("content", "").lower()
            if query_lower in content:
                matched.append(f"[{m.get('role', '?')}] {m.get('content', '')[:300]}")
                if len(matched) >= limit:
                    break

        if not matched:
            return f"未找到与 '{query}' 相关的记忆"
        return "\n".join(matched)

    async def _get_persona(params: dict, context, tool_config):
        """获取当前用户的角色设定。"""
        user_id = context.get("user_id", 0) if isinstance(context, dict) else getattr(context, "user_id", 0)
        if not user_id:
            return "无法确定用户 ID"

        service = ai_core._get_persona_service()
        if not service:
            return "角色系统不可用"

        persona = service.get_persona(user_id)
        if not persona:
            return "该用户未设定角色"

        return f"用户当前角色设定: {persona}"

    tool_manager.register_tool({
        "name": "get_recent_memory",
        "description": "获取最近几条群聊对话历史。当用户的问题涉及之前聊过的内容时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "返回的对话条数，默认 10，最大 50"
                }
            }
        },
        "callback": _get_recent_memory,
        "category": "memory"
    })

    tool_manager.register_tool({
        "name": "get_long_memory",
        "description": "按关键词搜索长期记忆中存储的对话内容。当用户提到特定话题/事件/人物时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回条数，默认 5，最大 20"
                }
            },
            "required": ["query"]
        },
        "callback": _get_long_memory,
        "category": "memory"
    })

    tool_manager.register_tool({
        "name": "get_persona",
        "description": "获取当前用户的角色设定。当 AI 需要知道用户设定的是什么角色时调用。",
        "parameters": {
            "type": "object",
            "properties": {}
        },
        "callback": _get_persona,
        "category": "memory"
    })

    _log.info("已注册记忆工具: get_recent_memory, get_long_memory, get_persona")
