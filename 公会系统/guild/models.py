import uuid
import time

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from tooldelta import  fmts
from datetime import datetime
from guild.config import Config

# FIRE 枚举类型 FIRE
class GuildRank(Enum):
    OWNER = "owner"
    DEPUTY = "deputy"
    ELDER = "elder"
    MEMBER = "member"
    
    @property
    def display_name(self):
        return {
            "owner": "§c会长",
            "deputy": "§6副会长",
            "elder": "§e长老",
            "member": "§a成员"
        }[self.value]

# FIRE 数据类 FIRE
@dataclass
class GuildBase:
    """公会据点信息"""
    dimension: int
    x: float
    y: float
    z: float

    def to_dict(self):
        return {"dimension": self.dimension, "x": self.x, "y": self.y, "z": self.z}

@dataclass
class VaultItem:
    """仓库物品信息"""
    item_id: str
    count: int
    price: int  # 贡献点价格
    seller: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        return {
            "item_id": self.item_id,
            "count": self.count,
            "price": self.price,
            "seller": self.seller,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            item_id=data["item_id"],
            count=data["count"],
            price=data["price"],
            seller=data["seller"],
            timestamp=data.get("timestamp", time.time())
        )


@dataclass
class GuildMember:
    """公会成员信息"""
    name: str
    rank: GuildRank
    join_time: float
    contribution: int = 0
    last_online: float = field(default_factory=time.time)
    
    def to_dict(self):
        return {
            "name": self.name,
            "rank": self.rank.value,
            "join_time": self.join_time,
            "contribution": self.contribution,
            "last_online": self.last_online
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data["name"],
            rank=GuildRank(data.get("rank", "member")),
            join_time=data.get("join_time", time.time()),
            contribution=data.get("contribution", 0),
            last_online=data.get("last_online", time.time())
        )

@dataclass
class GuildTask:
    """公会任务"""
    task_id: str
    name: str
    description: str
    task_type: str  # "collect", "kill", "build", "trade"
    target: str  # 目标物品/怪物等
    target_count: int
    current_count: int = 0
    reward_exp: int = 0
    reward_contribution: int = 0
    create_time: float = field(default_factory=time.time)
    deadline: float = 0  # 截止时间，0表示无限期
    completed: bool = False
    participants: List[str] = field(default_factory=list)  # 参与者列表

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type,
            "target": self.target,
            "target_count": self.target_count,
            "current_count": self.current_count,
            "reward_exp": self.reward_exp,
            "reward_contribution": self.reward_contribution,
            "create_time": self.create_time,
            "deadline": self.deadline,
            "completed": self.completed,
            "participants": self.participants
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            task_id=data["task_id"],
            name=data["name"],
            description=data["description"],
            task_type=data["task_type"],
            target=data["target"],
            target_count=data["target_count"],
            current_count=data.get("current_count", 0),
            reward_exp=data.get("reward_exp", 0),
            reward_contribution=data.get("reward_contribution", 0),
            create_time=data.get("create_time", time.time()),
            deadline=data.get("deadline", 0),
            completed=data.get("completed", False),
            participants=data.get("participants", [])
        )

@dataclass
class GuildStats:
    """公会统计数据"""
    total_contribution: int = 0
    total_trades: int = 0
    total_online_time: int = 0
    member_count_history: List[Tuple[float, int]] = field(default_factory=list)
    level_up_history: List[Tuple[float, int]] = field(default_factory=list)

    def to_dict(self):
        return {
            "total_contribution": self.total_contribution,
            "total_trades": self.total_trades,
            "total_online_time": self.total_online_time,
            "member_count_history": self.member_count_history,
            "level_up_history": self.level_up_history
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            total_contribution=data.get("total_contribution", 0),
            total_trades=data.get("total_trades", 0),
            total_online_time=data.get("total_online_time", 0),
            member_count_history=data.get("member_count_history", []),
            level_up_history=data.get("level_up_history", [])
        )

