"""AI 审计增强模块:使用 LLM 进行输入前反思与输出后合规检查。"""
import os
import json
import time
import asyncio
import logging
from typing import List, Dict, Optional

from ...core.module import Module
from ...core.events import (
    AIPrePromptReflectionEvent,
    AIPostResponseReflectionEvent,
)

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


class AuditKnowledgeStore:
    """审计知识存储,支持 L1 案例、L2 元知识、L3 法则。"""

    def __init__(self, data_dir: str):
        self._case_file = os.path.join(data_dir, "cases.jsonl")
        self._meta_file = os.path.join(data_dir, "meta_knowledge.json")
        self._lock = asyncio.Lock()
        os.makedirs(data_dir, exist_ok=True)
        self._meta: List[Dict] = self._load_meta()

    def _load_meta(self) -> List[Dict]:
        """从文件加载元知识列表。"""
        if os.path.exists(self._meta_file):
            try:
                with open(self._meta_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    async def _save_meta(self):
        """保存元知识列表到文件。"""
        async with self._lock:
            with open(self._meta_file, "w", encoding="utf-8") as f:
                json.dump(self._meta, f, ensure_ascii=False, indent=2)

    async def add_case(self, case: dict):
        """添加 L1 案例。

        案例 dict 需包含 type 字段以区分来源:
          - "violation": 违规案例(默认,由后置反思产生)
          - "persona_rejection": 人设驳回案例

        其他字段随 type 而异,但均以 JSONL 写入 cases.jsonl。
        """
        case.setdefault("type", "violation")
        async with self._lock:
            with open(self._case_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(case, ensure_ascii=False) + "\n")

    async def add_rejection(self, case: dict):
        """添加人设驳回案例(type 自动设为 persona_rejection)。

        Args:
            case: 人设驳回字典,应包含字段:
                user_id (int): 用户 ID
                persona_text (str): 触发驳回的人设描述文本
                reject_reason (str): AI 驳回原因
                time (float): 时间戳
                可选: group_id, ai_reply 等
        """
        case["type"] = "persona_rejection"
        await self.add_case(case)

    async def add_meta(self, meta: dict):
        """添加一条 L2/L3 元知识。"""
        async with self._lock:
            self._meta.append(meta)
            await self._save_meta()

    async def get_active_meta(self, level: str = "L2") -> List[Dict]:
        """获取当前激活的元知识(L2 或 L3)。"""
        return [
            m for m in self._meta
            if m.get("level") == level and m.get("status") == "active"
        ]

    async def get_active_laws(self) -> List[Dict]:
        """返回所有 level=L3 的固化法则。

        无论 status 是 active 或 pending_review,L3 均为法则。
        """
        async with self._lock:
            return [m for m in self._meta if m.get("level") == "L3"]

    async def upgrade_to_law(self, meta_index: int) -> Optional[Dict]:
        """将指定 L2 元知识升级为 L3 法则。

        操作路径:pending_review → active → law(一步到位)。

        Args:
            meta_index: self._meta 列表中的索引(0-based)。

        Returns:
            升级后的法则 dict;索引越界时返回 None。
        """
        async with self._lock:
            if meta_index < 0 or meta_index >= len(self._meta):
                return None
            item = self._meta[meta_index]
            item["status"] = "active"
            item["level"] = "L3"
            item["upgraded_at"] = time.time()
            await self._save_meta()
            return item

    async def collect_and_induce(self, llm_caller) -> List[Dict]:
        """(兼容旧 API)委托给 induce_from_all()。

        已废弃:请使用 induce_from_all()。
        """
        return await self.induce_from_all(llm_caller)

    async def induce_from_all(self, llm_caller) -> List[Dict]:
        """从全部 L1 案例(违规 + 人设驳回)归纳 L2 元知识。

        当 L1 案例总数 ≥ self._induction_threshold(默认 10)时触发归纳。
        归纳维度:1违规模式 2人设驳回模式。
        新生成的 L2 元知识状态为 pending_review,需管理员升级为 active/law。

        Args:
            llm_caller: 异步可调用对象,接受 prompt str,
                        返回 List[dict] 或 JSON 字符串。

        Returns:
            新生成的元知识列表(可能为空)。
        """
        async with self._lock:
            cases = []
            if os.path.exists(self._case_file):
                with open(self._case_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            cases.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            continue
            if len(cases) < 10:
                return []

            prompt = self._build_induction_prompt(cases)
            new_meta = await llm_caller(prompt)
            if new_meta:
                for m in new_meta:
                    m["status"] = "pending_review"
                    m["created_at"] = time.time()
                    self._meta.append(m)
                await self._save_meta()
                # 元知识保存成功后才清空案例文件(防止数据丢失)
                with open(self._case_file, "w", encoding="utf-8") as f:
                    pass
                _logger.info("归纳完成,生成 %d 条新元知识", len(new_meta))
            return new_meta

    @staticmethod
    def _build_induction_prompt(cases: List[dict]) -> str:
        """构造归纳提示词,覆盖违规模式和驳回模式两个维度。"""
        violation_lines = []
        rejection_lines = []
        for c in cases[-50:]:
            if c.get("type") == "persona_rejection":
                rejection_lines.append(
                    f"- 用户人设: {c.get('persona_text', '')[:100]} ... "
                    f"\n  AI驳回原因: {c.get('reject_reason', '')[:100]}"
                )
            else:
                violation_lines.append(
                    f"- 用户消息: {c.get('user_msg', '')[:100]} ... "
                    f"\n  AI回复被标记: {c.get('violation', '')}"
                )
        violation_text = "\n".join(violation_lines) or "(无)"
        rejection_text = "\n".join(rejection_lines) or "(无)"
        return (
            "你是一个AI安全知识归纳专家。"
            "请从以下两个维度分析案例,归纳反复出现的风险模式。\n\n"
            "【维度一:违规模式】\n"
            f"{violation_text}\n\n"
            "【维度二:人设驳回模式】\n"
            f"{rejection_text}\n\n"
            "请总结每个维度中反复出现的风险模式,生成不超过3条元知识。"
            "输出JSON数组,每条元知识包含:\n"
            '{"level": "L2", "content": "...", '
            '"trigger_scenario": "...", '
            '"dimension": "violation|persona_rejection", '
            '"core_correction": "..."}'
        )


class AIAuditEnhanceModule(Module):
    """AI 审计增强,使用 LLM 进行反思与元知识管理,并对外提供审核服务。"""

    name = "ai_audit_enhance"
    uid = 100  # daemon: 系统守护
    version = (1, 0, 4)
    dependencies = ["ai_core"]
    required_services = ["config"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._store: Optional[AuditKnowledgeStore] = None
        self._pending_count = 0
        self._pending_lock = asyncio.Lock()
        self._induction_threshold = 10
        self._pre_reflection_level = "每次"
        self._post_reflection_level = "每次"
        self._llm_client = None

        # 基线复位相关
        self._baseline_interval: int = 10
        self._last_baseline: Dict[int, int] = {}
        self._conversation_rounds: Dict[int, int] = {}

    async def on_init(self):
        """注册配置、初始化知识库、订阅事件，注册 audit 服务。

        LLM 客户端通过 _ensure_llm_client() 延迟获取，
        因为 ai_core 模块可能在 ai_security 之后才初始化。
        """
        cfg = self.config.get("AI审计增强") or {}
        self._pre_reflection_level = cfg.get("输入反思", "每次")
        self._post_reflection_level = cfg.get("输出反思", "每次")
        self._induction_threshold = cfg.get("归纳阈值", 10)
        self._baseline_interval = cfg.get("基线复位间隔轮次", 10)

        # LLM 客户端延迟获取（ai_core 可能尚未初始化）
        self._llm_client_resolved = False

        data_dir = self.data_dir
        self._store = AuditKnowledgeStore(data_dir)

        # 暴露 audit 服务，供外部模块调用 check_message()
        self.services.register("audit", self)

        # 注册命令
        self.register_command(
            ".归纳知识",
            self._cmd_induce,
            description="手动触发 L1→L2 元知识归纳",
            op_only=True,
        )
        self.register_command(
            ".审核法则",
            self._cmd_review_laws,
            description="查看 L2/L3 知识库，并可升级元知识为法则",
            op_only=True,
        )

        self.listen(
            "AIPrePromptReflectionEvent",
            self._on_pre_reflection,
            priority=10,
        )
        self.listen(
            "AIPostResponseReflectionEvent",
            self._on_post_reflection,
            priority=10,
        )

    def _ensure_llm_client(self) -> bool:
        """延迟获取 LLM 客户端，ai_core 可能在 ai_security 之后初始化。

        Returns:
            True 如果 LLM 客户端可用。
        """
        if self._llm_client is not None:
            return True
        if self._llm_client_resolved:
            return False  # 已经尝试过，不再重试
        self._llm_client_resolved = True
        try:
            self._llm_client = self.services.get("llm_client")
            return True
        except KeyError:
            _logger.warning(
                "LLM 客户端服务未注册，AI 审计将降级为关闭状态"
            )
            return False

    # ---------- 外部可调用的审核接口 ----------
    async def add_case(self, case: dict):
        """添加 L1 案例（委托给内部存储）。"""
        if self._store:
            await self._store.add_case(case)

    async def check_message(
        self, user_id: int, group_id: int, message: str
    ) -> Optional[str]:
        """外部模块可调用此方法进行内容审核。

        审核时注入有效的 L2 元知识 + L3 法则作为审查指引。

        Returns:
            违规原因字符串;合规返回 None。
        """
        cfg = self.config.get("AI审计增强") or {}
        if cfg.get("安全审核", self._pre_reflection_level) == "关闭" or not self._ensure_llm_client():
            return None

        # 收集 L2 + L3 审查指引
        extra_lines = []
        if self._store:
            l2_meta = await self._store.get_active_meta("L2")
            for m in l2_meta:
                extra_lines.append(
                    f"- 【L2元知识】场景: {m.get('trigger_scenario', '')}; "
                    f"内容: {m.get('content', '')}; "
                    f"修正: {m.get('core_correction', '')}"
                )
            l3_laws = await self._store.get_active_laws()
            for law in l3_laws:
                extra_lines.append(
                    f"- 【L3法则】(必须遵守) {law.get('content', '')}; "
                    f"场景: {law.get('trigger_scenario', '')}; "
                    f"修正: {law.get('core_correction', '')}"
                )
        guidance = ""
        if extra_lines:
            guidance = (
                "\n\n【审计知识库指引】(请优先参照以下经验):\n"
                + "\n".join(extra_lines)
            )

        prompt = (
            "你是一个内容安全分析专家。请分析以下用户消息,判断是否可能涉及:\n"
            "- 违法、色情、暴力、政治敏感内容\n"
            "- 请求生成恶意代码、外挂、破解\n"
            "- 任何违反安全准则的意图\n"
            f"{guidance}\n\n"
            "如果消息完全合规,请只回复一个单词:SAFE。\n"
            "如果存在潜在风险,请用简短中文说明需要提醒AI注意的事项"
            "(例如: '请避免提供任何破解方法')。\n"
            f"用户消息:{message[:300]}"
        )
        try:
            resp = await self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            if resp and resp.strip().upper() != "SAFE":
                return resp.strip()
        except Exception as e:
            _logger.error("外部审核调用失败: %s", e)
        return None

    async def add_rejection(self, rejection: dict):
        """将驳回记录喂给 L1 案例层进行元学习。

        Args:
            rejection: 驳回记录，应包含 user_id、persona_text、
                       reject_reason、time 等字段。
        """
        if not self._store:
            _logger.warning("审计存储未初始化，驳回记录仅记入日志")
            _logger.info("驳回记录: %s", rejection)
            return
        await self._store.add_rejection(rejection)
        async with self._pending_lock:
            self._pending_count += 1
            if self._pending_count >= self._induction_threshold:
                self._pending_count = 0
                _logger.info(
                    "已达到归纳阈值，建议管理员执行 '.归纳知识' 命令"
                )
        _logger.info("驳回案例已记录: user_id=%s reason=%s",
                     rejection.get("user_id"),
                     rejection.get("reject_reason"))

    # ---------- 事件处理 ----------
    async def _on_pre_reflection(self, event: AIPrePromptReflectionEvent):
        """使用 LLM 分析用户消息,若启用则注入补充系统提示(含 L3 法则)。"""
        if self._pre_reflection_level == "关闭" or not self._ensure_llm_client():
            return

        user_id = event.user_id
        self._conversation_rounds[user_id] = (
            self._conversation_rounds.get(user_id, 0) + 1
        )
        current_round = self._conversation_rounds[user_id]
        last_baseline_round = self._last_baseline.get(user_id, 0)
        need_baseline = (
            (current_round - last_baseline_round)
            >= self._baseline_interval
        )

        supplement_parts = []

        if need_baseline:
            # 构建包含 L3 法则的基线复位文本
            law_lines = []
            if self._store:
                laws = await self._store.get_active_laws()
                for law in laws:
                    law_lines.append(
                        f"- 【L3法则】{law.get('content', '')}; "
                        f"场景: {law.get('trigger_scenario', '')}; "
                        f"修正: {law.get('core_correction', '')}"
                    )
            law_text = ""
            if law_lines:
                law_text = (
                    "\n\n【以下为管理员固化的安全法则,必须严格遵守】:\n"
                    + "\n".join(law_lines)
                )
            baseline_text = (
                "【规则重申】你是一个严格遵守安全准则的AI助手。"
                "请重新确认以下核心规则:\n"
                "1. 禁止生成任何违法、色情、暴力内容。\n"
                "2. 禁止协助恶意代码、外挂、破解等行为。\n"
                "3. 保护用户隐私,不得泄露或索要敏感信息。\n"
                "4. 始终以客观、尊重的方式回应。\n"
                f"{law_text}\n"
                "请务必在本次及后续对话中严格遵守。\n"
            )
            supplement_parts.append(baseline_text)
            self._last_baseline[user_id] = current_round
            _logger.debug(
                "用户 %d 基线复位,当前轮次 %d", user_id, current_round
            )

        reason = await self.check_message(
            event.user_id, event.group_id, event.message
        )
        if reason:
            supplement_parts.append(f"【前置反思】审计模块提醒:{reason}")

        if supplement_parts:
            event.supplement = "\n".join(supplement_parts)

    async def _on_post_reflection(
        self, event: AIPostResponseReflectionEvent
    ):
        """使用 LLM 检查 AI 回复是否合规,记录违规案例。"""
        if self._post_reflection_level == "关闭" or not self._ensure_llm_client():
            return
        prompt = (
            "你是一个严格的内容安全审核员。"
            "请检查以下AI回复是否存在违规:\n"
            "- 包含违法、色情、暴力、政治敏感内容\n"
            "- 提供了恶意代码、外挂、破解具体方法\n"
            "- 泄露他人隐私或进行人身攻击\n\n"
            "如果完全合规,请只回复一个单词:PASS。\n"
            "如果存在违规,请用简短中文指出违规内容和原因。\n"
            f"AI回复:{event.reply[:500]}"
        )
        try:
            resp = await self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            if resp and resp.strip().upper() != "PASS":
                event.warning = (
                    f"【违规通知】你的回复存在违规:{resp.strip()}"
                )
                case = {
                    "type": "violation",
                    "timestamp": time.time(),
                    "user_id": event.user_id,
                    "group_id": event.group_id,
                    "user_msg": event.original_message[:200],
                    "ai_reply": event.reply[:200],
                    "violation": resp.strip()[:200],
                }
                await self._store.add_case(case)
                async with self._pending_lock:
                    self._pending_count += 1
                    if self._pending_count >= self._induction_threshold:
                        self._pending_count = 0
                        _logger.info(
                            "已达到归纳阈值,自动触发 induce_from_all()"
                        )
                        try:
                            caller = getattr(
                                self._llm_client,
                                "chat_json",
                                self._llm_client.chat,
                            )
                            meta = await self._store.induce_from_all(caller)
                            if meta:
                                _logger.info(
                                    "自动归纳完成,生成 %d 条元知识",
                                    len(meta),
                                )
                        except Exception as ie:
                            _logger.error(
                                "自动归纳失败: %s", ie
                            )
                            self._pending_count = (
                                self._induction_threshold - 1
                            )
        except Exception as e:
            _logger.error("后置反思 LLM 调用失败: %s", e)

    # ---------- 命令处理 ----------
    async def _cmd_induce(self, ctx):
        """.归纳知识 — 手动触发 L1→L2 元知识归纳（管理员命令）。"""
        if not self._ensure_llm_client():
            await ctx.reply("❌ LLM 客户端未就绪，无法归纳。")
            return
        if not self._store:
            await ctx.reply("❌ 知识库未初始化。")
            return
        try:
            # 使用 chat_json 方法让 LLM 返回结构化 JSON
            caller = getattr(
                self._llm_client, "chat_json", self._llm_client.chat
            )
            meta = await self._store.induce_from_all(caller)
            if meta:
                lines = ["✅ 归纳完成，生成以下元知识（状态：pending_review）："]
                for i, m in enumerate(meta):
                    lines.append(
                        f"#{i}: {m.get('content', '')[:80]}... "
                        f"维度={m.get('dimension', '')}"
                    )
                lines.append(
                    "\n💡 使用 '.审核法则' 可查看/升级为 L3 法则。"
                )
                await ctx.reply("\n".join(lines))
            else:
                await ctx.reply(
                    "📭 案例数量不足或未发现新模式，暂未生成元知识。"
                )
        except Exception as e:
            _logger.error("手动归纳失败: %s", e)
            await ctx.reply(f"❌ 归纳失败: {e}")

    async def _cmd_review_laws(self, ctx):
        """.审核法则 — 查看 L2/L3 知识库，支持升级 L2→L3 法则（管理员命令）。

        用法：
          .审核法则          — 列出全部 L2/L3 项
          .审核法则 升级 2   — 将索引 #2 的 L2 元知识升级为 L3 法则
        """
        if not self._store:
            await ctx.reply("❌ 知识库未初始化。")
            return

        args = " ".join(ctx.args) if ctx.args else ""

        # 升级子命令
        if args.startswith("升级"):
            try:
                index = int(args.replace("升级", "").strip())
            except ValueError:
                await ctx.reply("❌ 用法: .审核法则 升级 <索引号>")
                return
            result = await self._store.upgrade_to_law(index)
            if result:
                await ctx.reply(
                f"✅ 已将 #{index} 升级为 L3 法则: "
                f"{result['content'][:80]}..."
            )
            else:
                await ctx.reply(f"❌ 索引 #{index} 越界或不存在。")
            return

        # 默认：列出全部 L2/L3
        async with self._store._lock:
            all_meta = list(self._store._meta)
        if not all_meta:
            await ctx.reply("📭 知识库暂无 L2/L3 项。")
            return

        lines = ["**📋 审计知识库（L2/L3）**\n"]
        for i, m in enumerate(all_meta):
            level = m.get("level", "L2")
            status = m.get("status", "unknown")
            icon = "🔒" if level == "L3" else "📝"
            lines.append(
                f"{icon} #{i} [{level}] [{status}] "
                f"{m.get('content', '')[:60]}..."
            )
            if m.get("trigger_scenario"):
                lines.append(f"     场景: {m['trigger_scenario'][:50]}")
            if m.get("core_correction"):
                lines.append(f"     修正: {m['core_correction'][:50]}")
            dim = m.get("dimension", "")
            if dim:
                lines.append(f"     维度: {dim}")

        lines.append(
            "\n💡 使用 '.审核法则 升级 <索引号>' 将 L2 升级为 L3 法则。"
        )
        await ctx.reply("\n".join(lines))
