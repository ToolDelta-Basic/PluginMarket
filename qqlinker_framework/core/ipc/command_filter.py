from __future__ import annotations

import re
from typing import Tuple

__all__ = [
    "parse_command",
    "extract_final_command",
    "check_give_params",
    "check_fill_params",
    "check_command_safety",
    "DANGEROUS_COMMANDS",
    "SAFE_COMMANDS",
]

# ─── 命令分类 ────────────────────────────────────────────────────────────────

DANGEROUS_COMMANDS: set[str] = {
    "op",
    "deop",
    "stop",
    "restart",
    "save-off",
    "save-on",
    "whitelist",
    "permission",
    "changesetting",
    "dedicatedwsserver",  # BE 远程连接
}

SAFE_COMMANDS: set[str] = {
    "say",
    "tell",
    "msg",
    "w",
    "me",
    "title",
    "subtitle",
    "actionbar",
    "list",
    "testfor",
    "querytarget",
    "scoreboard",  # 只读场景
    "playsound",
    "stopsound",
    "particle",
    "effect",
    "tag",  # 标签操作
}

# execute 子命令关键字（run 之前可能出现的）
_EXECUTE_SUBCOMMANDS: set[str] = {
    "as",
    "at",
    "positioned",
    "rotated",
    "facing",
    "in",
    "anchored",
    "align",
    "if",
    "unless",
}

_MAX_EXECUTE_DEPTH: int = 3


# ─── 命令解析 ────────────────────────────────────────────────────────────────


def parse_command(cmd: str) -> str:
    """提取命令的首 token（去掉 / 前缀）。

    Examples:
        "/give @p diamond 64" → "give"
        "give @p diamond 64" → "give"
        "  /say hello" → "say"
    """
    stripped = cmd.strip()
    if not stripped:
        return ""
    # 去掉前导 /
    if stripped.startswith("/"):
        stripped = stripped[1:]
    # 取第一个 token
    parts = stripped.split(None, 1)
    return parts[0].lower() if parts else ""


def extract_final_command(cmd: str, depth: int = 0) -> str:
    """递归解析 /execute 链，提取最终执行的命令。

    /execute as @a run give @s diamond 64
    → 最终命令: "give @s diamond 64"

    /execute as @a at @s run execute as @p run op hacker
    → 递归: execute as @p run op hacker
    → 最终命令: "op hacker"

    深度限制: 3 层。超过时返回当前已解析的部分。
    """
    stripped = cmd.strip()
    if stripped.startswith("/"):
        stripped = stripped[1:]

    if not stripped:
        return ""

    # 检查是否是 execute 命令
    parts = stripped.split(None, 1)
    first_token = parts[0].lower()

    if first_token != "execute":
        return stripped

    if depth >= _MAX_EXECUTE_DEPTH:
        # 超过深度限制，返回当前命令字符串
        return stripped

    # 查找 "run" 关键字 — 它标记最终命令的开始
    # 格式: execute <subcommand> <args> [subcommand <args> ...] run <command>
    # 需要跳过 execute 子命令参数中可能出现的 "run" 字符串
    # 策略：从左到右扫描 tokens，识别子命令结构，找到顶层 run
    remainder = parts[1] if len(parts) > 1 else ""
    final_cmd = _find_run_target(remainder)

    if final_cmd is None:
        # 没有找到 run，返回原始命令
        return stripped

    # 递归解析（最终命令可能又是 execute）
    return extract_final_command(final_cmd, depth + 1)


def _find_run_target(remainder: str) -> str | None:
    """在 execute 的参数部分找到 'run' 关键字，返回 run 后面的命令。

    处理子命令（as/at/positioned 等）的参数跳过。
    """
    tokens = remainder.split()
    i = 0
    while i < len(tokens):
        token_lower = tokens[i].lower()

        if token_lower == "run":
            # run 后面是最终命令
            rest = " ".join(tokens[i + 1 :])
            return rest if rest else None

        # 当前 token 是子命令关键字，跳过其参数
        if token_lower in _EXECUTE_SUBCOMMANDS:
            i += 1
            # 跳过子命令参数（直到下一个子命令关键字或 run）
            # 子命令参数数量不固定，我们向前看
            # 策略：继续向前，直到碰到另一个子命令或 run
            while i < len(tokens):
                next_lower = tokens[i].lower()
                if next_lower == "run" or next_lower in _EXECUTE_SUBCOMMANDS:
                    break
                i += 1
        else:
            # 未知 token，可能是参数的一部分，继续
            i += 1

    return None


# ─── 参数安全检查 ─────────────────────────────────────────────────────────────


