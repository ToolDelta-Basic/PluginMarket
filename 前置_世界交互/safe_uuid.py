import uuid

# string_uuid_replace_map 保存了一个字符串映射，
# 用于将字符串型的 UUID 转化为不包含屏蔽词的安全字符串
string_uuid_replace_map = {
    "0": "+",
    "1": "−",
    "2": "|",
    "3": "–",
    "4": "×",
    "5": "÷",
    "6": "¦",
    "7": "—",
    "8": "=",
    "9": "(",
    "a": "<",
    "b": ">",
    "c": "⁅",
    "d": "⁆",
    "e": "[",
    "f": "]",
    "g": "‹",
    "h": "›",
    "i": "⌈",
    "j": "⌉",
    "k": "{",
    "l": "}",
    "m": "«",
    "n": "»",
    "o": "⌊",
    "p": "⌋",
    "q": "⟨",
    "r": "⟩",
    "s": "⟦",
    "t": "⟧",
    "u": "`",
    "v": "´",
    "w": "⟪",
    "x": "⟫",
    "y": "⟬",
    "z": "⟭",
    "-": "→",
}


def make_uuid_safe_string(unique_id: uuid.UUID) -> str:
    """
    make_uuid_safe_string 返回 unique_id 的安全化表示，
    这使得其不可能被网易屏蔽词所拦截

    Args:
        unique_id (str): 一个 UUID 实例

    Returns:
        str: 这个 UUID 的安全化字符串表示
    """
    result = ""
    for i in str(unique_id):
        result += string_uuid_replace_map[i]
    return result
