"""事件路由库 — 订阅 GroupMessageEvent → 命令匹配 → 分发执行。

依赖: command_registry, message_queue, adapter_bridge
"""
import asyncio
import logging
from typing import Optional

from ..channel_host import Library

_log = logging.getLogger(__name__)


class CommandContext:
    """命令执行上下文。"""

    __slots__ = ("user_id", "group_id", "nickname", "message", "args",
                 "_message_queue", "raw_data")

    def __init__(self, *, user_id, group_id, nickname, message, args,
                 message_queue, raw_data=None):
        self.user_id = user_id
        self.group_id = group_id
        self.nickname = nickname
        self.message = message
        self.args = args
        self._message_queue = message_queue
        self.raw_data = raw_data or {}

    async def reply(self, text: str) -> None:
        """回复消息到群。"""
        if self._message_queue:
            await self._message_queue.send_group(self.group_id, text)


class EventRouterLibrary(Library):
    """事件路由库 — 命令分发。"""

    name = "event_router"
    version = "1.6.0"
    dependencies = ["command_registry", "message_queue", "adapter_bridge"]

    async def mount(self) -> None:
        # 注册交互式会话追踪器（轮式对话支持）
        if self.services.try_get("session_tracker") is None:
            from ...core.kernel.services import InteractiveSessionTracker
            tracker = InteractiveSessionTracker()
            self.services.register("session_tracker", tracker, mid=300)
        self.events.subscribe("GroupMessageEvent", self._on_group_message, priority=50)

    async def unmount(self) -> None:
        self.events.unsubscribe("GroupMessageEvent", self._on_group_message)

    async def _on_group_message(self, event) -> None:
        """处理群消息事件 — 命令路由。

        尊重轮式对话：若用户处于交互式会话且 capture_command=True，
        跳过命令路由，让消息直接流向模块的 @listen 处理器。
        """
        msg = (event.message or "").strip()
        if not msg:
            return

        # 轮式对话检查：若用户在交互式会话中，跳过命令路由
        tracker = self.services.try_get("session_tracker")
        if tracker is not None:
            session = None
            if hasattr(tracker, 'get_session'):
                session = tracker.get_session(event.user_id)
            elif hasattr(tracker, 'is_active') and tracker.is_active(event.user_id):
                session = {"capture_command": True}
            if session and session.get("capture_command", True):
                # 用户在交互式会话中，不做命令路由
                if hasattr(tracker, 'touch'):
                    tracker.touch(event.user_id)
                return

        command_mgr = self.services.try_get("command")
        if not command_mgr:
            return

        # 最长匹配
        cmd_info = command_mgr.find_best_match(msg)
        if cmd_info is None:
            return

        trigger = cmd_info["trigger"]

        # 冷却检查
        cooldown = cmd_info.get("cooldown", 0)
        if not command_mgr.check_cooldown(event.user_id, trigger, cooldown):
            return

        # 权限检查
        if cmd_info.get("op_only"):
            config = self.services.try_get("config")
            admins = config.get("管理员.管理员QQ", []) if config else []
            if event.user_id not in admins:
                return

        # 解析参数
        rest = msg[len(trigger):].strip()
        args = rest.split() if rest else []

        # 构造上下文
        message_queue = self.services.try_get("message")
        ctx = CommandContext(
            user_id=event.user_id,
            group_id=event.group_id,
            nickname=event.nickname,
            message=msg,
            args=args,
            message_queue=message_queue,
            raw_data=event.raw_data,
        )

        # 执行回调
        callback = cmd_info["callback"]
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(ctx)
            else:
                callback(ctx)
            # 命令执行成功，标记事件已处理，阻止后续 handler 重复处理
            event.handled = True
        except Exception as e:
            _log.error("命令 '%s' 执行异常: %s", trigger, e, exc_info=True)