def check_give_params(cmd: str) -> Tuple[bool, str]:
    """检查 /give 命令参数。

    规则：
    - 单次数量 ≤ 64

    解析格式: /give <target> <item> [count] [data]

    Returns: (allowed, reason)
    """
    stripped = cmd.strip()
    if stripped.startswith("/"):
        stripped = stripped[1:]

    parts = stripped.split()
    # parts[0] = "give", parts[1] = target, parts[2] = item, parts[3] = count (optional)
    if len(parts) < 3:
        # 不完整的命令，放行（服务器会报错）
        return (True, "")

    if len(parts) < 4:
        # 没有指定数量，默认1，放行
        return (True, "")

    count_str = parts[3]
    try:
        count = int(count_str)
    except ValueError:
        # 可能是 data 字段或无效输入，放行让服务器处理
        return (True, "")

    if count > 64:
        return (False, f"give count {count} exceeds limit 64")
    if count < 0:
        return (False, f"give count {count} is negative")

    return (True, "")


def check_fill_params(cmd: str) -> Tuple[bool, str]:
    """检查 /fill 范围。

    规则：
    - 范围 ≤ 32*32*32 = 32768 方块

    解析格式: /fill <x1> <y1> <z1> <x2> <y2> <z2> <block> [...]
    如果坐标含 ~ 或 ^（相对坐标），无法确定范围时放行但返回审计提示。

    Returns: (allowed, reason)
    """
    stripped = cmd.strip()
    if stripped.startswith("/"):
        stripped = stripped[1:]

    parts = stripped.split()
    # parts[0] = "fill"/"setblock", parts[1..6] = coords, parts[7] = block
    if len(parts) < 8:
        # 不完整的 fill 命令
        # setblock 只有一个坐标（3个参数），不需要范围检查
        if parts and parts[0].lower() == "setblock":
            return (True, "")
        return (True, "")

    coords_raw = parts[1:7]

    # 检查是否有相对坐标
    has_relative = any(
        c.startswith("~") or c.startswith("^") for c in coords_raw
    )

    if has_relative:
        # 无法确定绝对范围，放行但标记审计
        return (True, "relative_coords_audit")

    # 尝试解析绝对坐标
    try:
        coords = [_parse_coord(c) for c in coords_raw]
    except ValueError:
        # 无法解析，放行
        return (True, "")

    x1, y1, z1 = coords[0], coords[1], coords[2]
    x2, y2, z2 = coords[3], coords[4], coords[5]

    dx = abs(x2 - x1) + 1
    dy = abs(y2 - y1) + 1
    dz = abs(z2 - z1) + 1
    volume = dx * dy * dz

    max_volume = 32 * 32 * 32  # 32768

    if volume > max_volume:
        return (False, f"fill volume {volume} exceeds limit {max_volume}")

    return (True, "")


def _parse_coord(s: str) -> int:
    """解析坐标值（整数部分）。"""
    # 去掉可能的 ~ 或 ^ 前缀（不应该到这里，但防御性编程）
    if s.startswith("~") or s.startswith("^"):
        raise ValueError("relative coordinate")
    return int(float(s))


# ─── 综合安全检查 ─────────────────────────────────────────────────────────────


def check_command_safety(
    cmd: str, caller_mid: int
) -> Tuple[bool, str]:
    """对单条命令进行完整安全检查。

    流程：
    1. extract_final_command（处理 execute 嵌套）
    2. 首 token 提取
    3. 危险命令黑名单检查（mid > 0 禁止）
    4. mid > 300: 只允许安全白名单命令
    5. /give: check_give_params
    6. /fill, /setblock: mid ≤ 100 + check_fill_params

    Args:
        cmd: 原始命令字符串
        caller_mid: 调用方模块 ID

    Returns: (allowed, reason)
    """
    if not cmd or not cmd.strip():
        return (False, "empty command")

    # 1. 解析 execute 链
    final_cmd = extract_final_command(cmd)
    if not final_cmd:
        return (False, "unable to parse command")

    # 2. 提取首 token
    first_token = parse_command(final_cmd)
    if not first_token:
        return (False, "empty command token")

    # 3. 危险命令检查 — mid > 0 的模块不允许执行危险命令
    if first_token in DANGEROUS_COMMANDS:
        if caller_mid > 0:
            return (False, f"dangerous command '{first_token}' blocked for mid={caller_mid}")
        # mid == 0 (核心) 允许
        return (True, "")

    # 4. mid > 300: 仅白名单命令
    if caller_mid > 300:
        if first_token not in SAFE_COMMANDS:
            return (False, f"command '{first_token}' not in safe list for mid={caller_mid}")
        return (True, "")

    # 5. /give 参数检查
    if first_token == "give":
        allowed, reason = check_give_params(final_cmd)
        if not allowed:
            return (False, reason)

    # 6. /fill, /setblock 范围检查 — 要求 mid ≤ 100
    if first_token in ("fill", "setblock"):
        if caller_mid > 100:
            return (False, f"command '{first_token}' requires mid <= 100, got {caller_mid}")
        if first_token == "fill":
            allowed, reason = check_fill_params(final_cmd)
            if not allowed:
                return (False, reason)

    return (True, "")
