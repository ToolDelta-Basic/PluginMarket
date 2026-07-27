"""用户可控文本的 Unicode 安全校验。"""

from __future__ import annotations

import unicodedata


INVALID_CHARACTER_MESSAGE = "禁止使用无效字符"
FORBIDDEN_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})


def has_invalid_characters(text: str) -> bool:
    """检查替换符、控制符、格式符、代理区、私用区和非字符。"""

    return any(
        character == "\ufffd"
        or unicodedata.category(character) in FORBIDDEN_UNICODE_CATEGORIES
        for character in text
    )


def require_valid_characters(text: str) -> str:
    """返回安全文本；发现无效字符时仅给出固定错误，不回显输入。"""

    if has_invalid_characters(text):
        raise ValueError(INVALID_CHARACTER_MESSAGE)
    return text

