# modules/ai/core.py
"""
AI 核心模块：提供 LLM 对话、工具调用、审核拦截、基础记忆
"""
import time
from ...core.module import Module
from ...core.events import GroupMessageEvent
from .llm_client import LLMClientFactory
from .auditor import Auditor
from .tools import register_all
from typing import Dict, List
import logging
import traceback
import re

class AICore(Module):
    """AI 核心模块：集成 LLM 对话、工具调用、审核和会话记忆。"""
    name = "ai_core"
    version = (0, 1, 0)
    required_services = ["config", "message", "tool", "adapter", "dedup"]

    def __init__(self, services, event_bus):
        """初始化 AI 核心模块。

        Args:
            services: 服务容器。
            event_bus: 事件总线。
        """
        super().__init__(services, event_bus)
        self.conversations: Dict[int, List[Dict]] = {}
        self.conversation_last_active: Dict[int, float] = {}
        self.conversation_max_age = 1800  # 30 分钟无活动清除
        self.max_memory = 5

    async def on_init(self):
        """注册配置节、LLM 工厂、审核器、命令和事件监听。"""
        self.config.register_section("AI助手", {
            "是否启用": True,
            "触发词": ["/ai", ".ai", "ai "],
            "模型": "deepseek-chat",
            "API密钥": "",
            "API地址": "https://api.siliconflow.cn/v1",
            "最大工具轮次": 5,
            "记忆条数": 5,
            "审核": {
                "是否启用": True,
                "违规词模式": ["傻逼", "操你", "fuck"],
                "违规次数上限": 3,
                "处理动作": "禁言"
            }
        })

        self.llm_factory = LLMClientFactory(self.config)
        self.auditor = Auditor(self)

        register_all(self.tool)

        triggers = self.config.get("AI助手.触发词", ["/ai"])
        for trigger in triggers:
            self.register_command(trigger, self._cmd_ai_handler,
                                  description="与 AI 对话",
                                  argument_hint="<问题>")

        self.listen("GroupMessageEvent", self.on_group_message, priority=10)

    async def _cmd_ai_handler(self, ctx):
        """命令处理入口，统一异常捕获。"""
        try:
            await self._handle_ai(ctx)
        except Exception as e:
            logging.getLogger(__name__).error("AI 命令异常: %s\n%s", e, traceback.format_exc())
            await ctx.reply(f"AI 服务内部错误: {str(e)}")

    async def _handle_ai(self, ctx):
        """核心 AI 对话处理：违规检查、构建消息历史、调用 LLM、保存记忆。"""
        if not self.config.get("AI助手.是否启用", True):
            await ctx.reply("AI 功能未启用")
            return

        question = " ".join(ctx.args) if ctx.args else ""
        if not question:
            await ctx.reply("请输入问题")
            return

        if self.auditor.check_violation(ctx.user_id, question):
            await ctx.reply("你的消息包含违规内容，已被记录")
            return

        user_id = ctx.user_id
        self._cleanup_expired(user_id)
        history = self._get_history(user_id)
        messages = history + [{"role": "user", "content": question}]

        tools_schema = self.tool.get_tools_schema(only_enabled=True)
        logging.getLogger(__name__).info("可用工具: %s", [t["function"]["name"] for t in tools_schema])

        response = await self.llm_factory.chat(
            messages=messages,
            tools=tools_schema if tools_schema else None,
            max_rounds=self.config.get("AI助手.最大工具轮次", 5),
            tool_executor=self._execute_tool
        )

        self._add_to_history(user_id, {"role": "user", "content": question})
        if response:
            self._add_to_history(user_id, {"role": "assistant", "content": response})

        # 图片处理
        image_urls = re.findall(r'\[IMAGE:(.*?)\]', response)
        for url in image_urls:
            await self.message.send_group(ctx.group_id, f"[CQ:image,file={url}]")
            response = response.replace(f"[IMAGE:{url}]", "").strip()

        if response:
            await ctx.reply(response)
        elif not image_urls:
            await ctx.reply("AI 未返回内容")

    async def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """执行工具并返回结果字符串，供 LLM 客户端调用。

        Args:
            tool_name: 工具名称。
            arguments: 工具参数。

        Returns:
            工具执行结果。
        """
        try:
            return await self.tool.execute(tool_name, arguments, context={"user_id": 0})
        except Exception as e:
            logging.getLogger(__name__).error("工具执行失败 %s: %s", tool_name, e)
            return f"工具调用失败: {str(e)}"

    async def on_group_message(self, event: GroupMessageEvent):
        """处理群消息事件，执行内容审核。"""
        self.auditor.process_message(event.user_id, event.group_id, event.message)

    def _cleanup_expired(self, user_id: int):
        """清除长时间未活动的会话历史。

        Args:
            user_id: 用户 QQ 号。
        """
        now = time.time()
        last = self.conversation_last_active.get(user_id, 0)
        if last and (now - last) > self.conversation_max_age:
            self.conversations.pop(user_id, None)
            self.conversation_last_active.pop(user_id, None)

    def _get_history(self, user_id: int) -> List[Dict]:
        """获取用户最近的对话历史（受记忆条数限制）。

        Args:
            user_id: 用户 QQ 号。

        Returns:
            历史消息列表。
        """
        now = time.time()
        self.conversation_last_active[user_id] = now
        hist = self.conversations.get(user_id, [])
        return hist[-self.max_memory:]

    def _add_to_history(self, user_id: int, msg: Dict):
        """向用户会话历史添加一条消息，并限制总条数。

        Args:
            user_id: 用户 QQ 号。
            msg: 消息字典 {"role": ..., "content": ...}
        """
        self.conversation_last_active[user_id] = time.time()
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        self.conversations[user_id].append(msg)
        max_total = self.max_memory * 2
        if len(self.conversations[user_id]) > max_total:
            self.conversations[user_id] = self.conversations[user_id][-max_total:]