"""AI 审计增强模块：提供输入前反思、输出后合规检查与元知识管理。"""
import os
import json
import time
import asyncio
import logging
from typing import List, Dict, Optional, Any

from ..core.module import Module
from ..core.events import AIPrePromptReflectionEvent, AIPostResponseReflectionEvent

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
                with open(self._case_file, "w", encoding="utf-8") as f:
                    pass
                for m in new_meta:
                    m["status"] = "pending_review"
                    m["created_at"] = time.time()
                    self._meta.append(m)
                await self._save_meta()
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
    """AI 审计增强，提供反思与元知识管理。"""

    name = "ai_audit_enhance"
    version = (1, 0, 0)
    required_services = ["config", "message"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._store: Optional[AuditKnowledgeStore] = None
        self._pending_count = 0
        self._induction_threshold = 10
        self._pre_reflection_enabled = True
        self._post_reflection_enabled = True

    async def on_init(self):
        """注册配置、初始化知识库、订阅反思事件。"""
        self.config.register_section("AI审计增强", {
            "输入反思": "每次",
            "输出反思": "每次",
            "归纳阈值": 10,
        })
        cfg = self.config.get("AI审计增强")
        self._pre_reflection_enabled = cfg.get("输入反思", "每次") == "每次"
        self._post_reflection_enabled = cfg.get("输出反思", "每次") == "每次"
        self._induction_threshold = cfg.get("归纳阈值", 10)

        data_dir = self.get_data_dir()
        self._store = AuditKnowledgeStore(data_dir)

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

    async def _on_pre_reflection(self, event: AIPrePromptReflectionEvent):
        """输入前反思：检查消息是否隐含风险，返回补充提示。"""
        if not self._pre_reflection_enabled:
            return
        keywords = ["攻击", "破解", "外挂"]
        found = [kw for kw in keywords if kw in event.message]
        if found:
            event.supplement = (
                f"【风险提醒】消息中包含关键词：{', '.join(found)}，"
                "回复时请注意避免提供违规帮助。"
            )

    async def _on_post_reflection(self, event: AIPostResponseReflectionEvent):
        """输出后反思：检查AI回复是否合规，记录案例并可能触发归纳。"""
        if not self._post_reflection_enabled:
            return
        sensitive = ["外挂", "破解教程"]
        violations = [kw for kw in sensitive if kw in event.reply]
        if violations:
            event.warning = (
                f"【违规通知】你的回复中包含了 {', '.join(violations)}，"
                "违反了安全规则。"
            )
            case = {
                "timestamp": time.time(),
                "user_id": event.user_id,
                "group_id": event.group_id,
                "user_msg": event.original_message[:200],
                "ai_reply": event.reply[:200],
                "violation": ", ".join(violations),
            }
            await self._store.add_case(case)
            self._pending_count += 1

            if self._pending_count >= self._induction_threshold:
                self._pending_count = 0
                _logger.info(
                    "已达到归纳阈值，建议管理员执行 '.归纳知识' 命令"
                )
