"""红包全服公告发送。"""

from __future__ import annotations

from typing import Any

from .messages import (
    claim_message,
    completed_message,
    created_message,
    tellraw_payload,
)
from .models import RedPacket


class RedPacketBroadcastMixin:
    """为红包插件提供全服公告方法。"""

    currency_name: str
    game_ctrl: Any

    def broadcast_created(self, packet: RedPacket) -> None:
        """广播新创建的红包。"""
        self._broadcast_raw(created_message(packet, self.currency_name))

    def broadcast_claim(
        self,
        claimant_name: str,
        sender_name: str,
        amount: int,
    ) -> None:
        """广播玩家领取红包的结果。"""
        self._broadcast_raw(
            claim_message(
                claimant_name,
                sender_name,
                amount,
                self.currency_name,
            )
        )

    def broadcast_completed(self, packet: RedPacket) -> None:
        """广播红包抢完及手气最佳结果。"""
        self._broadcast_raw(completed_message(packet, self.currency_name))

    def _broadcast_raw(self, message: str) -> None:
        """安全序列化并向全服发送消息。"""
        self.game_ctrl.sendwocmd(f"/tellraw @a {tellraw_payload(message)}")
