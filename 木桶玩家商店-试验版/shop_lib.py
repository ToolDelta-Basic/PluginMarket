from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from tooldelta import Player


class ShopPermission(IntEnum):
    OWNER = 3
    ADMIN = 2
    MEMBER = 1
    OTHER = 0


@dataclass
class Good:
    display_name: str
    structure_id: str
    price: int
    slots_nbt: dict

    @classmethod
    def from_dict(cls, data: dict) -> "Good":
        return cls(
            display_name=data["display_name"],
            structure_id=data["structure_id"],
            price=data["price"],
            slots_nbt=data["slots_nbt"],
        )

    def to_dict(self) -> dict:
        return {
            "display_name": self.display_name,
            "structure_id": self.structure_id,
            "price": self.price,
            "slots_nbt": self.slots_nbt,
        }


@dataclass
class ShopMember:
    name: str
    xuid: str

    @classmethod
    def from_player(cls, player: Player):
        return cls(name=player.name, xuid=player.xuid)

    @classmethod
    def from_dict(cls, data: dict) -> "ShopMember":
        return cls(name=data["name"], xuid=data["xuid"])

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "xuid": self.xuid,
        }

    def __eq__(self, other: "ShopMember"):
        return self.xuid == other.xuid


@dataclass
class ShopRecord:
    type: str
    who: str
    arg: str
    timestr: str = field(default_factory=lambda :datetime.now().strftime("[%m-%d %H:%M]"))

    def string(self):
        return str_record(self.type, self.who, self.arg)

    def marshal(self):
        return f"{self.timestr}::{self.type}::{self.who}::{self.arg}"

    @classmethod
    def unmarshal(cls, c: str):
        if c.count("::") != 3:
            return cls(timestr="ERR", type="日志错误", who="", arg="")
        timestr, type, who, arg = c.split("::", maxsplit=4)
        return cls(timestr=timestr, type=type, who=who, arg=arg)


