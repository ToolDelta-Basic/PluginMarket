"""通用输入清洗工具函数。

提供 Minecraft 命令参数和玩家名的安全转义函数，
防止字符串拼接导致的命令注入。
"""
import json
import re
import unicodedata
from typing import List, Optional, Set

# ── 禁止使用的 Minecraft 命令分隔符和危险字符 ──────────────

# 命令注入分隔符（可在游戏命令字符串中引入新命令）
_COMMAND_DELIMITERS = {"$", "&", "|", ";", "\n", "\r", "\\", "`"}

# 玩家名禁止的字符（Minecraft Bedrock 规则 + 额外安全限制）
_ILLEGAL_NAME_CHARS = {
    '"', "'", "\\", " ", "\t", "\n", "\r",
    "$", "&", "|", ";", "`", "@", "!", "%", "^",
    "(", ")", "{", "}", "[", "]", "<", ">",
}

# ── Unicode 同形字映射 ──────────────────────────────────

# 常见拉丁字母的 Cyrillic/Greek/数学 同形字
_HOMOGLYPH_MAP: dict[int, int] = {}

# 初始化同形字映射
def _init_homoglyph_map() -> None:
    """初始化 Unicode 同形字 → ASCII 映射表。"""
    pairs = [
        # Cyrillic
        ("А", "A"), ("В", "B"), ("Е", "E"), ("К", "K"),
        ("М", "M"), ("Н", "H"), ("О", "O"), ("Р", "P"),
        ("С", "C"), ("Т", "T"), ("У", "Y"), ("Х", "X"),
        ("а", "a"), ("е", "e"), ("о", "o"), ("р", "p"),
        ("с", "c"), ("у", "y"), ("х", "x"),
        # Greek
        ("Α", "A"), ("Β", "B"), ("Ε", "E"), ("Ζ", "Z"),
        ("Η", "H"), ("Ι", "I"), ("Κ", "K"), ("Μ", "M"),
        ("Ν", "N"), ("Ο", "O"), ("Ρ", "P"), ("Τ", "T"),
        ("Υ", "Y"), ("Χ", "X"),
    ]
    for homoglyph, ascii_char in pairs:
        try:
            _HOMOGLYPH_MAP[ord(homoglyph)] = ord(ascii_char)
        except (TypeError, ValueError):
            pass


_init_homoglyph_map()


# ── 通用转义函数 ───────────────────────────────────────


def sanitize_player_name(name: str, max_len: int = 16) -> str:
    """清洗玩家名，移除 Minecraft 命令注入危险字符并截断。

    适用场景：任何将玩家名嵌入 tellraw/kick/damage 等游戏命令之前的清洗。

    Args:
        name: 原始玩家名。
        max_len: 最大允许长度（Minecraft Bedrock 默认 16）。

    Returns:
        安全的玩家名字符串。
    """
    if not name:
        return "_unknown_"
    # 移除所有非法字符
    result: list[str] = []
    for ch in name:
        if ch in _ILLEGAL_NAME_CHARS:
            continue
        if ord(ch) < 32:  # 控制字符
            continue
        result.append(ch)
    cleaned = "".join(result)
    if not cleaned:
        return "_unknown_"
    return cleaned[:max_len]


def sanitize_game_command_param(
    value: str,
    allow_spaces: bool = False,
    max_len: int = 256,
) -> str:
    """清洗游戏命令参数，移除命令注入分隔符。

    适用场景：任何通过字符串拼接构建游戏命令时，对参数值的清洗。
    包括 reason、warn_text 等用户可控内容。

    Args:
        value: 原始参数值。
        allow_spaces: 是否允许空格（如 reason 文本）。
        max_len: 最大长度。

    Returns:
        安全的参数字符串。
    """
    if not value:
        return ""
    result: list[str] = []
    for ch in value:
        if ch in _COMMAND_DELIMITERS:
            continue
        if ord(ch) < 32:
            continue
        if not allow_spaces and ch == " ":
            continue
        result.append(ch)
    cleaned = "".join(result)
    return cleaned[:max_len]


def json_safe_str(value: str) -> str:
    """将任意字符串转为 JSON-safe 字符串，用于 tellraw / rawtext 构建。

    与 json.dumps(str) 等效，但提供清晰的语义名称。
    """
    return json.dumps(value, ensure_ascii=False)


# ── Unicode 同形字检测 ─────────────────────────────────


def contains_homoglyphs(
    text: str,
    dangerous_prefixes: Optional[Set[str]] = None,
) -> bool:
    """检测文本中是否包含 Unicode 同形字（混淆攻击）。

    检查文本在规范化后是否匹配危险前缀，防御以 Cyrillic/Greek
    同形字绕过 "." / "。" 等命令前缀检测。

    Args:
        text: 待检测的文本。
        dangerous_prefixes: 禁止的前缀集合（ASCII 形式），
                           默认检查 ".", "。", "!", "#", "/"。

    Returns:
        True 表示检测到潜在的同形字前缀绕过。
    """
    if not text:
        return False
    if dangerous_prefixes is None:
        dangerous_prefixes = {".", "。", "!", "#", "/"}
    # 尝试将文本转为 ASCII 兼容形式
    normalized = unicodedata.normalize("NFKD", text)
    ascii_first_char = ""
    for ch in normalized:
        cp = ord(ch)
        if cp in _HOMOGLYPH_MAP:
            ascii_first_char = chr(_HOMOGLYPH_MAP[cp])
            break
        if cp < 128:
            ascii_first_char = ch
            break
    if not ascii_first_char:
        return False
    return ascii_first_char in dangerous_prefixes


def unicode_safe_strip(text: str) -> str:
    """安全去除 Unicode 空白（包括全角空格、零宽字符等）。

    比 str.strip() 更彻底地处理 Unicode 混淆。
    """
    if not text:
        return ""
    # 移除所有 Unicode 空白和零宽字符
    cleaned = [
        ch for ch in text
        if unicodedata.category(ch) not in ("Zs", "Zl", "Zp", "Cc", "Cf")
    ]
    return "".join(cleaned).strip()


# ── 通用输入验证 ──────────────────────────────────────


def is_safe_alphanumeric(
    value: str,
    extra_allowed: str = "_",
    max_len: int = 64,
) -> bool:
    """检查字符串是否仅包含安全字符（字母数字 + 额外允许的字符）。

    Args:
        value: 待检查的字符串。
        extra_allowed: 额外允许的字符集合。
        max_len: 最大允许长度。

    Returns:
        True 表示安全。
    """
    if not value or len(value) > max_len:
        return False
    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        + extra_allowed
    )
    return all(ch in allowed for ch in value)
