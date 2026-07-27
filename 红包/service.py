"""红包创建、领取和退款业务。"""

from __future__ import annotations

import random
import threading
import time
import uuid
from typing import Any

from .economy import ScoreboardEconomy
from .messages import refund_message
from .models import (
    RedPacket,
    RedPacketRequest,
    RedPacketState,
    choose_lucky_amount,
    player_identity,
)
from .storage import RedPacketStore


class RedPacketService:
    """串行处理所有会改变红包或计分板余额的操作。"""

    def __init__(
        self,
        plugin: Any,
        store: RedPacketStore,
        state: RedPacketState,
        rng: random.Random | None = None,
    ) -> None:
        self.plugin = plugin
        self.store = store
        self.state = state
        self.rng = rng or random.SystemRandom()
        self.lock = threading.RLock()
        self.economy = ScoreboardEconomy(plugin)

    def has_active_phrase(self, phrase: str) -> bool:
        with self.lock:
            return self._find_active(phrase) is not None

    def create(self, player: Any, request: RedPacketRequest) -> bool:
        with self.lock:
            if not request.has_valid_phrase():
                player.show("§c禁止使用无效字符§r")
                return False
            if self._find_active(request.phrase) is not None:
                player.show("§e这个口令已有未结束的红包，请换一个口令§r")
                return False
            balance = self.economy.get_balance(player)
            if balance is None:
                return False
            if balance < request.total_amount:
                currency = self.plugin.currency_name
                player.show(
                    f"§c余额不足：需要 §6{request.total_amount} {currency}"
                    f"§c，你只有 §6{balance} {currency}§r"
                )
                return False
            if not self.economy.change_score(
                player.safe_name,
                -request.total_amount,
            ):
                player.show("§c扣除余额失败，红包没有创建，请稍后重试§r")
                return False
            now = time.time()
            packet = RedPacket(
                packet_id=uuid.uuid4().hex,
                sender_name=player.name,
                sender_key=player_identity(player),
                total_amount=request.total_amount,
                remaining_amount=request.total_amount,
                total_count=request.total_count,
                remaining_count=request.total_count,
                phrase=request.phrase,
                is_public=True,
                created_at=now,
                expires_at=now + self.plugin.expiry_seconds,
            )
            self.state.packets[packet.packet_id] = packet
            if not self._save():
                self.state.packets.pop(packet.packet_id, None)
                refunded = self.economy.change_score(
                    player.safe_name,
                    request.total_amount,
                )
                message = (
                    "§c红包数据保存失败，金额已退回§r"
                    if refunded
                    else "§c红包数据保存和自动退款均失败，请立即联系管理员§r"
                )
                player.show(message)
                return False
            self.plugin.broadcast_created(packet)
            return True

    def claim(self, player: Any, phrase: str) -> bool:
        with self.lock:
            packet = self._find_active(phrase)
            if packet is None:
                return False
            claimant_key = player_identity(player)
            if claimant_key in packet.claimed_keys:
                player.show("§e你已经领取过这个红包了§r")
                return True
            amount = choose_lucky_amount(
                packet.remaining_amount,
                packet.remaining_count,
                self.rng,
            )
            if not self.economy.change_score(player.safe_name, amount):
                player.show("§c红包领取失败，金额没有被消耗，请稍后重试§r")
                return True
            packet.remaining_amount -= amount
            packet.remaining_count -= 1
            packet.claimed_keys.append(claimant_key)
            if amount > packet.best_claim_amount:
                packet.best_claimant_name = player.name
                packet.best_claim_amount = amount
            completed = packet.remaining_count == 0
            if completed:
                self.state.packets.pop(packet.packet_id, None)
            if not self._save():
                self.plugin.print_err(
                    f"玩家 {player.name} 已领取红包，但红包状态保存失败"
                )
            self.plugin.broadcast_claim(player.name, packet.sender_name, amount)
            if completed:
                self.plugin.broadcast_completed(packet)
            return True

    def process_expired(self, now: float | None = None) -> None:
        current_time = time.time() if now is None else now
        with self.lock:
            changed = False
            for packet in self.state.packets.values():
                if packet.status == "active" and packet.expires_at <= current_time:
                    packet.status = "refund_pending"
                    changed = True
            if changed:
                self._save()
            for packet in list(self.state.packets.values()):
                if packet.status == "refund_pending":
                    self._try_refund(packet)

    def deliver_refund_notices(self, player: Any) -> None:
        key = player_identity(player)
        with self.lock:
            messages = self.state.refund_notices.pop(key, [])
            if not messages:
                return
            if not self._save():
                self.state.refund_notices[key] = messages
                return
        for message in messages:
            player.show(message)

    def _try_refund(self, packet: RedPacket) -> None:
        online_player = self.economy.find_online_player(packet.sender_key)
        target = (
            online_player.safe_name
            if online_player is not None
            else self.economy.quoted_name(packet.sender_name)
        )
        if not self.economy.change_score(target, packet.remaining_amount):
            self.plugin.print_war(
                f"红包 {packet.packet_id} 退款失败，稍后将自动重试"
            )
            return
        message = refund_message(packet, self.plugin.currency_name)
        self.state.packets.pop(packet.packet_id, None)
        if online_player is not None:
            online_player.show(message)
        else:
            self.state.refund_notices.setdefault(packet.sender_key, []).append(
                message
            )
        if not self._save():
            self.plugin.print_err(
                f"红包 {packet.packet_id} 已退款，但状态保存失败"
            )

    def _find_active(self, phrase: str) -> RedPacket | None:
        for packet in self.state.packets.values():
            if packet.status == "active" and packet.phrase == phrase:
                return packet
        return None

    def _save(self) -> bool:
        try:
            self.store.save(self.state)
            return True
        except Exception as err:
            self.plugin.print_err(f"保存红包数据失败: {err}")
            return False
