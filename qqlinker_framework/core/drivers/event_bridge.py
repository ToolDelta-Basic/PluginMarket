"""事件桥接模块 — 游戏→QQ 事件分发 + OneBot 消息解析。

从 FrameworkHost 拆分出来，聚焦事件转换与分发。
不持有 FrameworkHost 引用，通过独立参数解耦。
"""
import asyncio
import logging
from typing import Callable, Optional

from ..kernel.events import (
    GameChatEvent, PlayerJoinEvent, PlayerLeaveEvent, GroupMessageEvent,
)
from ..kernel.defguard import validate_onebot_event
from ..kernel.error_hints import hint
from ..kernel.bus import EventBus

access_log = logging.getLogger("access")
_log = logging.getLogger(__name__)


class EventBridge:
    """将游戏侧和 QQ 侧事件桥接到 EventBus。

    通过独立参数接收依赖，不持有 FrameworkHost 引用:
        - event_bus: 事件总线
        - config_mgr: 配置管理器（用于读取链接的群聊等）
        - dedup: 消息去重引擎
        - main_loop_getter: 返回当前主事件循环的可调用对象
        - adapter: 框架适配器（用于触发原始消息处理器）
    """

    def __init__(
        self,
        event_bus: EventBus,
        config_mgr,
        dedup,
        main_loop_getter: Callable[[], Optional[asyncio.AbstractEventLoop]],
        adapter,
    ):
        self.event_bus = event_bus
        self.config_mgr = config_mgr
        self.dedup = dedup
        self.main_loop_getter = main_loop_getter
        self.adapter = adapter

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
        loop = self.main_loop_getter()
        if loop and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    self.event_bus.publish(event), loop,
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
        if data.get("post_type") != "message":
            return

        linked_groups = self.config_mgr.get("消息转发.链接的群聊", [], requester_uid=0)
        group_id = data["group_id"]
        if group_id not in linked_groups:
            return

        # 分层去重
        text = data["message"]
        stripped = text.strip()

        # ── Layer 1: 翻页导航字符 — 永不拦截 ──
        if stripped in ("+", "-", "q", "Q"):
            pass  # 直接跳过一切去重

        # ── Layer 2: 命令消息 — 短 TTL 专用去重 (5s) ──
        elif stripped.startswith("."):
            from ..kernel.defguard import safe_int
            user_id = safe_int(data.get("user_id", 0), 0)
            logic_id = f"cmd_{group_id}_{user_id}_{text[:30]}"
            if self.dedup and not self.dedup.check_and_add_command(logic_id):
                return

        # ── Layer 3: 普通消息 — 标准去重 ──
        else:
            from .robot_guard import CrossValidation
            from ..kernel.defguard import safe_int
            raw_time = safe_int(data.get("time", 0), 0)
            logic_id = CrossValidation.content_id(data)
            if self.dedup and not self.dedup.check_and_add_id(f"raw_{raw_time}_{logic_id}"):
                return

        nickname = data["nickname"]
        access_log.info("[QQ] %s: %s", nickname, text.strip())

        # 触发原始消息处理器（给适配器用）
        try:
            trigger = getattr(self.adapter, "trigger_raw_group_handlers", None)
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
        loop = self.main_loop_getter()
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.event_bus.publish(event), loop,
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
