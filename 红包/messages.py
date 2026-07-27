"""红包聊天文案和 tellraw 序列化。"""

from __future__ import annotations

import json

from .models import RedPacket


def created_message(packet: RedPacket, currency_name: str) -> str:
    return (
        "§c§l------->>抢红包<<-------§r\n"
        f"§f玩家 §b{packet.sender_name} §f发送了价值 "
        f"§6§l{packet.total_amount} {currency_name}§r§f 的红包\n"
        f"§f 发送口令 §a§l「{packet.phrase}」§r§f 领取\n"
        "§c----------------------------§r"
    )


def claim_message(
    claimant_name: str,
    sender_name: str,
    amount: int,
    currency_name: str,
) -> str:
    return (
        f"§f玩家 §a§l{claimant_name}§r§f 从 §b{sender_name} "
        f"§f的红包中抢到了 §6§l{amount} {currency_name}§r"
    )


def completed_message(packet: RedPacket, currency_name: str) -> str:
    return (
        f"§f玩家 §b{packet.sender_name} §f发送的红包被抢完，"
        f"§a§l{packet.best_claimant_name}§r§f 是手气最佳，抢到了 "
        f"§6§l{packet.best_claim_amount} {currency_name}§r"
    )


def refund_message(packet: RedPacket, currency_name: str) -> str:
    packet_label = (
        f"红包「{packet.phrase}」"
        if packet.has_valid_phrase()
        else "含无效字符的红包"
    )
    return (
        f"§e{packet_label} 已过期，剩余 "
        f"§6§l{packet.remaining_amount} {currency_name}§r§e 已退回§r"
    )


def tellraw_payload(message: str) -> str:
    return json.dumps(
        {"rawtext": [{"text": message}]},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def is_red_packet_command(message: str) -> bool:
    lowered = message.casefold()
    return lowered == ".fhb" or lowered.startswith(".fhb ") or (
        message == ".发红包"
        or message.startswith(".发红包 ")
        or message == "。发红包"
        or message.startswith("。发红包 ")
        or lowered == "。fhb"
        or lowered.startswith("。fhb ")
    )
