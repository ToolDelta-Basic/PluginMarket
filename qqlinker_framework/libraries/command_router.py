"""命令路由库 — 信道实现。

订阅 GroupMessageEvent，匹配注册的命令并分发执行。
支持子命令匹配、冷却、权限检查。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from ..core.channel import ChannelEvent, Library

_log = logging.getLogger(__name__)


# ── 事件类型 ──────────────────────────────────────────────────

@dataclass
class GroupMessageEvent(ChannelEvent):
    """群消息事件。由适配器桥接库发布。"""
    user_id: int = 0
    group_id: int = 0
    nickname: str = ""
    message: str = ""
    raw_data: dict = field(default_factory=dict)


# ── 命令上下文 ────────────────────────────────────────────────

class CommandContext:
    """简化的命令上下文。

    传递给命令回调的参数对象。
    提供 reply() 便捷方法。
    """
    __slots__ = ("user_id", "group_id", "nickname", "message", "args", "_messages")

    def __init__(self, *, user_id, group_id, nickname, message, args, messages):
        self.user_id = user_id
        self.group_id = group_id
        self.nickname = nickname
        self.message = message
        self.args = args
        self._messages = messages

    async def reply(self, text: str):
        """回复消息到群。

        Args:
            text: 回复的文本内容。
        """
        if self._messages:
            await self._messages.send_group(self.group_id, text)


# ── 命令路由器 ────────────────────────────────────────────────

class CommandRouterLibrary(Library):
    """命令路由库。

    订阅 GroupMessageEvent，将 `.` 开头的消息分发给注册的命令。

    依赖 message_bus（提供 command 注册表）和 config_source（提供管理员列表）。
    """

    name = "command_router"
    version = "1.0.0"
    dependencies = ["core", "message_bus"]

    async def mount(self):
        self._cooldowns: dict = {}
        self.events.subscribe("GroupMessageEvent", self._on_message, priority=50)

    async def unmount(self):
        self.events.unsubscribe("GroupMessageEvent", self._on_message)

    async def _on_message(self, event: GroupMessageEvent):
        msg = (event.message or "").strip()
        if not msg.startswith("."):
            return

        # 获取命令注册表
        cmd_registry = self.services.try_get("command")
        if not cmd_registry:
            return

        # 获取管理员列表
        config = self.services.try_get("config")
        admins = config.get("管理员.管理员QQ", []) if config else []

        # 触发词 = 第一个空格前的部分
        space_idx = msg.find(" ")
        if space_idx == -1:
            trigger = msg
            args = []
        else:
            trigger = msg[:space_idx]
            args = msg[space_idx + 1:].split()

        # 精确匹配 → 回退子命令匹配
        cmd_info = cmd_registry.find(trigger)
        if cmd_info is None:
            # 子命令匹配：例如 ".规则 创建" 匹配 trigger=".规则"
            cmd_info = cmd_registry.find(trigger.split()[0] if " " in msg else msg)
        if cmd_info is None:
            return

        # 冷却检查
        cooldown = cmd_info.get("cooldown", 0)
        if cooldown > 0:
            now = time.time()
            key = (event.user_id, trigger)
            last = self._cooldowns.get(key, 0)
            if now - last < cooldown:
                return
            self._cooldowns[key] = now

        # 权限检查
        if cmd_info.get("op_only") and event.user_id not in admins:
            _log.warning("用户 %d 尝试越权执行 %s", event.user_id, trigger)
            return

        # 构造上下文
        ctx = CommandContext(
            user_id=event.user_id,
            group_id=event.group_id,
            nickname=event.nickname,
            message=event.message,
            args=args,
            messages=self.messages,
        )

        # 执行回调
        try:
            callback = cmd_info["callback"]
            if asyncio.iscoroutinefunction(callback):
                await callback(ctx)
            else:
                callback(ctx)
        except Exception as e:
            _log.error("命令 %s 执行异常: %s", trigger, e)
