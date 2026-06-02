"""内核授权模块 — .grant 授权 UID、.exec 调用模块方法（root 独占）。

uid=0 (root) — 只能由框架内核加载，不通过模块市场分发。
"""
import logging
from ...core.module import Module
from ...core.decorators import command
from ...core.services import uid_label, UID_ROOT, UID_DAEMON_MIN, UID_SERVICE_MIN, UID_NOBODY

_log = logging.getLogger(__name__)


class KernelAuthModule(Module):
    """内核级授权模块。uid=0，仅 root 用户可触发。"""

    name = "kernel_auth"
    uid = 0  # root: 框架内核
    version = (1, 0, 0)
    required_services = ["config", "message"]

    async def on_init(self):
        """初始化：注册命令（装饰器自动扫描）。"""

    # ── 命令 ──

    @command(".grant", description="授权用户 UID 等级（root only）",
             argument_hint="<QQ号> [uid等级]", min_uid=0)
    async def cmd_grant(self, ctx):
        """root 授权用户到指定 UID 等级。

        用法: .grant 12345 2000   (授予用户级)
              .grant 12345 1000   (授予系统级)
              .grant 12345 0      (授予内核级)
        """
        caller_uid = self._get_user_uid(ctx.user_id)
        if caller_uid > UID_ROOT:
            await ctx.reply(f"\u274c 仅 root(0) 可使用此命令。你的 UID: {caller_uid}")
            return

        if len(ctx.args) < 1:
            await ctx.reply("用法: .grant <QQ号> [uid等级]\n"
                            "等级: 100=daemon, 1000=service, 2000=app(默认), 3000=nobody")
            return

        try:
            target_qq = int(ctx.args[0])
        except ValueError:
            await ctx.reply("\u274c QQ号格式错误")
            return

        new_uid = UID_NOBODY
        if len(ctx.args) >= 2:
            try:
                new_uid = int(ctx.args[1])
            except ValueError:
                await ctx.reply("\u274c UID等级格式错误")
                return

        if new_uid < 0 or new_uid >= UID_NOBODY + 10000:
            await ctx.reply(f"\u274c 无效的 UID 等级: {new_uid}\n"
                            f"有效范围: 0=内核, 100=守护, 1000=系统, 2000=用户")
            return

        # root 可以授予任意 uid（包括 root）
        self._set_user_uid(target_qq, new_uid)
        label = uid_label(new_uid)

        if new_uid <= 100:
            self._ensure_admin(target_qq)
            await ctx.reply(
                f"\u2705 用户 {target_qq} 已授权为: UID {new_uid} ({label})，"
                f"并已加入管理员列表"
            )
        elif new_uid >= UID_NOBODY:
            self._remove_admin(target_qq)
            await ctx.reply(
                f"\u2705 用户 {target_qq} 已降级为: UID {new_uid} ({label})"
            )
        else:
            await ctx.reply(
                f"\u2705 用户 {target_qq} 已授权为: UID {new_uid} ({label})"
            )

    @command(".exec", description="root 直接调用模块方法",
             argument_hint="<模块.方法> [参数...]", min_uid=0)
    async def cmd_exec(self, ctx):
        """root 直接调用任意已加载模块的任意方法。

        用法: .exec <模块名.方法名> [参数...]
        例如: .exec auth.cmd_uid
              .exec config_repair.cmd_status

        仅 root(0) 可用。目标模块 uid 必须 > 0（不能调自身或其他 uid=0 模块）。
        """
        user_uid = self._get_user_uid(ctx.user_id)
        if user_uid > UID_ROOT:
            await ctx.reply(f"\u274c 仅 root(0) 可使用此命令。你的 UID: {user_uid}")
            return

        args = ctx.args
        if not args:
            loaded = []
            try:
                host = self.services.get("_host")
                for name, mod in host.module_mgr._loaded_modules.items():
                    mod_uid = getattr(mod, 'uid', 9999)
                    if mod_uid > 0:
                        loaded.append(f"  {name} (uid={mod_uid})")
            except Exception:
                pass
            hint = f"\U0001f6e0\ufe0f UID: {user_uid} | .exec <模块.方法> [参数]"
            if loaded:
                hint += "\n可调用模块:\n" + "\n".join(loaded[:15])
            await ctx.reply(hint)
            return

        parts = args[0].split(".", 1)
        if len(parts) != 2:
            await ctx.reply("\u274c 格式: .exec <模块名.方法名> [参数...]")
            return
        mod_name, method_name = parts

        target_mod = None
        try:
            host = self.services.get("_host")
            target_mod = host.module_mgr._loaded_modules.get(mod_name)
        except Exception:
            pass

        if target_mod is None:
            await ctx.reply(f"\u274c 模块 '{mod_name}' 未加载")
            return

        target_uid = getattr(target_mod, 'uid', UID_NOBODY)
        # root 不能通过 .exec 调用其他 root 级模块（包括自身 kernel_auth）
        if target_uid <= UID_ROOT:
            await ctx.reply(f"\u274c 禁止调用 root 级模块 '{mod_name}'")
            return

        method = getattr(target_mod, method_name, None)
        if method is None or not callable(method):
            await ctx.reply(
                f"\u274c '{method_name}' 在 '{mod_name}' 中不存在或不可调用"
            )
            return

        from ...core.context import CommandContext
        sub_ctx = CommandContext(
            user_id=ctx.user_id,
            group_id=ctx.group_id,
            nickname=ctx.nickname,
            message=ctx.message,
            args=args[1:] if len(args) > 1 else [],
            adapter=ctx.adapter,
            message_mgr=ctx._message_mgr,
        )

        try:
            await method(sub_ctx)
        except Exception as e:
            await ctx.reply(f"\u274c {mod_name}.{method_name}: {e}")

    # ── 内部 ──

    def _get_user_uid(self, user_id: int) -> int:
        uid_map = self.config.get("权限管理.UID授权", {})
        if isinstance(uid_map, dict):
            for uid_str, qq_list in uid_map.items():
                try:
                    uid_level = int(uid_str)
                except ValueError:
                    continue
                if isinstance(qq_list, list) and user_id in qq_list:
                    return uid_level
        if user_id in self._get_admin_list():
            return 100
        return UID_NOBODY

    def _set_user_uid(self, user_id: int, new_uid: int):
        uid_map = self.config.get("权限管理.UID授权", {})
        if not isinstance(uid_map, dict):
            uid_map = {}

        for uid_str in list(uid_map.keys()):
            qq_list = uid_map.get(uid_str, [])
            if isinstance(qq_list, list) and user_id in qq_list:
                qq_list.remove(user_id)
                if not qq_list:
                    del uid_map[uid_str]
                else:
                    uid_map[uid_str] = qq_list

        key = str(new_uid)
        if key not in uid_map:
            uid_map[key] = []
        if user_id not in uid_map[key]:
            uid_map[key].append(user_id)

        self.config.set("权限管理.UID授权", uid_map)
        try:
            self.services.get("config").save()
        except Exception:
            pass

    def _get_admin_list(self) -> list:
        try:
            admin_list = self.config.get("游戏管理.管理员QQ", [])
            if not isinstance(admin_list, list):
                admin_list = self.config.get("管理员.管理员QQ", [])
            return [int(q) for q in admin_list if q]
        except (TypeError, ValueError):
            return []

    def _ensure_admin(self, user_id: int) -> None:
        admin_list = self._get_admin_list()
        if user_id in admin_list:
            return
        admin_list.append(user_id)
        self.config.set("管理员.管理员QQ", admin_list)
        try:
            self.services.get("config").save()
        except Exception:
            pass
        _log.info("用户 %d 已加入管理员列表", user_id)

    def _remove_admin(self, user_id: int) -> None:
        admin_list = self._get_admin_list()
        if user_id not in admin_list:
            return
        admin_list.remove(user_id)
        self.config.set("管理员.管理员QQ", admin_list)
        try:
            self.services.get("config").save()
        except Exception:
            pass
        _log.info("用户 %d 已从管理员列表移除", user_id)
