"""Data models for the land protection cloud interop plugin."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple


class LandRank(Enum):
    """Land membership roles."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

    @property
    def display_name(self):
        return {
            "owner": "§c领主",
            "admin": "§6管理员",
            "member": "§a成员",
        }[self.value]


@dataclass
class LandMember:
    """One member entry inside a land claim."""

    name: str
    xuid: str
    rank: LandRank
    join_time: float = field(default_factory=time.time)

    def to_dict(self):
        return {
            "name": self.name,
            "xuid": self.xuid,
            "rank": self.rank.value,
            "join_time": self.join_time,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d["name"],
            xuid=str(d["xuid"]),
            rank=LandRank(d["rank"]),
            join_time=d.get("join_time", time.time()),
        )


@dataclass
class LandData:
    """Persisted land claim data."""

    land_id: str
    name: str
    owner: str
    owner_xuid: str
    center: Tuple[float, float, float]
    radius: int
    shape: str = "圆形"
    dimension: int = 0
    size: Optional[Tuple[int, int, int]] = None
    members: List[LandMember] = field(default_factory=list)
    create_time: float = field(default_factory=time.time)

    def to_dict(self):
        return {
            "land_id": self.land_id,
            "name": self.name,
            "owner": self.owner,
            "owner_xuid": self.owner_xuid,
            "center": list(self.center),
            "radius": self.radius,
            "shape": self.shape,
            "size": list(self.get_size()) if self.is_box() else None,
            "dimension": self.dimension,
            "members": [m.to_dict() for m in self.members],
            "create_time": self.create_time,
        }

    @classmethod
    def from_dict(cls, d):
        members = [LandMember.from_dict(m) for m in d.get("members", [])]
        shape = cls.normalize_shape(d.get("shape", "圆形"))
        radius = d["radius"]
        size = cls.normalize_size(
            d.get("size"),
            radius) if shape == "方形" else None
        return cls(
            land_id=d["land_id"],
            name=d["name"],
            owner=d["owner"],
            owner_xuid=str(d["owner_xuid"]),
            center=tuple(d["center"]),
            radius=radius,
            shape=shape,
            dimension=d.get("dimension", 0),
            size=size,
            members=members,
            create_time=d.get("create_time", time.time()),
        )

    @staticmethod
    def normalize_shape(raw: Any) -> str:
        shape = str(raw or "圆形").strip().lower()
        if shape in (
            "方形",
            "矩形",
            "长方形",
            "square",
            "box",
            "立方体",
            "长方体",
                "cuboid"):
            return "方形"
        return "圆形"

    @staticmethod
    def normalize_size(
            raw: Any, fallback_radius: int = 1) -> Tuple[int, int, int]:
        if isinstance(raw, (list, tuple)) and len(raw) == 3:
            try:
                length = max(1, int(raw[0]))
                height = max(1, int(raw[1]))
                width = max(1, int(raw[2]))
                return (length, height, width)
            except (TypeError, ValueError):
                pass
        fallback = max(1, int(fallback_radius) * 2)
        return (fallback, fallback, fallback)

    def is_box(self) -> bool:
        return self.normalize_shape(self.shape) == "方形"

    def get_size(self) -> Tuple[int, int, int]:
        return self.normalize_size(self.size, self.radius)

    def get_bounds(self) -> Tuple[Tuple[float,
                                        float, float], Tuple[float, float, float]]:
        length, height, width = self.get_size()
        cx, cy, cz = self.center
        half = (length / 2, height / 2, width / 2)
        return (
            (cx - half[0], cy - half[1], cz - half[2]),
            (cx + half[0], cy + half[1], cz + half[2]),
        )

    def contains_pos(self, pos: Tuple[float, float, float]) -> bool:
        x, y, z = pos
        if self.is_box():
            min_pos, max_pos = self.get_bounds()
            return all(min_pos[i] <= pos[i] <= max_pos[i] for i in range(3))
        cx, cy, cz = self.center
        return (x - cx) ** 2 + (y - cy) ** 2 + \
            (z - cz) ** 2 <= self.radius ** 2

    def range_text(self) -> str:
        if self.is_box():
            length, height, width = self.get_size()
            return f"方形 长:{length}, 高:{height}, 宽:{width}"
        return f"圆形 半径:{self.radius}"

    def get_member(self, xuid: str) -> Optional[LandMember]:
        xuid = str(xuid)
        for member in self.members:
            if member.xuid == xuid:
                return member
        return None

    def has_permission(self, xuid: str, perm: str) -> bool:
        member = self.get_member(xuid)
        if not member:
            return False
        if member.rank == LandRank.OWNER:
            return True
        if member.rank == LandRank.ADMIN and perm in ["manage_member"]:
            return True
        if member.rank == LandRank.MEMBER and perm == "tp":
            return True
        return False

    def can_manage_member(self, manager_xuid: str, target_xuid: str) -> bool:
        manager = self.get_member(manager_xuid)
        target = self.get_member(target_xuid)
        if not manager or not target:
            return False
        if manager.rank == LandRank.OWNER:
            return True
        if manager.rank == LandRank.ADMIN and target.rank == LandRank.MEMBER:
            return True
        return False
