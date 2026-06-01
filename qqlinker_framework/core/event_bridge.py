"""事件桥接模块 — 游戏→QQ 事件分发 + OneBot 消息解析。

从 FrameworkHost 拆分出来，聚焦事件转换与分发。
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from .events import (
    GameChatEvent, PlayerJoinEvent, PlayerLeaveEvent, GroupMessageEvent,
)
from .defguard import validate_onebot_event
from .error_hints import hint

if TYPE_CHECKING:
    from .host import FrameworkHost

access_log = logging.getLogger("access")
_log = logging.getLogger(__name__)


class EventBridge:
    """将游戏侧和 QQ 侧事件桥接到 EventBus。"""

    def __init__(self, host: "FrameworkHost"):
        self.host = host

    # ── 游戏侧 → 事件总线 ──

    def on_game_chat(self, player_name: str, message: str):
        """游戏聊天 → GameChatEvent。"""
        self._publish(
            GameChatEvent(player_name=player_name, message=message),
            "游戏聊天事件桥接")

    def on_player_join(self, player_name: str):
        """玩家加入 → PlayerJoinEvent。"""
        self._publish(
            PlayerJoinEvent(player_name=player_name),
            "玩家加入事件桥接")

    def on_player_leave(self, player_name: str):
        """玩家离开 → PlayerLeaveEvent。"""
        self._publish(
            PlayerLeaveEvent(player_name=player_name),
            "玩家离开事件桥接")

    def _publish(self, event, label: str):
        """线程安全地发布事件到主循环。"""
        host = self.host
        if host._main_loop and host._main_loop.is_running():  # noqa: PYL-W0212
            try:
                asyncio.run_coroutine_threadsafe(
                    host.event_bus.publish(event), host._main_loop,
                )
            except Exception as e:
                logging.getLogger(__name__).error(
                    "%s失败: %s。%s", label, e, hint["EVENT_HANDLER_FAILED"],
                )

    # ── QQ 侧 → 事件总线 ──

    def on_ws_group_message(self, raw: dict):
        """处理 WebSocket 群消息：验证→过滤→去重→发布。"""
        ok, data, reason = validate_onebot_event(raw)
        if not ok:
            _log.debug("丢弃无效 WS 消息: %s", reason)
            return

        host = self.host
        linked_groups = host.config_mgr.get("消息转发.链接的群聊", [])
        group_id = data["group_id"]
        if group_id not in linked_groups:
            return

        msg_id = data.get("message_id")
        if msg_id and not host.dedup.check_and_add_id(f"raw_{msg_id}"):
            return

        text = data["message"]
        nickname = data["nickname"]
        access_log.info("[QQ] %s: %s", nickname, text.strip())

        # 触发原始消息处理器（给适配器用）
        try:
            trigger = getattr(host.adapter, "trigger_raw_group_handlers", None)
            if trigger:
                trigger(data["_raw"])
        except Exception as e:
            _log.error("原始消息处理器异常: %s。%s", e, hint["EVENT_HANDLER_FAILED"])

        event = GroupMessageEvent(
            user_id=data["user_id"],
            group_id=group_id,
            nickname=nickname,
            message=text.strip(),
            raw_data=data["_raw"],
        )
        if host._main_loop and host._main_loop.is_running():  # noqa: PYL-W0212
            asyncio.run_coroutine_threadsafe(
                host.event_bus.publish(event), host._main_loop,
            )

    @staticmethod
    def parse_onebot_message(raw_msg) -> str:
        """解析 OneBot 消息段列表为纯文本。"""
        if isinstance(raw_msg, list):
            parts = []
            for seg in raw_msg:
                if seg.get("type") == "text":
                    parts.append(seg["data"].get("text", ""))
                elif seg.get("type") == "at":
                    qq = seg["data"].get("qq")
                    parts.append(f"[@{qq}]" if qq != "all" else "[@全体成员]")
                else:
                    parts.append(f"[{seg.get('type')}]")
            return "".join(parts)
        return str(raw_msg) if raw_msg else ""