@dataclass
class Shop:
    name: str
    disp_name: str
    owner: ShopMember
    admins: list[ShopMember]
    members: list[ShopMember]
    description: str
    goods: list[Good]
    profits: float
    records: list[ShopRecord]

    def add_good(self, good: Good):
        self.goods.append(good)

    def remove_good(self, good: Good):
        self.goods.remove(good)

    def add_member(self, member: ShopMember, permission: ShopPermission):
        if permission == ShopPermission.OWNER:
            raise ValueError("无法重新设置店主")
        elif permission == ShopPermission.ADMIN:
            self.admins.append(member)
        elif permission == ShopPermission.MEMBER:
            self.members.append(member)

    def remove_member(self, member: ShopMember):
        if member.xuid == self.owner.xuid:
            raise ValueError("无法移除店主")
        elif member.xuid in [admin.xuid for admin in self.admins]:
            self.admins.remove(member)
        elif member.xuid in [member.xuid for member in self.members]:
            self.members.remove(member)

    def change_permission(self, member: ShopMember, permission: ShopPermission):
        former = self.player_permission(member)
        if former < ShopPermission.MEMBER:
            raise ValueError("无法更改路人权限, 考虑先使其入店")
        if former == ShopPermission.OWNER:
            raise ValueError("店主无法更改权限")
        self -= member
        self.add_member(member, permission)

    def player_permission(self, player: Player | ShopMember):
        xuid = player.xuid
        if xuid == self.owner.xuid:
            return ShopPermission.OWNER
        elif xuid in [admin.xuid for admin in self.admins]:
            return ShopPermission.ADMIN
        elif xuid in [member.xuid for member in self.members]:
            return ShopPermission.MEMBER
        else:
            return ShopPermission.OTHER

    def record_invite(self, inviter: Player, invitee: str):
        self += record_invite(inviter, invitee)

    def record_kick(self, kicker: Player, kickee: str):
        self += record_kick(kicker, kickee)

    def record_buy(self, buyer: Player, good: Good):
        self += record_buy(buyer, good)

    def record_profit_taken(self, operator: Player, amount: float):
        self += record_profit(operator, amount)

    def record_on(self, operator: Player, good: Good):
        self += record_on(operator, good)

    def record_off(self, operator: Player, good: Good):
        self += record_off(operator, good)

    def add_record(self, record: ShopRecord):
        self.records.append(record)
        if len(self.records) > 100:
            self.records.pop(0)

    def has_duplicated_name_good(self, name: str):
        for good in self.goods:
            if good.display_name == name:
                return True
        return False

    @classmethod
    def new(cls, player: Player, name: str):
        return cls(
            name=name,
            disp_name=name,
            owner=ShopMember.from_player(player),
            admins=[],
            members=[],
            description="",
            goods=[],
            profits=0,
            records=[],
        )

    @classmethod
    def from_dict(cls, data: dict) -> "Shop":
        return cls(
            name=data["name"],
            disp_name=data["disp_name"],
            owner=ShopMember.from_dict(data["owner"]),
            admins=[ShopMember.from_dict(admin) for admin in data["admins"]],
            members=[ShopMember.from_dict(member) for member in data["members"]],
            description=data["description"],
            goods=[Good.from_dict(good) for good in data["goods"]],
            profits=data["profits"],
            records=[ShopRecord.unmarshal(record) for record in data["records"]],
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "disp_name": self.disp_name,
            "owner": self.owner.to_dict(),
            "admins": [admin.to_dict() for admin in self.admins],
            "members": [member.to_dict() for member in self.members],
            "description": self.description,
            "goods": [good.to_dict() for good in self.goods],
            "profits": self.profits,
            "records": [record.marshal() for record in self.records],
        }

    def __iadd__(self, other: Good | ShopMember | ShopRecord | float):
        print("iadd", other)
        if isinstance(other, Good):
            self.add_good(other)
        elif isinstance(other, ShopMember):
            self.add_member(other, ShopPermission.MEMBER)
        elif isinstance(other, float | int):
            self.profits += other
        elif isinstance(other, ShopRecord):
            self.add_record(other)
        return self

    def __isub__(self, other: Good | ShopMember | float):
        if isinstance(other, Good):
            self.remove_good(other)
        elif isinstance(other, ShopMember):
            self.remove_member(other)
        elif isinstance(other, float):
            self.profits -= other
        return self

    def __iter__(self):
        return iter(self.goods)


@dataclass
class ShopPlayerInfo:
    xuid: str
    in_shop_name: str

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            xuid=data["xuid"],
            in_shop_name=data["in_shop_name"],
        )

    def to_dict(self):
        return {
            "xuid": self.xuid,
            "in_shop_name": self.in_shop_name,
        }


def str_record(type: str, who: str, arg: str):
    if type == "on":
        return f"{who} §7上架了商品 §f{arg}"
    elif type == "off":
        return f"{who} §7下架了商品 §f{arg}"
    elif type == "buy":
        return f"{who} §7购买了商品 §f{arg}"
    elif type == "invite":
        return f"{who} §7邀请了店员 §f{arg}"
    elif type == "kick":
        return f"{who} §7移除了店员 §f{arg}"
    elif type == "profit":
        return f"{who} §7提取利润 §f{arg}"
    else:
        return f"错误记录 {type}:{who}:{arg}"


def record_buy(buyer: Player, good: Good):
    return ShopRecord(type="buy", who=buyer.name, arg=good.display_name)


def record_on(operator: Player, good: Good):
    return ShopRecord(type="on", who=operator.name, arg=good.display_name)


def record_off(operator: Player, good: Good):
    return ShopRecord(type="off", who=operator.name, arg=good.display_name)


def record_invite(inviter: Player, invitee: str):
    return ShopRecord(type="invite", who=inviter.name, arg=invitee)


def record_kick(kicker: Player, kickee: str):
    return ShopRecord(type="kick", who=kicker.name, arg=kickee)


def record_profit(operator: Player, amount: float):
    return ShopRecord(type="profit", who=operator.name, arg=str(amount))
