from typing import Tuple

class InputValidator:
    """输入验证器"""

    @staticmethod
    def validate_guild_name(name: str) -> Tuple[bool, str]:
        """验证公会名称"""
        if not name:
            return False, "公会名称不能为空"

        if len(name) < 2:
            return False, "公会名称至少需要2个字符"

        if len(name) > 20:
            return False, "公会名称不能超过20个字符"

        # 检查特殊字符
        invalid_chars = ['&', '<', '>', '"', "'", '\\', '/', '|']
        for char in invalid_chars:
            if char in name:
                return False, f"公会名称不能包含特殊字符: {char}"

        return True, ""

    @staticmethod
    def validate_player_name(name: str) -> Tuple[bool, str]:
        """验证玩家名称"""
        if not name:
            return False, "玩家名称不能为空"

        if len(name) < 3 or len(name) > 16:
            return False, "玩家名称长度应在3-16个字符之间"

        return True, ""

    @staticmethod
    def validate_positive_integer(value: str, field_name: str = "数值") -> Tuple[bool, int, str]:
        """验证正整数"""
        if not value:
            return False, 0, f"{field_name}不能为空"

        if not value.isdigit():
            return False, 0, f"{field_name}必须是正整数"

        num = int(value)
        if num <= 0:
            return False, 0, f"{field_name}必须大于0"

        return True, num, ""

    @staticmethod
    def validate_announcement(text: str) -> Tuple[bool, str]:
        """验证公告内容"""
        if not text:
            return False, "公告内容不能为空"

        if len(text) > 200:
            return False, "公告内容不能超过200个字符"

        return True, ""
