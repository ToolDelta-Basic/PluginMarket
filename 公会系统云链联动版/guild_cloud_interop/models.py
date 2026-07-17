"""Data models for the guild cloud interop plugin."""

import uuid
import time

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from tooldelta import fmts
from datetime import datetime
from guild_cloud_interop.config import Config

# FIRE 枚举类型 FIRE


class GuildRank(Enum):
    """Guild membership roles."""

    OWNER = "owner"
    DEPUTY = "deputy"
    ELDER = "elder"
    MEMBER = "member"

    @property
    def display_name(self):
        """Return the display name."""
        return {
            "owner": "§c会长",
            "deputy": "§6副会长",
            "elder": "§e长老",
            "member": "§a成员"
        }[self.value]

    @property
    def config_key(self):
        """Return the config key."""
        return {
            "owner": "会长",
            "deputy": "副会长",
            "elder": "长老",
            "member": "成员"
        }[self.value]


PERMISSION_CONFIG_KEYS = {
    "kick": "踢出成员权限",
    "invite": "处理/同意加入公会申请权限",
    "announce": "设置公会公告权限",
    "task_manage": "管理公会任务权限",
    "vault": "公会仓库使用权限",
    "setbase": "设置公会据点权限",
    "return_base": "返回公会据点权限",
    "effect_buy": "购买公会效果权限",
    "vault_settings": "设置仓库物品价值权限",
    "vault_sell": "出售仓库物品权限",
    "vault_buy": "购买仓库物品权限",
    "vault_cancel_own": "撤回自己出售物品权限",
    "vault_cancel_any": "撤回任意仓库物品权限",
    "join_queue": "处理加入申请队列权限",
    "audit_log": "查看审计日志权限",
    "set_rank": "设置成员职位权限",
    "transfer_owner": "转让会长权限",
    "task_create": "创建公会任务权限",
    "task_delete": "删除公会任务权限",
    "task_complete": "强制完成公会任务权限",
}


# FIRE 数据类 FIRE
@dataclass
class GuildBase:
    """公会据点信息"""

    dimension: int
    x: float
    y: float
    z: float

    def to_dict(self):
        """Implement the to dict operation."""
        return {
            "dimension": self.dimension,
            "x": self.x,
            "y": self.y,
            "z": self.z}


@dataclass
class VaultItem:
    """仓库物品信息"""

    item_id: str
    count: int
    price: int  # 贡献点价格
    seller: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        """Implement the to dict operation."""
        return {
            "item_id": self.item_id,
            "count": self.count,
            "price": self.price,
            "seller": self.seller,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data):
        """Implement the from dict operation."""
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
        """Implement the to dict operation."""
        return {
            "name": self.name,
            "rank": self.rank.value,
            "join_time": self.join_time,
            "contribution": self.contribution,
            "last_online": self.last_online
        }

    @classmethod
    def from_dict(cls, data):
        """Implement the from dict operation."""
        return cls(
            name=data["name"],
            rank=GuildRank(data.get("rank", "member")),
            join_time=data.get("join_time", time.time()),
            contribution=data.get("contribution", 0),
            last_online=data.get("last_online", time.time())
        )


@dataclass
class GuildJoinRequest:
    """公会加入申请记录"""

    player_name: str
    reason: str = ""
    create_time: float = field(default_factory=time.time)
    status: str = "pending"
    handler: str = ""
    handle_time: float = 0
    result_reason: str = ""

    def to_dict(self):
        """Implement the to dict operation."""
        return {
            "player_name": self.player_name,
            "reason": self.reason,
            "create_time": self.create_time,
            "status": self.status,
            "handler": self.handler,
            "handle_time": self.handle_time,
            "result_reason": self.result_reason,
        }

    @classmethod
    def from_dict(cls, data):
        """Implement the from dict operation."""
        return cls(
            player_name=data["player_name"],
            reason=data.get("reason", ""),
            create_time=data.get("create_time", time.time()),
            status=data.get("status", "pending"),
            handler=data.get("handler", ""),
            handle_time=data.get("handle_time", 0),
            result_reason=data.get("result_reason", ""),
        )


@dataclass
class VaultTradeLog:
    """公会仓库交易日志"""

    action: str
    item_id: str
    count: int
    price: int
    actor: str
    seller: str = ""
    buyer: str = ""
    timestamp: float = field(default_factory=time.time)
    detail: str = ""

    def to_dict(self):
        """Implement the to dict operation."""
        return {
            "action": self.action,
            "item_id": self.item_id,
            "count": self.count,
            "price": self.price,
            "actor": self.actor,
            "seller": self.seller,
            "buyer": self.buyer,
            "timestamp": self.timestamp,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data):
        """Implement the from dict operation."""
        return cls(
            action=data["action"],
            item_id=data["item_id"],
            count=data.get("count", 0),
            price=data.get("price", 0),
            actor=data.get("actor", ""),
            seller=data.get("seller", ""),
            buyer=data.get("buyer", ""),
            timestamp=data.get("timestamp", time.time()),
            detail=data.get("detail", ""),
        )


