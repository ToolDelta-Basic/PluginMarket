"""命令路由中间件（权限检查 + 角色系统 + 冷却控制 + 群级模块过滤 + 友好错误提示）。"""
import time
import logging
from ...managers.command_mgr import CommandManager
from ...core.kernel.error_hints import hint
from ..kernel.context import CommandContext


class CommandRouter:
    """将 GroupMessageEvent 分发给匹配的命令，进行权限校验和冷却控制。"""

    def __init__(
        self,
        command_mgr: CommandManager,
        adapter,
        config_mgr,
        message_mgr,
        group_filter=None,
        loaded_modules: dict = None,
        uid_lookup=None,
    ):
        self.command_mgr = command_mgr
        self.adapter = adapter
        self.config_mgr = config_mgr
        self.message_mgr = message_mgr
        self.group_filter = group_filter
        self.loaded_modules = loaded_modules or {}
        self.uid_lookup = uid_lookup
        self._cooldowns: dict[str, dict[int, float]] = {}
        self._cooldown_check_count = 0

    async def handle_message(self, event):
        """处理群消息事件，查找匹配命令并执行。"""
        msg = (event.message or "").strip()
        if not msg:
            return False
        for cmd_info in self.command_mgr.get_group_commands():
            trigger = cmd_info["trigger"]
            if not msg.startswith(trigger):
                continue

            # ── 群级模块/命令过滤 ──
            if self.group_filter:
                module_name = cmd_info.get("plugin", "core")
                if not self.group_filter.is_command_enabled(
                    event.group_id, module_name, trigger
                ):
                    return False  # 静默忽略，不给提示

            # ── 冷却检查 ──
            cooldown = cmd_info.get("cooldown", 0)
            if cooldown > 0:
                now = time.time()
                # 定期清理过期条目（每 100 次检查触发一次）
                if self._cooldown_check_count >= 100:
                    self._cleanup_cooldowns(now)
                    self._cooldown_check_count = 0
                self._cooldown_check_count += 1
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
                    event.handled = True
                    return True

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
                event.handled = True
                return True

            # ── UID 等级检查 ──
            # min_uid > 0 时始终检查（0=root 不限制任何命令）。
            # 当 user_uid > min_uid 时拒绝（数字越小权限越高）。
            min_uid = cmd_info.get("min_uid", 400)
            if self.uid_lookup and min_uid > 0:
                user_uid = self.uid_lookup(event.user_id)
                if user_uid > min_uid:
                    logging.getLogger(__name__).warning(
                        "用户 %d (uid=%d) 尝试执行需要 min_uid=%d 的命令 %s",
                        event.user_id, user_uid, min_uid, trigger,
                    )
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
                        f"\U0001f512 你的 UID ({user_uid}) 不足，"
                        f"该命令需要 UID <= {min_uid}"
                    )
                    event.handled = True
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
                # 执行成功后才记录冷却
                if cooldown > 0:
                    user_cd[event.user_id] = now
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

    def _cleanup_cooldowns(self, now: float):
        """清理过期的冷却条目。"""
        for trigger in list(self._cooldowns):
            user_cd = self._cooldowns[trigger]
            expired = [uid for uid, t in user_cd.items() if now - t > 120]
            for uid in expired:
                del user_cd[uid]
            if not user_cd:
                del self._cooldowns[trigger]

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
