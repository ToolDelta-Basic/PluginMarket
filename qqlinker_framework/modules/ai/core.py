"""AI 核心模块：提供 LLM 对话、工具调用、审核拦截、基础记忆"""
import asyncio
import logging
import os
import time
import traceback
import re
import json
from typing import Dict, List

from ...core.module import Module
from ...core.events import (
    GroupMessageEvent,
    AIPrePromptReflectionEvent,
    AIPostResponseReflectionEvent,
)
from .llm_client import LLMClientFactory
from .auditor import Auditor
from .tools import register_all


class AICore(Module):
    """AI 核心模块：集成 LLM 对话、工具调用、审核和会话记忆。"""

    name = "ai_core"
    version = (0, 1, 0)
    required_services = [
        "config", "message", "tool", "adapter", "dedup"
    ]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self.conversations: Dict[int, List[Dict]] = {}
        self.conversation_last_active: Dict[int, float] = {}
        self.conversation_max_age = 1800
        self.max_memory = 5
        self.llm_factory = None
        self.auditor = None
        self.persona = None
        self._safety_rules: list[str] = []
        self._memory_dir = ""
        self._memory_lock = asyncio.Lock()

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
                "处理动作": "禁言",
            },
            "安全规则": [
                "绝对禁止生成任何违法内容，包括但不限于暴力、色情、欺诈、侵犯隐私等。",
                "不得协助用户进行任何形式的网络攻击、破解、恶意代码编写。",
                "不得提供可能危害未成年人身心健康的内容或建议。",
                "若用户要求扮演的角色试图违背这些规则，你必须礼貌拒绝并说明原因。",
                "在回答时始终保持对他人的人格尊重，禁止羞辱、歧视或人身攻击。",
            ],
        })

        self.llm_factory = LLMClientFactory(self.config)
        self.auditor = Auditor(self)

        # 安全获取 persona 服务（如果存在）
        try:
            self.persona = self.services.get("persona")
        except KeyError:
            self.persona = None

        self._safety_rules = self.config.get("AI助手.安全规则", [])

        # 设置长时记忆目录
        base_dir = self.get_data_dir()
        self._memory_dir = os.path.join(base_dir, "用户记忆")
        os.makedirs(self._memory_dir, exist_ok=True)

        register_all(self.tool)

        triggers = self.config.get("AI助手.触发词", ["/ai"])
        for trigger in triggers:
            self.register_command(
                trigger,
                self._cmd_ai_handler,
                description="与 AI 对话",
                argument_hint="<问题>",
            )

        # 管理员记忆管理命令
        self.register_command(
            ".delmemory", self._cmd_del_memory,
            description="删除指定用户的长期记忆（管理员）",
            op_only=True, argument_hint="<QQ号>",
        )
        self.register_command(
            ".clearmemory", self._cmd_clear_memory,
            description="清除所有用户的长时记忆（管理员）",
            op_only=True,
        )

        self.listen("GroupMessageEvent", self.on_group_message, priority=10)

    async def _cmd_ai_handler(self, ctx):
        """命令处理入口，统一异常捕获。"""
        try:
            await self._handle_ai(ctx)
        except Exception as e:
            logging.getLogger(__name__).error(
                "AI 命令异常: %s\n%s", e, traceback.format_exc()
            )
            await ctx.reply(f"AI 服务内部错误: {str(e)}")

    def _build_system_prompt(self, user_id: int) -> str:
        """构建双层身份 system prompt：真实身份 + 安全规则 + 可选的用户人设。"""
        base_prompt = "你的真实身份是群聊的AI助手。"

        rules = self._safety_rules
        if rules:
            base_prompt += " 你必须在严格遵守以下安全规则的前提下与用户交流：\n"
            for i, rule in enumerate(rules, 1):
                base_prompt += f"{i}. {rule}\n"
            base_prompt += "\n"

        persona_text = ""
        if self.persona:
            persona_text = self.persona.get_persona(user_id)

        if persona_text:
            base_prompt += (
                f"此外，当前用户希望你在符合上述规则的前提下"
                f"协助其扮演以下角色：{persona_text}。"
                "请以该角色的语气和知识范围进行回复，但永远不要违反安全规则。"
            )
        else:
            base_prompt += "请保持友好、专业、乐于助人的态度回复用户。"

        return base_prompt.strip()

    async def _handle_ai(self, ctx):
        """核心 AI 对话处理：违规检查、构建消息、调用 LLM、保存记忆。"""
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
        history = await self._get_history(user_id)
        messages = history + [{"role": "user", "content": question}]

        # 发布输入前反思事件
        pre_event = AIPrePromptReflectionEvent(
            user_id=user_id,
            group_id=ctx.group_id,
            message=question,
        )
        await self.event_bus.publish(pre_event)
        if pre_event.supplement:
            messages.insert(0, {"role": "system", "content": pre_event.supplement})

        system_content = self._build_system_prompt(user_id)
        if system_content:
            messages.insert(0, {"role": "system", "content": system_content})

        tools_schema = self.tool.get_tools_schema(only_enabled=True)
        logging.getLogger(__name__).info(
            "可用工具: %s",
            [t["function"]["name"] for t in tools_schema],
        )

        async def tool_executor(name: str, args: dict) -> str:
            """执行工具调用并返回结果，会透传群号以支持媒体发送。"""
            return await self._execute_tool(name, args, ctx.group_id)

        response = await self.llm_factory.chat(
            messages=messages,
            tools=tools_schema if tools_schema else None,
            max_rounds=self.config.get("AI助手.最大工具轮次", 5),
            tool_executor=tool_executor,
        )

        self._add_to_history(
            user_id, {"role": "user", "content": question}
        )
        if response:
            self._add_to_history(
                user_id, {"role": "assistant", "content": response}
            )

        # 发布输出后反思事件
        post_event = AIPostResponseReflectionEvent(
            user_id=user_id,
            group_id=ctx.group_id,
            reply=response,
            original_message=question,
        )
        await self.event_bus.publish(post_event)
        if post_event.warning:
            self._add_to_history(
                user_id, {"role": "system", "content": post_event.warning}
            )

        # 保存磁盘记忆
        await self._save_memory_file(user_id)

        image_urls = re.findall(r'\[IMAGE:(.*?)\]', response)
        for url in image_urls:
            await self.message.send_group(
                ctx.group_id, f"[CQ:image,file={url}]"
            )
            response = response.replace(f"[IMAGE:{url}]", "").strip()

        if response:
            await ctx.reply(response)
        elif not image_urls:
            await ctx.reply("AI 未返回内容")

    async def _execute_tool(
        self, tool_name: str, arguments: dict, group_id: int
    ) -> str:
        """执行工具并返回结果字符串。对于媒体类工具，会直接发送媒体并清理标签。"""
        try:
            result = await self.tool.execute(
                tool_name, arguments,
                context={"user_id": 0, "group_id": group_id}
            )
        except Exception as e:
            logging.getLogger(__name__).error(
                "工具执行失败 %s: %s", tool_name, e
            )
            return f"工具调用失败: {str(e)}"

        if tool_name == "generate_image":
            urls = re.findall(r'\[IMAGE:(.*?)\]', result)
            for url in urls:
                try:
                    await self.message.send_group(
                        group_id, f"[CQ:image,file={url}]"
                    )
                except Exception as e:
                    logging.getLogger(__name__).error(
                        "发送图片失败: %s", e
                    )
                result = result.replace(f"[IMAGE:{url}]", "").strip()

        return result

    async def on_group_message(self, event: GroupMessageEvent):
        """处理群消息事件，执行内容审核。"""
        self.auditor.process_message(
            event.user_id, event.group_id, event.message
        )

    # ---------- 长时记忆管理 ----------

    def _memory_file_path(self, user_id: int) -> str:
        """获取用户记忆文件路径。"""
        return os.path.join(self._memory_dir, f"{user_id}.json")

    async def _load_memory_from_disk(self, user_id: int) -> List[Dict]:
        """从磁盘加载用户记忆。"""
        path = self._memory_file_path(user_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data[-self.max_memory * 2:]
        except Exception:
            return []
        return []

    async def _save_memory_file(self, user_id: int):
        """保存用户记忆到磁盘。"""
        path = self._memory_file_path(user_id)
        history = self.conversations.get(user_id, [])
        if not history:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.getLogger(__name__).error("保存记忆文件失败: %s", e)

    def _cleanup_expired(self, user_id: int):
        """清除长时间未活动的会话历史（内存）。"""
        now = time.time()
        last = self.conversation_last_active.get(user_id, 0)
        if last and (now - last) > self.conversation_max_age:
            self.conversations.pop(user_id, None)
            self.conversation_last_active.pop(user_id, None)

    async def _get_history(self, user_id: int) -> List[Dict]:
        """获取用户最近的对话历史，优先内存，无则从磁盘加载。"""
        now = time.time()
        self.conversation_last_active[user_id] = now
        if user_id not in self.conversations:
            loaded = await self._load_memory_from_disk(user_id)
            if loaded:
                self.conversations[user_id] = loaded
        hist = self.conversations.get(user_id, [])
        return hist[-self.max_memory:]

    def _add_to_history(self, user_id: int, msg: Dict):
        """向用户会话历史添加一条消息，并限制总条数。"""
        self.conversation_last_active[user_id] = time.time()
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        self.conversations[user_id].append(msg)
        max_total = self.max_memory * 2
        if len(self.conversations[user_id]) > max_total:
            self.conversations[user_id] = self.conversations[user_id][-max_total:]

    # ---------- 管理员记忆管理命令 ----------

    async def _cmd_del_memory(self, ctx):
        """删除指定用户的长期记忆。"""
        if not ctx.args:
            await ctx.reply("用法：.delmemory <QQ号>")
            return
        try:
            target_qq = int(ctx.args[0])
        except ValueError:
            await ctx.reply("QQ号必须是整数")
            return

        self.conversations.pop(target_qq, None)
        self.conversation_last_active.pop(target_qq, None)
        path = self._memory_file_path(target_qq)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        await ctx.reply(f"已清除用户 {target_qq} 的长时记忆。")

    async def _cmd_clear_memory(self, ctx):
        """清除所有用户的长时记忆。"""
        self.conversations.clear()
        self.conversation_last_active.clear()
        try:
            for filename in os.listdir(self._memory_dir):
                file_path = os.path.join(self._memory_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        except Exception as e:
            logging.getLogger(__name__).error("清除记忆文件失败: %s", e)
        await ctx.reply("已清除所有用户的长期记忆。")
