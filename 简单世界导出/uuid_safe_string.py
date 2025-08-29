_string_uuid_replace_map = {
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


def make_uuid_safe_string(unique_id: str) -> str:
    """
    make_uuid_safe_string 返回 unique_id 的安全化表示，
    这使得其不可能被网易屏蔽词所拦截

    Args:
        unique_id (str): UUID 字符串

    Returns:
        str: unique_id 的安全化表示
    """
    result = ""
    for i in unique_id:
        result += _string_uuid_replace_map[i]
    return result