@dataclass
class GuildAuditLog:
    """公会审计日志"""

    action: str
    actor: str
    target: str = ""
    detail: str = ""
    result: str = "success"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        """Implement the to dict operation."""
        return {
            "action": self.action,
            "actor": self.actor,
            "target": self.target,
            "detail": self.detail,
            "result": self.result,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data):
        """Implement the from dict operation."""
        return cls(
            action=data["action"],
            actor=data.get("actor", ""),
            target=data.get("target", ""),
            detail=data.get("detail", ""),
            result=data.get("result", "success"),
            timestamp=data.get("timestamp", time.time()),
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
        """Implement the to dict operation."""
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
        """Implement the from dict operation."""
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
        """Implement the to dict operation."""
        return {
            "total_contribution": self.total_contribution,
            "total_trades": self.total_trades,
            "total_online_time": self.total_online_time,
            "member_count_history": self.member_count_history,
            "level_up_history": self.level_up_history
        }

    @classmethod
    def from_dict(cls, data):
        """Implement the from dict operation."""
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
    join_requests: List[GuildJoinRequest] = field(default_factory=list)
    vault_trade_logs: List[VaultTradeLog] = field(default_factory=list)
    audit_logs: List[GuildAuditLog] = field(default_factory=list)

    def add_log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%m-%d %H:%M")
        self.logs.append(f"[{timestamp}] {message}")
        # 保留最近50条日志
        if len(self.logs) > 50:
            self.logs = self.logs[-50:]

    def add_audit_log(
        self,
        action: str,
        actor: str,
        target: str = "",
        detail: str = "",
        result: str = "success",
        now: Optional[float] = None,
    ):
        """添加审计日志"""
        self.audit_logs.append(GuildAuditLog(
            action=action,
            actor=actor,
            target=target,
            detail=detail,
            result=result,
            timestamp=time.time() if now is None else now,
        ))
        max_logs = int(
            getattr(
                Config,
                "GUILD_DATA_SAFETY_CONFIG",
                {}).get(
                "审计日志保留数量",
                200))
        if 0 < max_logs < len(self.audit_logs):
            self.audit_logs = self.audit_logs[-max_logs:]

    def get_member(self, name: str) -> Optional[GuildMember]:
        """获取成员信息"""
        for member in self.members:
            if member.name == name:
                return member
        return None

    def pending_join_requests(
            self,
            now: Optional[float] = None) -> List[GuildJoinRequest]:
        """获取未过期的待处理加入申请"""
        current_time = time.time() if now is None else now
        expire_seconds = int(
            getattr(
                Config,
                "GUILD_JOIN_REQUEST_CONFIG",
                {}).get(
                "申请有效期秒",
                86400))
        return [
            request
            for request in self.join_requests
            if request.status == "pending"
            and (
                expire_seconds <= 0
                or current_time - request.create_time <= expire_seconds
            )
        ]

    def add_join_request(
            self,
            player_name: str,
            reason: str = "",
            now: Optional[float] = None) -> bool:
        """添加离线加入申请"""
        if self.get_member(player_name):
            return False

        current_time = time.time() if now is None else now
        join_config = getattr(Config, "GUILD_JOIN_REQUEST_CONFIG", {})
        max_reason_len = int(join_config.get("申请理由最大长度", 60))
        reason = (reason or "")[:max_reason_len]

        for request in self.pending_join_requests(now=current_time):
            if request.player_name == player_name:
                return False

        max_pending = int(join_config.get("每个公会最多待处理申请数", 30))
        if 0 < max_pending <= len(
            self.pending_join_requests(
                now=current_time)):
            return False

        self.join_requests.append(GuildJoinRequest(
            player_name=player_name,
            reason=reason,
            create_time=current_time,
        ))
        self.add_log(f"{player_name} 提交了加入申请")
        self.add_audit_log("join_request_create", player_name,
                           detail=reason, now=current_time)
        return True

    def resolve_join_request(
        self,
        player_name: str,
        handler: str,
        approved: bool,
        result_reason: str = "",
        now: Optional[float] = None,
    ) -> bool:
        """处理加入申请"""
        current_time = time.time() if now is None else now
        for request in self.pending_join_requests(now=current_time):
            if request.player_name != player_name:
                continue
            request.status = "approved" if approved else "rejected"
            request.handler = handler
            request.handle_time = current_time
            request.result_reason = result_reason
            self.add_log(
                f"{handler} {'批准' if approved else '拒绝'}了 {player_name} 的加入申请")
            self.add_audit_log(
                "join_request_approve" if approved else "join_request_reject",
                handler,
                target=player_name,
                detail=result_reason,
                now=current_time,
            )
            return True
        return False

    def has_permission(self, player_name: str, permission: str) -> bool:
        """检查成员权限 - 优化版本"""
        if not player_name or not permission:
            return False

        member = self.get_member(player_name)
        if not member:
            return False

        rank_permissions = Config.PERMISSIONS.get(member.rank.config_key, {})
        permission_key = PERMISSION_CONFIG_KEYS.get(permission)

        has_perm = (
            isinstance(rank_permissions, dict)
            and permission_key is not None
            and bool(rank_permissions.get(permission_key, False))
        )

        if not has_perm:
            self.add_log(f"权限检查失败: {player_name} 尝试使用 {permission} 权限")

        return has_perm

    def get_member_permissions(self, player_name: str) -> List[str]:
        """获取成员的所有权限列表"""
        member = self.get_member(player_name)
        if not member:
            return []

        rank_permissions = Config.PERMISSIONS.get(member.rank.config_key, {})
        if not isinstance(rank_permissions, dict):
            return []

        return [
            permission
            for permission, config_key in PERMISSION_CONFIG_KEYS.items()
            if bool(rank_permissions.get(config_key, False))
        ]

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
        return self.custom_item_values.get(
            item_id, Config.DEFAULT_ITEM_VALUES.get(item_id, 1))

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

    def add_vault_trade_log(
        self,
        action: str,
        item: VaultItem,
        actor: str,
        buyer: str = "",
        detail: str = "",
        now: Optional[float] = None,
    ):
        """添加仓库交易日志"""
        self.vault_trade_logs.append(VaultTradeLog(
            action=action,
            item_id=item.item_id,
            count=item.count,
            price=item.price,
            actor=actor,
            seller=item.seller,
            buyer=buyer,
            timestamp=time.time() if now is None else now,
            detail=detail,
        ))
        max_logs = int(
            getattr(
                Config,
                "GUILD_VAULT_CONFIG",
                {}).get(
                "交易日志保留数量",
                120))
        if 0 < max_logs < len(self.vault_trade_logs):
            self.vault_trade_logs = self.vault_trade_logs[-max_logs:]

    def cancel_vault_item(
            self,
            actor: str,
            index: int,
            now: Optional[float] = None) -> Optional[VaultItem]:
        """撤回仓库上架物品"""
        item = self.remove_vault_item(index)
        if not item:
            return None

        self.add_vault_trade_log(
            "cancel", item, actor, detail="撤回上架物品", now=now)
        self.add_audit_log("vault_cancel", actor, target=item.seller,
                           detail=item.item_id, now=now)
        self.add_log(
            f"{actor} 撤回了 {item.seller} 上架的 {item.item_id} x{item.count}")
        return item

    def to_dict(self):
        """Implement the to dict operation."""
        return {
            "guild_id": self.guild_id,
            "name": self.name,
            "owner": self.owner,
            "level": self.level,
            "exp": self.exp,
            "create_time": self.create_time,
            "base": self.base.to_dict() if self.base else None,
            "vault": self.vault,
            "vault_items": [
                item.to_dict() for item in self.vault_items],
            "custom_item_values": self.custom_item_values,
            "announcement": self.announcement,
            "purchased_effects": self.purchased_effects,
            "members": [
                m.to_dict() for m in self.members],
            "logs": self.logs,
            "stats": self.stats.to_dict(),
            "settings": self.settings,
            "tasks": [
                task.to_dict() for task in self.tasks],
            "join_requests": [
                request.to_dict() for request in self.join_requests],
            "vault_trade_logs": [
                log.to_dict() for log in self.vault_trade_logs],
            "audit_logs": [
                log.to_dict() for log in self.audit_logs],
        }

    @classmethod
    def from_dict(cls, data, outer_key=None):  # skipcq: PY-R1000
        """Implement the from dict operation."""
        base = None
        try:
            if data.get("base") and isinstance(data["base"], dict):
                base_data = data["base"]
                if all(
                    key in base_data for key in [
                        "dimension",
                        "x",
                        "y",
                        "z"]):
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
        stats = GuildStats.from_dict(stats_data) if isinstance(
            stats_data, dict) else GuildStats()

        # 处理任务数据
        tasks = []
        for task_data in data.get("tasks", []):
            if isinstance(task_data, dict):
                tasks.append(GuildTask.from_dict(task_data))

        join_requests = []
        for request_data in data.get("join_requests", []):
            if isinstance(request_data, dict):
                join_requests.append(GuildJoinRequest.from_dict(request_data))

        vault_trade_logs = []
        for log_data in data.get("vault_trade_logs", []):
            if isinstance(log_data, dict):
                vault_trade_logs.append(VaultTradeLog.from_dict(log_data))

        audit_logs = []
        for log_data in data.get("audit_logs", []):
            if isinstance(log_data, dict):
                audit_logs.append(GuildAuditLog.from_dict(log_data))

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
            tasks=tasks,
            join_requests=join_requests,
            vault_trade_logs=vault_trade_logs,
            audit_logs=audit_logs,
        )
