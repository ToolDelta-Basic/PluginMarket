"""审核拦截器：基于正则匹配违规词，自动处理违规用户。"""
import re
import logging
from typing import Dict, List


class Auditor:
    """审核拦截器，检测消息违规并自动执行处理动作。"""

    def __init__(self, ai_module):
        self.ai = ai_module
        self.config = ai_module.config
        self.patterns: List[re.Pattern] = []
        self.violation_counts: Dict[int, int] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        """从配置编译正则表达式列表。"""
        words = self.config.get("AI助手.审核.违规词模式", [])
        self.patterns = [
            re.compile(re.escape(w), re.IGNORECASE) for w in words
        ]

    def check_violation(self, user_id: int, text: str) -> bool:
        """检查文本是否包含违规词，并自动记录。"""
        for pattern in self.patterns:
            if pattern.search(text):
                self._record_violation(user_id)
                return True
        return False

    def _record_violation(self, user_id: int):
        """记录一次违规并检查是否达到处理阈值。"""
        count = self.violation_counts.get(user_id, 0) + 1
        self.violation_counts[user_id] = count
        limit = self.config.get("AI助手.审核.违规次数上限", 3)
        if count >= limit:
            self._apply_action(user_id)
            self.violation_counts[user_id] = 0

    def _apply_action(self, user_id: int):
        """执行配置中设定的违规处理动作（禁言、踢出等）。"""
        action = self.config.get("AI助手.审核.处理动作", "禁言")
        if action == "禁言":
            logging.getLogger(__name__).warning(
                "用户 %d 违规次数达到上限，请求禁言", user_id
            )
        elif action == "踢出":
            logging.getLogger(__name__).warning(
                "用户 %d 违规次数达到上限，请求踢出", user_id
            )

    def process_message(
        self, user_id: int, group_id: int, message: str
    ):
        """处理群消息，违规时发送警告并记录。"""
        if self.check_violation(user_id, message):
            self.ai.message.send_group(
                group_id,
                f"[CQ:at,qq={user_id}] 请注意文明用语"
            )
