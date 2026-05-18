"""AI 审计增强模块：使用 LLM 进行输入前反思与输出后合规检查。"""
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
    """审计知识存储，支持 L1 案例、L2 元知识、L3 法则。"""

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
        """添加 L1 案例。"""
        async with self._lock:
            with open(self._case_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(case, ensure_ascii=False) + "\n")

    async def add_meta(self, meta: dict):
        """添加一条 L2/L3 元知识。"""
        async with self._lock:
            self._meta.append(meta)
            await self._save_meta()

    async def get_active_meta(self, level: str = "L2") -> List[Dict]:
        """获取当前激活的元知识（L2 或 L3）。"""
        return [
            m for m in self._meta
            if m.get("level") == level and m.get("status") == "active"
        ]

    async def collect_and_induce(self, llm_caller) -> List[Dict]:
        """当案例积累 ≥ 10 时触发归纳，生成新的 L2 元知识。"""
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
                # 元知识保存成功后才清空案例文件（防止数据丢失）
                with open(self._case_file, "w", encoding="utf-8") as f:
                    pass
                _logger.info("归纳完成，生成 %d 条新元知识", len(new_meta))
            return new_meta

    @staticmethod
    def _build_induction_prompt(cases: List[dict]) -> str:
        """构造归纳提示词。"""
        lines = []
        for c in cases[-50:]:
            lines.append(
                f"- 用户消息: {c['user_msg'][:100]} ... "
                f"\n  AI回复被标记: {c.get('violation', '')}"
            )
        cases_text = "\n".join(lines)
        return (
            "你是一个AI安全知识归纳专家。"
            "以下是最近发生的AI交互中的违规案例：\n"
            f"{cases_text}\n"
            "请总结其中反复出现的风险模式，生成不超过3条元知识。"
            "输出JSON数组，每条元知识包含:\n"
            '{"level": "L2", "content": "...", '
            '"trigger_scenario": "...", '
            '"core_correction": "..."}'
        )


class AIAuditEnhanceModule(Module):
    """AI 审计增强，使用 LLM 进行反思与元知识管理，并对外提供审核服务。"""

    name = "ai_audit_enhance"
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
        """注册配置、获取 LLM 客户端、初始化知识库、订阅事件，注册 audit 服务。"""
        self.config.register_section("AI审计增强", {
            "输入反思": "每次",
            "输出反思": "每次",
            "归纳阈值": 10,
            "基线复位间隔轮次": 10,
        })
        cfg = self.config.get("AI审计增强")
        self._pre_reflection_level = cfg.get("输入反思", "每次")
        self._post_reflection_level = cfg.get("输出反思", "每次")
        self._induction_threshold = cfg.get("归纳阈值", 10)
        self._baseline_interval = cfg.get("基线复位间隔轮次", 10)

        try:
            self._llm_client = self.services.get("llm_client")
        except KeyError:
            _logger.warning(
                "LLM 客户端服务未注册，AI 审计将降级为关闭状态"
            )
            self._pre_reflection_level = "关闭"
            self._post_reflection_level = "关闭"

        data_dir = self.get_data_dir()
        self._store = AuditKnowledgeStore(data_dir)

        self.services.register("audit", self)

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

    # ---------- 外部可调用的审核接口 ----------
    async def check_message(
        self, user_id: int, group_id: int, message: str
    ) -> Optional[str]:
        """外部模块可调用此方法进行内容审核。

        Returns:
            违规原因字符串；合规返回 None。
        """
        if self._pre_reflection_level == "关闭" or not self._llm_client:
            return None
        prompt = (
            "你是一个内容安全分析专家。请分析以下用户消息，判断是否可能涉及：\n"
            "- 违法、色情、暴力、政治敏感内容\n"
            "- 请求生成恶意代码、外挂、破解\n"
            "- 任何违反安全准则的意图\n\n"
            "如果消息完全合规，请只回复一个单词：SAFE。\n"
            "如果存在潜在风险，请用简短中文说明需要提醒AI注意的事项"
            "（例如：“请避免提供任何破解方法”）。\n"
            f"用户消息：{message[:300]}"
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

    # ---------- 事件处理 ----------
    async def _on_pre_reflection(self, event: AIPrePromptReflectionEvent):
        """使用 LLM 分析用户消息，若启用则注入补充系统提示。"""
        if self._pre_reflection_level == "关闭" or not self._llm_client:
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
            baseline_text = (
                "【规则重申】你是一个严格遵守安全准则的AI助手。"
                "请重新确认以下核心规则：\n"
                "1. 禁止生成任何违法、色情、暴力内容。\n"
                "2. 禁止协助恶意代码、外挂、破解等行为。\n"
                "3. 保护用户隐私，不得泄露或索要敏感信息。\n"
                "4. 始终以客观、尊重的方式回应。\n"
                "请务必在本次及后续对话中严格遵守。\n"
            )
            supplement_parts.append(baseline_text)
            self._last_baseline[user_id] = current_round
            _logger.debug(
                "用户 %d 基线复位，当前轮次 %d", user_id, current_round
            )

        reason = await self.check_message(
            event.user_id, event.group_id, event.message
        )
        if reason:
            supplement_parts.append(f"【前置反思】审计模块提醒：{reason}")

        if supplement_parts:
            event.supplement = "\n".join(supplement_parts)

    async def _on_post_reflection(
        self, event: AIPostResponseReflectionEvent
    ):
        """使用 LLM 检查 AI 回复是否合规，记录违规案例。"""
        if self._post_reflection_level == "关闭" or not self._llm_client:
            return
        prompt = (
            "你是一个严格的内容安全审核员。"
            "请检查以下AI回复是否存在违规：\n"
            "- 包含违法、色情、暴力、政治敏感内容\n"
            "- 提供了恶意代码、外挂、破解具体方法\n"
            "- 泄露他人隐私或进行人身攻击\n\n"
            "如果完全合规，请只回复一个单词：PASS。\n"
            "如果存在违规，请用简短中文指出违规内容和原因。\n"
            f"AI回复：{event.reply[:500]}"
        )
        try:
            resp = await self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            if resp and resp.strip().upper() != "PASS":
                event.warning = (
                    f"【违规通知】你的回复存在违规：{resp.strip()}"
                )
                case = {
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
                            "已达到归纳阈值，建议管理员执行 '.归纳知识' 命令"
                        )
        except Exception as e:
            _logger.error("后置反思 LLM 调用失败: %s", e)
