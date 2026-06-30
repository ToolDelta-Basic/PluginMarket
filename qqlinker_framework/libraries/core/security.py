import re
import unicodedata
from typing import Set

from ..channel_host import Library


# ── Homoglyph 检测 ──────────────────────────────────────────

# 常见的视觉混淆字符映射（Latin ↔ Cyrillic 等）
_HOMOGLYPH_MAP = {
    '\u0410': 'A', '\u0412': 'B', '\u0421': 'C', '\u0415': 'E',
    '\u041d': 'H', '\u041a': 'K', '\u041c': 'M', '\u041e': 'O',
    '\u0420': 'P', '\u0422': 'T', '\u0425': 'X', '\u0423': 'Y',
    '\u0430': 'a', '\u0435': 'e', '\u043e': 'o', '\u0440': 'p',
    '\u0441': 'c', '\u0443': 'y', '\u0445': 'x',
}


class SecurityService:
    """安全工具服务。"""

    def sanitize_player_name(self, name: str) -> str:
        """清理玩家名称（去除不可见字符和控制字符）。"""
        if not name:
            return ""
        # 去除控制字符
        cleaned = "".join(
            c for c in name
            if unicodedata.category(c) not in ('Cc', 'Cf', 'Co', 'Cn')
            or c in (' ', '\t')
        )
        # 去首尾空白
        return cleaned.strip()

    def sanitize_game_command_param(self, param: str) -> str:
        """清理游戏命令参数（防注入）。"""
        if not param:
            return ""
        # 去除可能的命令注入字符
        dangerous = set(';&|`$(){}[]\\')
        return "".join(c for c in param if c not in dangerous).strip()

    def escape_player_name(self, name: str) -> str:
        """转义玩家名用于消息显示。"""
        if not name:
            return ""
        # 转义 CQ 码相关字符
        return (name
                .replace("&", "&amp;")
                .replace("[", "&#91;")
                .replace("]", "&#93;"))

    def contains_homoglyphs(self, text: str) -> bool:
        """检测文本中是否包含视觉混淆字符。"""
        for char in text:
            if char in _HOMOGLYPH_MAP:
                return True
        return False

    def unicode_safe_strip(self, text: str) -> str:
        """安全去除 Unicode 不可见字符（保留正常空格）。"""
        if not text:
            return ""
        return "".join(
            c for c in text
            if unicodedata.category(c) not in ('Cf', 'Co', 'Cn')
        ).strip()

    def detect_section_sign(self, text: str) -> bool:
        """检测 Minecraft § 颜色代码。"""
        return '\u00a7' in text if text else False


class SecurityLibrary(Library):
    """安全工具库。"""

    name = "security_tools"
    version = "1.6.0"
    dependencies: list = []

    async def mount(self) -> None:
        svc = SecurityService()
        self.services.register("security", svc, mid=400)  # 所有模块可访问

    async def unmount(self) -> None:
        pass
