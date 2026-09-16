"""ToolDelta 在线玩家能力读取与八位权限标志转换。"""
from __future__ import annotations

from typing import Any


ABILITY_FIELDS = (
    ("建造", "build"),
    ("挖掘", "mine"),
    ("门和开关", "doors_and_switches"),
    ("打开容器", "open_containers"),
    ("攻击玩家", "attack_players"),
    ("攻击生物", "attack_mobs"),
    ("管理员命令", "operator_commands"),
    ("传送", "teleport"),
)


def permission_category(flags: str | None) -> str:
    """将八位能力标志映射为用户可读的权限类别。"""
    if not isinstance(flags, str) or len(flags) != 8 or any(char not in "01" for char in flags):
        return "未知"
    return {"00000000": "访客", "11111100": "成员", "11111111": "管理员"}.get(flags, "自定义")


def read_player_abilities(player: Any) -> dict[str, Any]:
    """读取玩家能力；字段缺失时返回未就绪，绝不把缺失当成 False。"""
    try:
        abilities = getattr(player, "abilities", None)
    except Exception:
        abilities = None
    if abilities is None:
        return {"就绪": False, "权限标志": None, "能力": {}, "玩家权限等级": None, "命令权限等级": None}
    values: dict[str, bool] = {}
    for label, attr in ABILITY_FIELDS:
        value = getattr(abilities, attr, None)
        if not isinstance(value, bool):
            return {
                "就绪": False,
                "权限标志": None,
                "能力": values,
                "玩家权限等级": getattr(abilities, "player_permissions", None),
                "命令权限等级": getattr(abilities, "command_permissions", None),
            }
        values[label] = value
    flags = "".join("1" if values[label] else "0" for label, _ in ABILITY_FIELDS)
    return {
        "就绪": True,
        "权限标志": flags,
        "能力": values,
        "玩家权限等级": getattr(abilities, "player_permissions", None),
        "命令权限等级": getattr(abilities, "command_permissions", None),
    }


def compare_ability_flags(actual: str | None, expected: str) -> list[str]:
    """返回八位权限中存在差异的中文能力名称。"""
    if not isinstance(actual, str) or len(actual) != 8 or len(expected) != 8:
        return [label for label, _ in ABILITY_FIELDS]
    return [label for (label, _), a, e in zip(ABILITY_FIELDS, actual, expected) if a != e]
