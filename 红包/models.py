"""红包领域模型和纯计算函数。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from random import Random
from typing import Any

from .text_validation import has_invalid_characters


MAX_SCORE = 2_147_483_647


@dataclass(frozen=True)
class RedPacketRequest:
    """玩家创建红包时已经校验过的参数。"""

    total_amount: int
    total_count: int
    phrase: str

    def has_valid_phrase(self) -> bool:
        """检查创建请求中的口令是否安全。"""
        return (
            1 <= len(self.phrase) <= 32
            and not any(character.isspace() for character in self.phrase)
            and not has_invalid_characters(self.phrase)
        )


@dataclass
class RedPacket:
    """一个尚未完成退款或领取的红包。"""

    packet_id: str
    sender_name: str
    sender_key: str
    total_amount: int
    remaining_amount: int
    total_count: int
    remaining_count: int
    phrase: str
    is_public: bool
    claimed_keys: list[str] = field(default_factory=list)
    best_claimant_name: str = ""
    best_claim_amount: int = 0
    created_at: float = 0.0
    expires_at: float = 0.0
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        """转换为可持久化字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RedPacket":
        """从持久化字典恢复并校验红包。"""
        packet = cls(
            packet_id=str(data["packet_id"]),
            sender_name=str(data["sender_name"]),
            sender_key=str(data["sender_key"]),
            total_amount=int(data["total_amount"]),
            remaining_amount=int(data["remaining_amount"]),
            total_count=int(data["total_count"]),
            remaining_count=int(data["remaining_count"]),
            phrase=str(data["phrase"]),
            is_public=bool(data["is_public"]),
            claimed_keys=[str(item) for item in data.get("claimed_keys", [])],
            best_claimant_name=str(data.get("best_claimant_name", "")),
            best_claim_amount=int(data.get("best_claim_amount", 0)),
            created_at=float(data["created_at"]),
            expires_at=float(data["expires_at"]),
            status=str(data.get("status", "active")),
        )
        unsafe_phrase = not packet.has_valid_phrase()
        packet.validate(allow_unsafe_phrase=unsafe_phrase)
        if unsafe_phrase:
            packet.status = "refund_pending"
        return packet

    def has_valid_phrase(self) -> bool:
        """检查持久化红包口令是否安全。"""
        return (
            1 <= len(self.phrase) <= 32
            and not any(character.isspace() for character in self.phrase)
            and not has_invalid_characters(self.phrase)
        )

    def validate(self, allow_unsafe_phrase: bool = False) -> None:
        """校验红包金额、份数、口令和状态。"""
        if not self.packet_id or not self.sender_name or not self.sender_key:
            raise ValueError("红包身份信息不完整")
        if self.total_amount < 1 or self.total_amount > MAX_SCORE:
            raise ValueError("红包总金额无效")
        if self.total_count < 1 or self.total_count > self.total_amount:
            raise ValueError("红包总份数无效")
        if not 0 <= self.remaining_amount <= self.total_amount:
            raise ValueError("红包剩余金额无效")
        if not 0 <= self.remaining_count <= self.total_count:
            raise ValueError("红包剩余份数无效")
        if not 0 <= self.best_claim_amount <= self.total_amount:
            raise ValueError("红包手气最佳金额无效")
        if bool(self.best_claimant_name) != bool(self.best_claim_amount):
            raise ValueError("红包手气最佳信息不完整")
        if not allow_unsafe_phrase and not self.has_valid_phrase():
            raise ValueError("红包口令无效")
        if self.status not in {"active", "refund_pending"}:
            raise ValueError("红包状态无效")


@dataclass
class RedPacketState:
    """需要持久化的全部红包状态。"""

    packets: dict[str, RedPacket] = field(default_factory=dict)
    refund_notices: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换全部红包状态为持久化字典。"""
        return {
            "format_version": 1,
            "packets": [
                packet.to_dict() for packet in self.packets.values()
            ],
            "refund_notices": self.refund_notices,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RedPacketState":
        """从持久化字典恢复全部红包状态。"""
        if int(data.get("format_version", 0)) != 1:
            raise ValueError("不支持的红包数据版本")
        packets = {}
        for raw_packet in data.get("packets", []):
            packet = RedPacket.from_dict(raw_packet)
            if packet.packet_id in packets:
                raise ValueError("存在重复的红包 ID")
            packets[packet.packet_id] = packet
        notices = {
            str(key): [str(message) for message in messages]
            for key, messages in data.get("refund_notices", {}).items()
        }
        return cls(packets=packets, refund_notices=notices)


def choose_lucky_amount(
    remaining_amount: int,
    remaining_count: int,
    rng: Random,
) -> int:
    """使用双均值法抽取一份，并保证每个剩余红包至少有 1。"""
    if remaining_count < 1 or remaining_amount < remaining_count:
        raise ValueError("红包剩余金额和份数不合法")
    if remaining_count == 1:
        return remaining_amount
    guaranteed_max = remaining_amount - (remaining_count - 1)
    double_mean = max(1, (remaining_amount * 2) // remaining_count)
    return rng.randint(1, min(guaranteed_max, double_mean))


def player_identity(player: Any) -> str:
    """获取跨重启尽量稳定的玩家身份键。"""
    for prefix, attribute in (("xuid", "xuid"), ("uuid", "uuid")):
        value = str(getattr(player, attribute, "") or "").strip()
        if value:
            return f"{prefix}:{value}"
    return f"name:{str(getattr(player, 'name', player))}"
