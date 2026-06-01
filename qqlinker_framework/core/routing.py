"""命令路由中间件（权限检查 + 角色系统 + 冷却控制 + 友好错误提示）。"""
import time
import logging
from ..managers.command_mgr import CommandManager
from ..core.error_hints import hint
from .context import CommandContext


class CommandRouter:
    """将 GroupMessageEvent 分发给匹配的命令，进行权限校验和冷却控制。"""

    def __init__(
        self,
        command_mgr: CommandManager,
        adapter,
        config_mgr,
        message_mgr,
    ):
        self.command_mgr = command_mgr
        self.adapter = adapter
        self.config_mgr = config_mgr
        self.message_mgr = message_mgr
        self._cooldowns: dict[str, dict[int, float]] = {}

    async def handle_message(self, event):
        """处理群消息事件，查找匹配命令并执行。"""
        msg = (event.message or "").strip()
        if not msg:
            return False
        for cmd_info in self.command_mgr.get_group_commands():
            trigger = cmd_info["trigger"]
            if not msg.startswith(trigger):
                continue

            # ── 冷却检查 ──
            cooldown = cmd_info.get("cooldown", 0)
            if cooldown > 0:
                now = time.time()
                user_cd = self._cooldowns.setdefault(trigger, {})
                last = user_cd.get(event.user_id, 0)
                if now - last < cooldown:
                    remain = cooldown - (now - last)
                    ctx = CommandContext(
                        user_id=event.user_id,
                        group_id=event.group_id,
                        nickname=event.nickname,
                        message=event.message,
                        args=[],
                        adapter=self.adapter,
                        message_mgr=self.message_mgr,
                    )
                    await ctx.reply(
                        f"⏳ 命令冷却中，请 {remain:.0f} 秒后再试。{hint['COMMAND_COOLDOWN']}"
                    )
                    return True
                user_cd[event.user_id] = now

            # ── 权限检查 ──
            authorized = True
            if cmd_info.get("op_only", False):
                authorized = self.adapter.is_user_admin(event.user_id, self.config_mgr)
            elif required_role := cmd_info.get("required_role"):
                authorized = self._check_role(required_role, event.user_id)

            if not authorized:
                ctx = CommandContext(
                    user_id=event.user_id,
                    group_id=event.group_id,
                    nickname=event.nickname,
                    message=event.message,
                    args=[],
                    adapter=self.adapter,
                    message_mgr=self.message_mgr,
                )
                await ctx.reply(
                    f"🔒 权限不足，该命令仅管理员可用。{hint['COMMAND_PERMISSION_DENIED']}"
                )
                logging.getLogger(__name__).warning(
                    "用户 %d 尝试越权执行命令 %s", event.user_id, trigger,
                )
                return True

            args_str = msg[len(trigger):].strip()
            args = args_str.split() if args_str else []
            ctx = CommandContext(
                user_id=event.user_id,
                group_id=event.group_id,
                nickname=event.nickname,
                message=event.message,
                args=args,
                adapter=self.adapter,
                message_mgr=self.message_mgr,
            )
            try:
                await cmd_info["callback"](ctx)
                event.handled = True
            except Exception as e:
                logging.getLogger(__name__).error(
                    "命令 %s 执行异常: %s。%s",
                    trigger, e, hint['COMMAND_EXEC_FAILED'],
                )
                try:
                    await ctx.reply(
                        f"❌ 命令执行出错。{hint['COMMAND_EXEC_FAILED']}"
                    )
                except Exception:
                    pass
            return True
        return False

    def _check_role(self, role: str, user_id: int) -> bool:
        """检查用户是否属于指定角色。

        角色定义在 config.json 的 [权限管理] 节：
            "权限管理": {
                "管理员": [10000, 10001],
                "moderator": [20000],
                "vip": [30000, 30001]
            }
        每个角色对应一个 QQ 号列表。
        """
        roles = self.config_mgr.get("权限管理.角色", {})
        if not isinstance(roles, dict):
            return False
        allowed = roles.get(role, [])
        if not isinstance(allowed, list):
            return False
        if user_id in allowed:
            return True
        logging.getLogger(__name__).warning(
            "用户 %d 无角色 '%s' 权限", user_id, role
        )
        return False
