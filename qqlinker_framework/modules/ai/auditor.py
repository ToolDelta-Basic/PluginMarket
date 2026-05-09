# modules/ai/auditor.py
import re
import time
import logging
from typing import Dict, List, Tuple

class Auditor:
    def __init__(self, ai_module):
        self.ai = ai_module
        self.config = ai_module.config
        self.patterns: List[re.Pattern] = []
        self.violation_counts: Dict[int, int] = {}      # user_id -> 违规次数
        self._compile_patterns()

    def _compile_patterns(self):
        words = self.config.get("ai_core.audit.bad_words_patterns", [])
        self.patterns = [re.compile(re.escape(w), re.IGNORECASE) for w in words]

    def check_violation(self, user_id: int, text: str) -> bool:
        """检查是否违规，返回 True 表示违规"""
        for pattern in self.patterns:
            if pattern.search(text):
                self._record_violation(user_id)
                return True
        return False

    def _record_violation(self, user_id: int):
        count = self.violation_counts.get(user_id, 0) + 1
        self.violation_counts[user_id] = count
        limit = self.config.get("ai_core.audit.violation_limit", 3)
        if count >= limit:
            self._apply_action(user_id)
            self.violation_counts[user_id] = 0  # 重置计数，或保留记录

    def _apply_action(self, user_id: int):
        action = self.config.get("ai_core.audit.action", "mute")
        if action == "mute":
            # 需要 OneBot 支持，暂时仅记录
            logging.getLogger(__name__).warning("用户 %d 违规次数达到上限，请求禁言", user_id)
            # self.ai.adapter.mute_user(group_id, user_id, 600)  # 未来实现
        elif action == "kick":
            logging.getLogger(__name__).warning("用户 %d 违规次数达到上限，请求踢出", user_id)
        # 可以扩展 ban 等

    def process_message(self, user_id: int, group_id: int, message: str):
        """处理群消息，违规则记录并可能自动处理"""
        if self.check_violation(user_id, message):
            # 发送警告
            self.ai.message.send_group(group_id, f"[CQ:at,qq={user_id}] 请注意文明用语")
            # 违规计数已在 check_violation 中处理