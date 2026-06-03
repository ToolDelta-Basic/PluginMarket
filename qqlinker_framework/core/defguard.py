"""防御性输入验证层 (Defensive Guard)

═══════════════════════════════════════════════════════════════════════════
设计原则: 对所有输入默认不信任，显式验证后再使用。
═══════════════════════════════════════════════════════════════════════════

使用方式:
  from qqlinker_framework.core.defguard import (
      safe_str, safe_int, safe_dict, safe_list,
      safe_event_message, safe_config_get, validate_onebot_event,
  )

核心约定:
  1. 所有 safe_* 函数绝不抛异常，返回安全的默认值
  2. validate_* 函数返回 (ok, sanitized_value, error_reason) 三元组
  3. 字符串默认截断到合理长度，防止 DoS

═══════════════════════════════════════════════════════════════════════════

此外还提供 Minecraft 命令注入防护函数 escape_player_name。
═══════════════════════════════════════════════════════════════════════
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

_log = logging.getLogger(__name__)


def escape_player_name(name: str) -> str:
    """转义玩家名中的危险字符，防止 Minecraft 命令注入。

    Minecraft 原生命令使用双引号包裹参数，玩家名中含 " 可逃逸
    引号并执行任意命令。此处将 ", \, \n, \r 转义以消除注入风险。
    """
    name = name.replace('\\', '\\\\')  # 反斜杠 → 双反斜杠
    name = name.replace('"', '\\"')        # 双引号 → 转义双引号
    name = name.replace('\n', '')            # 移除换行，防止多行命令注入
    name = name.replace('\r', '')            # 移除回车
    return name


# ── 常量和限制 ──────────────────────────────────────────────

MAX_STRING_LENGTH = 4096       # 单条消息最大字符数
MAX_GROUP_ID = 2 ** 63 - 1     # QQ 群号上限
MAX_USER_ID = 2 ** 63 - 1      # QQ 号上限
MAX_LIST_LENGTH = 500          # 列表元素上限
MAX_DICT_DEPTH = 10            # 嵌套字典深度上限
MAX_MESSAGE_SEGMENTS = 100     # OneBot 消息段上限

# ── 安全类型转换 — 绝不抛异常 ──────────────────────────────────


def safe_str(value: Any, max_len: int = MAX_STRING_LENGTH) -> str:
    """安全地将任意值转为字符串，None → ""，超长截断。

    Args:
        value: 任意输入。
        max_len: 最大允许长度，默认 4096。

    Returns:
        安全字符串（绝不返回 None）。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:max_len]
    if isinstance(value, bytes):
        try:
            s = value.decode("utf-8", errors="replace")
        except Exception:
            s = repr(value)
        return s[:max_len]
    # 其他类型：安全转换
    try:
        s = str(value)
    except Exception:
        s = f"<{type(value).__name__}>"
    return s[:max_len]


def safe_int(
    value: Any,
    default: int = 0,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
) -> int:
    """安全地将任意值转为整数，失败返回 default。

    Args:
        value: 任意输入。
        default: 转换失败时的默认值。
        min_val: 下限（含）。
        max_val: 上限（含）。

    Returns:
        安全的整数值。
    """
    if isinstance(value, int) and not isinstance(value, bool):
        result = value
    elif isinstance(value, float) and value == int(value):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            return default
    else:
        return default

    if min_val is not None and result < min_val:
        return min_val
    if max_val is not None and result > max_val:
        return max_val
    return result


def safe_float(value: Any, default: float = 0.0) -> float:
    """安全地将任意值转为浮点数。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def safe_list(value: Any, max_len: int = MAX_LIST_LENGTH) -> list:
    """安全地将任意值转为列表，None → []，超长截断。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value[:max_len]
    if isinstance(value, tuple):
        return list(value)[:max_len]
    # 不是列表类型，包装
    return [value]


def safe_dict(
    value: Any,
    depth: int = 0,
    max_depth: int = MAX_DICT_DEPTH,
) -> dict:
    """安全地将任意值转为字典，并对嵌套值做浅层 sanitize。

    Args:
        value: 任意输入。
        depth: 当前递归深度（内部用）。
        max_depth: 最大嵌套深度。

    Returns:
        安全的字典（绝不返回 None）。
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        if depth >= max_depth:
            return dict(value)
        result = {}
        for k, v in value.items():
            safe_k = safe_str(k, max_len=256)
            if isinstance(v, dict):
                result[safe_k] = safe_dict(v, depth + 1, max_depth)
            elif isinstance(v, list):
                result[safe_k] = safe_list(v)
            elif v is None:
                result[safe_k] = None  # 保留 None（调用方自己判断）
            else:
                result[safe_k] = v
        return result
    # 尝试包装
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {"_raw": safe_str(value)}


def safe_bool(value: Any, default: bool = False) -> bool:
    """安全地将任意值转为布尔值。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on", "y")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


# ── 事件层防御 — 对框架事件进行标准化处理 ──────────────────────

def safe_event_message(raw_message: Any) -> str:
    """安全提取事件消息文本。

    处理 None、bytes、非字符串等边缘情况。
    """
    return safe_str(raw_message, max_len=MAX_STRING_LENGTH)


def safe_player_name(raw_name: Any) -> str:
    """安全提取玩家名，限制 32 字符。"""
    name = safe_str(raw_name, max_len=32)
    if not name:
        return "<unknown>"
    return name


# ── OneBot 消息解析 ──────────────────────────────────────────

