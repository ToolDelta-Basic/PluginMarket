from typing import List, Optional, Tuple
from guild.config import Config


class ItemNameMatcher:
    """智能物品名称匹配器"""

    def __init__(self):
        self.chinese_names = Config.CHINESE_ITEM_NAMES
        self.aliases = Config.ITEM_ALIASES
        # 创建反向映射：物品ID -> 中文名称
        self.id_to_chinese = {v: k for k, v in self.chinese_names.items()}

    def normalize_input(self, input_text: str) -> str:
        """标准化输入文本"""
        if not input_text:
            return ""
        return input_text.strip().lower()

    def find_item_id(self, user_input: str) -> Optional[str]:
        """根据用户输入查找物品ID"""
        if not user_input:
            return None

        user_input = user_input.strip()

        # 1. 直接匹配物品ID（向后兼容）
        if user_input.startswith("minecraft:"):
            return user_input if user_input in self.id_to_chinese else None

        # 2. 直接匹配中文名称
        if user_input in self.chinese_names:
            return self.chinese_names[user_input]

        # 3. 匹配别名
        if user_input in self.aliases:
            chinese_name = self.aliases[user_input]
            return self.chinese_names.get(chinese_name)

        # 4. 模糊匹配（部分匹配）
        matches = self.fuzzy_match(user_input)
        if matches:
            return self.chinese_names[matches[0]]

        return None

    def fuzzy_match(self, user_input: str, max_results: int = 5) -> List[str]:
        """模糊匹配，返回可能的中文名称列表"""
        if not user_input:
            return []

        user_input = user_input.lower()
        matches = []

        # 搜索中文名称
        for chinese_name in self.chinese_names.keys():
            if user_input in chinese_name.lower():
                matches.append((chinese_name, self._calculate_match_score(user_input, chinese_name)))

        # 搜索别名
        for alias, chinese_name in self.aliases.items():
            if user_input in alias.lower() and chinese_name not in [m[0] for m in matches]:
                matches.append((chinese_name, self._calculate_match_score(user_input, alias)))

        # 按匹配度排序
        matches.sort(key=lambda x: x[1], reverse=True)

        return [match[0] for match in matches[:max_results]]

    def _calculate_match_score(self, user_input: str, target: str) -> float:
        """计算匹配分数"""
        user_input = user_input.lower()
        target = target.lower()

        # 完全匹配得分最高
        if user_input == target:
            return 1.0

        # 开头匹配得分较高
        if target.startswith(user_input):
            return 0.8 + (len(user_input) / len(target)) * 0.2

        # 包含匹配
        if user_input in target:
            return 0.6 + (len(user_input) / len(target)) * 0.2

        # 字符相似度
        return self._string_similarity(user_input, target) * 0.4

    def _string_similarity(self, s1: str, s2: str) -> float:
        """计算字符串相似度"""
        if not s1 or not s2:
            return 0.0

        # 简单的字符重叠度计算
        s1_chars = set(s1)
        s2_chars = set(s2)

        intersection = len(s1_chars & s2_chars)
        union = len(s1_chars | s2_chars)

        return intersection / union if union > 0 else 0.0

    def get_chinese_name(self, item_id: str) -> str:
        """根据物品ID获取中文名称"""
        return self.id_to_chinese.get(item_id, item_id.replace("minecraft:", "").replace("_", " ").title())

    def get_suggestions(self, user_input: str, max_suggestions: int = 5) -> List[Tuple[str, str]]:
        """获取输入建议，返回 (中文名称, 物品ID) 的列表"""
        if not user_input:
            return []

        matches = self.fuzzy_match(user_input, max_suggestions)
        suggestions = []

        for chinese_name in matches:
            item_id = self.chinese_names[chinese_name]
            suggestions.append((chinese_name, item_id))

        return suggestions

    def validate_and_suggest(self, user_input: str) -> Tuple[Optional[str], List[str]]:
        """验证输入并提供建议
        返回: (找到的物品ID, 建议列表)
        """
        item_id = self.find_item_id(user_input)

        if item_id:
            return item_id, []

        # 如果没找到，提供建议
        suggestions = self.fuzzy_match(user_input, 5)
        return None, suggestions