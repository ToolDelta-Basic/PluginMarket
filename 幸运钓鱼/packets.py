"""
鱼钩数据包的字段解析。
"""

from dataclasses import dataclass

HOOK_TYPES = ("minecraft:fishing_hook", "fishing_hook")

# 鱼钩的实体事件号
HOOK_EVENTS = {
    11: "冒泡",
    12: "鱼在靠近",
    13: "咬住了",
    14: "试探, 未咬住",
}


def get_any(data: dict, *names):
    for name in names:
        if name in data:
            return data[name]
    return None


def parse_pos(raw) -> tuple[float, float, float] | None:
    if isinstance(raw, dict):
        x, y, z = get_any(raw, "X", "x"), get_any(raw, "Y", "y"), get_any(raw, "Z", "z")
    elif isinstance(raw, (list, tuple)) and len(raw) >= 3:
        x, y, z = raw[0], raw[1], raw[2]
    else:
        return None
    try:
        return (float(x), float(y), float(z))
    except (TypeError, ValueError):
        return None


def int_of(packet: dict, *names) -> int | None:
    raw = get_any(packet, *names)
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def runtime_id(packet: dict) -> int | None:
    "ActorEvent 和 MoveActorAbsolute 认这个"
    return int_of(
        packet, "EntityRuntimeID", "entityRuntimeId", "RuntimeEntityID",
        "runtime_entity_id", "runtime_id",
    )


def unique_id(packet: dict) -> int | None:
    "AddActor 和 RemoveActor 认这个, 和运行时 ID 是两套编号, 不能混用"
    return int_of(
        packet, "EntityUniqueID", "entityUniqueId", "entity_id_self",
        "unique_id", "EntityUniqueId",
    )


def owner_of(packet: dict) -> int | None:
    "AddActor 元数据 5 号键是 owner_eid, 存的是主人的 unique ID"
    meta = get_any(packet, "EntityMetadata", "entityMetadata", "Metadata", "metadata")
    if isinstance(meta, dict):
        for key in ("5", 5, "Owner", "owner", "owner_eid", "OwnerID", "ownerId"):
            if key in meta:
                try:
                    return int(meta[key])
                except (TypeError, ValueError):
                    continue
    direct = get_any(packet, "OwnerRuntimeID", "ownerRuntimeId", "OwnerID")
    if direct is None:
        return None
    try:
        return int(direct)
    except (TypeError, ValueError):
        return None


def is_hook(packet: dict) -> bool:
    kind = get_any(packet, "EntityType", "entityType", "entity_type", "Type", "type")
    return isinstance(kind, str) and kind.lower() in HOOK_TYPES


@dataclass
class Hook:
    runtime_id: int
    unique_id: int | None
    owner_id: int | None
    pos: tuple[float, float, float]
    cast_at: float
    # 收到过移动包没有; 没有的话 pos 还是出手位置, 不是落水点
    moved: bool = False
    # 靠近事件一竿会连发很多次, 提示过就不再提示
    warned: bool = False
    bit_at: float = 0.0
    last_alert: float = 0.0