def validate_onebot_event(raw: dict) -> Tuple[bool, Dict[str, Any], str]:
    """验证并标准化 OneBot 事件数据。

    Args:
        raw: WebSocket 接收到的原始 dict。

    Returns:
        (ok, sanitized, reason) — ok 为 False 时应当丢弃该事件。
    """
    if not isinstance(raw, dict):
        return False, {}, "not a dict"

    post_type = safe_str(raw.get("post_type"), max_len=32)
    if post_type != "message":
        return True, raw, "non-message event, pass through"

    message_type = safe_str(raw.get("message_type"), max_len=32)
    if message_type not in ("group", "private"):
        return True, raw, f"unsupported message_type: {message_type}"

    user_id = safe_int(raw.get("user_id"), default=0,
                       min_val=0, max_val=MAX_USER_ID)
    group_id = safe_int(raw.get("group_id"), default=0,
                        min_val=0, max_val=MAX_GROUP_ID)

    if message_type == "group" and group_id == 0:
        return False, {}, "group message without valid group_id"

    # 消息体可能是 str 或 list (OneBot message segments)
    raw_message = raw.get("message")
    if isinstance(raw_message, list):
        if len(raw_message) > MAX_MESSAGE_SEGMENTS:
            return False, {}, f"too many message segments: {len(raw_message)}"
        message_text = _parse_onebot_segments(raw_message)
    else:
        message_text = safe_str(raw_message)

    # sender
    sender = safe_dict(raw.get("sender"))
    nickname = safe_str(
        sender.get("card") or sender.get("nickname") or "未知",
        max_len=64,
    )

    sanitized = {
        "post_type": post_type,
        "message_type": message_type,
        "user_id": user_id,
        "group_id": group_id,
        "nickname": nickname,
        "message": message_text,
        "message_id": raw.get("message_id"),
        "sender": sender,
        "_raw": raw,
    }
    return True, sanitized, "ok"


def _parse_onebot_segments(segments: list) -> str:
    """解析 OneBot 消息段为纯文本。"""
    parts = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        seg_type = safe_str(seg.get("type"), max_len=32)
        if seg_type == "text":
            parts.append(safe_str(seg.get("data", {}).get("text", "")))
        elif seg_type == "at":
            qq = safe_str(seg.get("data", {}).get("qq", ""))
            parts.append(f"[@{'全体成员' if qq == 'all' else qq}]")
        elif seg_type == "image":
            parts.append("[图片]")
        elif seg_type == "face":
            parts.append("[表情]")
        else:
            parts.append(f"[{seg_type}]")
    result = "".join(parts)
    return result[:MAX_STRING_LENGTH]


# ── 配置安全读取 ──────────────────────────────────────────────

def safe_config_get(
    config_svc,
    key: str,
    default: Any = None,
    *,
    expected_type: Optional[type] = None,
) -> Any:
    """安全地从 ConfigManager 读取配置值，类型不匹配时返回 default。

    Args:
        config_svc: ConfigManager 实例。
        key: 配置键（点号分隔）。
        default: 默认值。
        expected_type: 期望的 Python 类型，不匹配时返回 default 并警告。

    Returns:
        配置值或默认值。
    """
    try:
        value = config_svc.get(key, default)
    except Exception:
        return default

    if expected_type is not None and value is not None and not isinstance(value, expected_type):
        _log.warning(
            "配置类型不匹配 [%s]: 期望 %s, 实际 %s (%s)，使用默认值",
            key,
            expected_type.__name__,
            type(value).__name__,
            repr(value)[:80],
            )
        return default

    return value


def safe_config_list(config_svc, key: str, default=None) -> list:
    """安全读取配置列表，强制返回 list。"""
    result = safe_config_get(config_svc, key, default or [])
    return safe_list(result)


def safe_config_dict(config_svc, key: str, default=None) -> dict:
    """安全读取配置字典，强制返回 dict。"""
    result = safe_config_get(config_svc, key, default or {})
    return safe_dict(result)


# ── 命令参数安全 ───────────────────────────────────────────────

def safe_command_args(raw_text: str, max_args: int = 20) -> list:
    """安全地将命令文本解析为参数列表。

    Args:
        raw_text: 命令后的参数字符串。
        max_args: 最大参数数量。

    Returns:
        安全参数列表。
    """
    text = safe_str(raw_text, max_len=MAX_STRING_LENGTH)
    if not text:
        return []
    parts = text.split()
    return [part[:256] for part in parts[:max_args]]


# ── 批量验证工具 ──────────────────────────────────────────────

def validate_game_command(
    cmd: str, allowed: List[str], dangerous: List[str]
) -> Tuple[bool, str]:
    """验证游戏指令是否在允许列表且不含危险参数。

    Args:
        cmd: 完整指令字符串。
        allowed: 允许的根命令列表。
        dangerous: 危险参数列表。

    Returns:
        (合法, 错误信息)
    """
    cmd_clean = safe_str(cmd, max_len=512).strip().lstrip("/").lower()
    if not cmd_clean:
        return False, "指令为空"
    parts = cmd_clean.split()
    root = parts[0]
    allowed_lower = [a.lower() for a in allowed]
    if root not in allowed_lower:
        return False, f"禁止执行的命令: {root}"
    dangerous_lower = [d.lower() for d in dangerous]
    for arg in parts[1:]:
        if arg in dangerous_lower:
            return False, f"参数包含敏感项: {arg}"
    return True, ""
