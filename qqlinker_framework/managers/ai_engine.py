"""AI 引擎 — 将 LLM 对话能力从 AICore 中抽离为独立服务。

模块通过 services.get("ai_engine") 获取实例，不再直接依赖 ai_core。

功能:
  - chat() — 对话接口（支持工具调用循环）
  - chat_simple() — 简单对话（无工具调用）
  - get_available_tools() — 按 UID 获取可用工具 schema
  - get_group_memory() / add_to_memory() — 群对话记忆
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .tool_policy import ToolPolicy, filter_tools

_log = logging.getLogger(__name__)
_log.setLevel(logging.INFO)

# ── 工具注册表（引擎级，与 core.py 的 _TOOL_REGISTRY 定义同步）──

_ENGINE_TOOL_REGISTRY: List[dict] = [
    {
        "name": "send_group_msg",
        "description": "向当前群发送一条消息。用于回复用户的问题或分享信息。",
        "min_uid": 400,
        "parameters": {
            "message": {"type": "string", "description": "要发送的消息内容"},
        },
    },
    {
        "name": "send_private_msg",
        "description": "向当前对话的用户发送私聊消息。仅在需要私密回复时使用。",
        "min_uid": 400,
        "parameters": {
            "message": {"type": "string", "description": "要发送的私聊消息内容"},
        },
    },
    {
        "name": "search_web",
        "description": "搜索互联网获取实时信息。参数：query (搜索关键词)。",
        "min_uid": 300,
        "parameters": {
            "query": {"type": "string", "description": "搜索关键词"},
        },
    },
    {
        "name": "fetch_url",
        "description": "抓取指定网页的文本内容。参数：url (网页地址)。",
        "min_uid": 200,
        "parameters": {
            "url": {"type": "string", "description": "要抓取的网页完整URL"},
        },
    },
    {
        "name": "generate_image",
        "description": "根据文字描述生成图片。参数：prompt (图片描述)。",
        "min_uid": 300,
        "parameters": {
            "prompt": {"type": "string", "description": "图片描述文字"},
        },
    },
    {
        "name": "get_random_image",
        "description": "获取一张随机二次元图片（ACG）。",
        "min_uid": 400,
        "parameters": {},
    },
    {
        "name": "finish",
        "description": "结束当前对话回合，不输出任何内容。AI 完成所有回复后调用此工具。",
        "min_uid": 400,
        "parameters": {},
    },
    {
        "name": "reject_service",
        "description": "拒绝本次服务请求，输出拒绝原因。在余额不足、权限不足、或请求违反规则时使用。",
        "min_uid": 400,
        "parameters": {
            "reason": {"type": "string", "description": "拒绝服务的原因"},
        },
    },
]


class AIEngine:
    """AI 引擎 — 模块通过 services.get("ai_engine") 使用。

    AICore 在 on_init 中创建此实例并注册为服务。其他模块无需再
    通过 tool_manager._root_services 获取 AICore。

    属性:
      ai_core: 反向引用 AICore（用于访问安全规则、审核等核心能力）
    """

    name = "ai_engine"

    def __init__(self, ai_core):
        """初始化引擎。

        Args:
            ai_core: AICore 模块实例（用于内存管理、审核、服务访问等）
        """
        self.ai_core = ai_core
        self._logger = logging.getLogger(f"{__name__}.AIEngine")
        # 可选：引擎级配置覆盖
        self._tool_registry: List[dict] = list(_ENGINE_TOOL_REGISTRY)

    # ═══════════════════════════════════════════════════════════
    # 对话接口
    # ═══════════════════════════════════════════════════════════

    async def chat(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        max_rounds: int = 5,
        tool_executor: Optional[Callable] = None,
        caller_uid: int = 400,
    ) -> str:
        """发送对话，返回 LLM 响应（支持工具调用循环）。

        Args:
            messages: 消息列表 [{"role":"system"|"user"|"assistant", "content":"..."}]
            tools: 工具 schema 列表。为 None 时自动按 caller_uid 获取
            max_rounds: 最大工具调用轮次
            tool_executor: 工具执行回调，签名为 async (name, args) -> str
            caller_uid: 调用方 UID（用于工具策略过滤）

        Returns:
            LLM 最终响应文本
        """
        if not self.ai_core.llm_factory:
            return "AI 引擎未初始化"

        # 按 UID 获取可用工具并过滤
        if tools is None:
            base_tools = self.get_available_tools(caller_uid)
            tools = filter_tools(base_tools, caller_uid)
        elif tools:
            # 即使外部传入了 tools，也要做策略过滤
            tools = filter_tools(list(tools), caller_uid)

        return await self.ai_core.llm_factory.chat(
            messages=messages,
            tools=tools if tools else None,
            max_rounds=max_rounds,
            tool_executor=tool_executor,
        )

    async def chat_simple(self, messages: List[Dict]) -> str:
        """简单对话（无工具调用），返回纯文本。

        Args:
            messages: 消息列表

        Returns:
            LLM 纯文本响应
        """
        if not self.ai_core.llm_factory:
            return "AI 引擎未初始化"

        return await self.ai_core.llm_factory.chat(
            messages=messages,
            tools=None,
            max_rounds=1,
        )

    # ═══════════════════════════════════════════════════════════
    # 工具管理
    # ═══════════════════════════════════════════════════════════

    def get_available_tools(self, min_uid: int = 400) -> List[dict]:
        """获取用户可用的工具 schema 列表（按 min_uid 过滤）。

        Args:
            min_uid: 调用方的最低 UID，只有 min_uid 达到工具要求的
                    工具才会返回

        Returns:
            OpenAI 格式的 tools schema 列表
        """
        available = []
        for tool_def in self._tool_registry:
            if min_uid >= tool_def["min_uid"]:
                params = tool_def.get("parameters", {})
                schema = {
                    "type": "function",
                    "function": {
                        "name": tool_def["name"],
                        "description": tool_def["description"],
                        "parameters": {
                            "type": "object",
                            "properties": params,
                            "required": list(params.keys()),
                        },
                    },
                }
                available.append(schema)
        return available

    def register_engine_tool(self, tool_def: dict) -> None:
        """向引擎注册一个新的工具定义。

        Args:
            tool_def: 工具定义字典，格式与 _ENGINE_TOOL_REGISTRY 一致
        """
        # 防止重复注册
        existing_names = {t["name"] for t in self._tool_registry}
        if tool_def["name"] not in existing_names:
            self._tool_registry.append(tool_def)
            self._logger.info("引擎已注册工具: %s", tool_def["name"])

    # ═══════════════════════════════════════════════════════════
    # 记忆管理
    # ═══════════════════════════════════════════════════════════

    def get_group_memory(self, group_id: int) -> List[Dict]:
        """获取群对话记忆（同步包装，返回历史列表的快照）。

        推荐在不需要异步上下文的场景使用。完整异步版请用
        ai_core._get_group_history()。

        Args:
            group_id: 群号

        Returns:
            对话历史列表 [{"role":..., "content":...}, ...]
        """
        history = self.ai_core.conversations.get(group_id, [])
        max_memory = self.ai_core.max_memory
        return list(history[-max_memory:]) if history else []

    def add_to_memory(self, group_id: int, role: str, content: str) -> None:
        """追加对话记忆（同步包装，调度异步写入）。

        仅追加到内存，不触发文件保存。适合高频调用。持久化请在合适时机
        调用 ai_core._save_group_memory_file()。

        Args:
            group_id: 群号
            role: 角色（"user" | "assistant" | "system"）
            content: 消息内容
        """
        msg = {"role": role, "content": content}
        # 直接追加到 conversations 字典（需注意线程安全）
        if group_id not in self.ai_core.conversations:
            self.ai_core.conversations[group_id] = []
        self.ai_core.conversations[group_id].append(msg)
        self.ai_core.conversation_last_active[group_id] = time.time()

        # 裁剪超量记忆
        limit = self.ai_core.max_memory * 2
        conv = self.ai_core.conversations[group_id]
        if len(conv) > limit:
            self.ai_core.conversations[group_id] = conv[-limit:]

    # ═══════════════════════════════════════════════════════════
    # 异步记忆接口
    # ═══════════════════════════════════════════════════════════

    async def get_group_memory_async(self, group_id: int) -> List[Dict]:
        """获取群对话记忆（异步版，含清理过期逻辑）。

        Args:
            group_id: 群号

        Returns:
            对话历史列表
        """
        return await self.ai_core._get_group_history(group_id)

    async def add_to_memory_async(self, group_id: int,
                                   role: str, content: str) -> None:
        """追加对话记忆并触发文件持久化（异步版）。

        Args:
            group_id: 群号
            role: 角色
            content: 消息内容
        """
        await self.ai_core._add_to_group_history(
            group_id, {"role": role, "content": content}
        )
        await self.ai_core._save_group_memory_file(group_id)