@dataclass
class GuildData:
    """公会完整数据"""
    guild_id: str
    name: str
    owner: str
    level: int = 1
    exp: int = 0
    create_time: float = field(default_factory=time.time)
    base: Optional[GuildBase] = None
    vault: Dict[str, int] = field(default_factory=dict)  # 保留原有仓库格式兼容性
    vault_items: List[VaultItem] = field(default_factory=list)  # 新的仓库物品列表
    custom_item_values: Dict[str, int] = field(default_factory=dict)  # 自定义物品价值
    announcement: str = ""
    members: List[GuildMember] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    purchased_effects: Dict[str, int] = field(default_factory=dict)
    stats: GuildStats = field(default_factory=GuildStats)  # 新增统计数据
    settings: Dict[str, Any] = field(default_factory=dict)  # 公会设置
    tasks: List[GuildTask] = field(default_factory=list)  # 公会任务列表
    
    def add_log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%m-%d %H:%M")
        self.logs.append(f"[{timestamp}] {message}")
        # 保留最近50条日志
        if len(self.logs) > 50:
            self.logs = self.logs[-50:]
    
    def get_member(self, name: str) -> Optional[GuildMember]:
        """获取成员信息"""
        for member in self.members:
            if member.name == name:
                return member
        return None
    
    def has_permission(self, player_name: str, permission: str) -> bool:
        """检查成员权限 - 优化版本"""
        if not player_name or not permission:
            return False

        member = self.get_member(player_name)
        if not member:
            return False

        rank_permissions = Config.PERMISSIONS.get(member.rank.value, [])

        has_perm = "all" in rank_permissions or permission in rank_permissions

        if not has_perm:
            self.add_log(f"权限检查失败: {player_name} 尝试使用 {permission} 权限")

        return has_perm

    def get_member_permissions(self, player_name: str) -> List[str]:
        """获取成员的所有权限列表"""
        member = self.get_member(player_name)
        if not member:
            return []

        return Config.PERMISSIONS.get(member.rank.value, [])

    def can_manage_member(self, manager_name: str, target_name: str) -> bool:
        """检查是否可以管理指定成员"""
        manager = self.get_member(manager_name)
        target = self.get_member(target_name)

        if not manager or not target:
            return False

        if manager_name == target_name:
            return False

        if manager.rank == GuildRank.OWNER:
            return True

        if manager.rank == GuildRank.DEPUTY:
            return target.rank in [GuildRank.ELDER, GuildRank.MEMBER]

        return False

    def get_item_value(self, item_id: str) -> int:
        """获取物品的贡献点价值"""
        # 优先使用自定义价值，否则使用默认价值
        return self.custom_item_values.get(item_id, Config.DEFAULT_ITEM_VALUES.get(item_id, 1))

    def add_vault_item(self, item: VaultItem) -> bool:
        """添加物品到仓库"""
        max_slots = Config.VAULT_INITIAL_SLOTS  # 固定10000格
        if len(self.vault_items) >= max_slots:
            return False
        self.vault_items.append(item)
        return True

    def remove_vault_item(self, index: int) -> Optional[VaultItem]:
        """从仓库移除物品"""
        if 0 <= index < len(self.vault_items):
            return self.vault_items.pop(index)
        return None
    
    def to_dict(self):
        return {
            "guild_id": self.guild_id,
            "name": self.name,
            "owner": self.owner,
            "level": self.level,
            "exp": self.exp,
            "create_time": self.create_time,
            "base": self.base.to_dict() if self.base else None,
            "vault": self.vault,
            "vault_items": [item.to_dict() for item in self.vault_items],
            "custom_item_values": self.custom_item_values,
            "announcement": self.announcement,
            "purchased_effects": self.purchased_effects,
            "members": [m.to_dict() for m in self.members],
            "logs": self.logs,
            "stats": self.stats.to_dict(),
            "settings": self.settings,
            "tasks": [task.to_dict() for task in self.tasks]
        }

    @classmethod
    def from_dict(cls, data, outer_key=None):
        base = None
        try:
            if data.get("base") and isinstance(data["base"], dict):
                base_data = data["base"]
                if all(key in base_data for key in ["dimension", "x", "y", "z"]):
                    base = GuildBase(
                        dimension=base_data["dimension"],
                        x=float(base_data["x"]),
                        y=float(base_data["y"]),
                        z=float(base_data["z"])
                    )
            elif data.get("base"):
                fmts.print_err(f"据点数据格式不正确: {data['base']}")
        except Exception as e:
            fmts.print_err(f"解析据点数据出错: {e}")
            import traceback
            fmts.print_err(traceback.format_exc())

        guild_id = data.get("guild_id")
        if not guild_id:
            guild_id = outer_key if outer_key else uuid.uuid4().hex[:8]

        # 兼容 members 为字符串列表
        members = []
        for m in data.get("members", []):
            if isinstance(m, dict):
                members.append(GuildMember.from_dict(m))
            elif isinstance(m, str):
                members.append(GuildMember(
                    name=m,
                    rank=GuildRank.MEMBER,
                    join_time=time.time()
                ))

        # 处理仓库物品
        vault_items = []
        for item_data in data.get("vault_items", []):
            if isinstance(item_data, dict):
                vault_items.append(VaultItem.from_dict(item_data))

        # 处理统计数据
        stats_data = data.get("stats", {})
        stats = GuildStats.from_dict(stats_data) if isinstance(stats_data, dict) else GuildStats()

        # 处理任务数据
        tasks = []
        for task_data in data.get("tasks", []):
            if isinstance(task_data, dict):
                tasks.append(GuildTask.from_dict(task_data))

        return cls(
            guild_id=guild_id,
            name=data.get("name", ""),
            owner=data.get("owner", ""),
            level=data.get("level", 1),
            exp=data.get("exp", 0),
            create_time=data.get("create_time", time.time()),
            base=base,
            vault=data.get("vault", {}),
            vault_items=vault_items,
            custom_item_values=data.get("custom_item_values", {}),
            announcement=data.get("announcement", ""),
            members=members,
            purchased_effects=data.get("purchased_effects", {}),
            logs=data.get("logs", []),
            stats=stats,
            settings=data.get("settings", {}),
            tasks=tasks
        )
