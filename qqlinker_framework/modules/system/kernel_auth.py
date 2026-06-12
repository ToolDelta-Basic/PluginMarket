"""内核授权模块 — .grant 授权 UID、.exec 调用模块方法（root 独占）。

uid=0 (root) — 只能由框架内核加载，不通过模块市场分发。

安全约束:
  - .grant 不允许授予 uid=0（root 只能在配置文件/启动参数中设置）
  - .exec 只能调用标记了 @exec_exposed 的方法
  - 所有 .exec 调用写入审计日志文件
"""
import hashlib
import json
import logging
import time
from ...core.module import Module
from ...core.kernel.decorators import command
from ...core.kernel.services import uid_label, TIER_KERNEL, TIER_DAEMON, TIER_SERVICE, UID_NOBODY
from ...core.kernel.audit import audit_log, audit_log_exec, AuditLevel
from .auth import persist_user_uid

_log = logging.getLogger(__name__)


# ── @exec_exposed 装饰器 ───────────────────────────────────

def exec_exposed(func):
    """标记方法可通过 .exec 命令调用。

    只有标记了此装饰器的方法才能被 root 通过 .exec 调用。
    这是瑞士奶酪模型的额外一层：即使 .exec 命令被滥用，
    攻击面也被限制在明确标记为安全的公开方法上。

    用法:
        @exec_exposed
        async def cmd_status(self, ctx):
            ...
    """
    func._exec_exposed = True
    return func


def is_exec_exposed(method) -> bool:
    """检查方法是否标记了 @exec_exposed。"""
    return getattr(method, '_exec_exposed', False)


class KernelAuthModule(Module):
    background = True
    """内核级授权模块。uid=0，仅 root 用户可触发。"""

    name = "kernel_auth"
    tier = 0  # TIER_KERNEL  # root: 框架内核
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
              .grant 12345 100    (授予守护级)

        禁止: .grant <任何人> 0    (root 只能在配置文件设置)
        """
        caller_uid = self._get_user_uid(ctx.user_id)
        if caller_uid > TIER_KERNEL:
            await ctx.reply(f"\u274c 仅 root(0) 可使用此命令。你的 UID: {caller_uid}")
            return

        if len(ctx.args) < 1:
            await ctx.reply("用法: .grant <QQ号> [uid等级]\n"
                            "等级: 0=root, 100=daemon, 200=service, 300=app(默认), 400=nobody")
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
                            f"有效范围: 100=守护, 1000=系统, 2000=用户")
            return

        # ★ 硬限制: 禁止通过 .grant 授予 uid=0
        if new_uid <= TIER_KERNEL:
            audit_log(
                sender=str(ctx.user_id),
                action="grant_root_attempt",
                target=str(target_qq),
                detail=f"grant_attempt_from_{ctx.user_id}_to_{target_qq}_uid=0",
                level=AuditLevel.CRITICAL,
                group_id=ctx.group_id,
            )
            _log.critical(
                "⛔ 严重安全事件: 用户 %d 尝试通过 .grant 授予 %d uid=0！"
                "该操作已被硬编码阻止。root 只能在配置文件/启动参数中设置。",
                ctx.user_id, target_qq,
            )
            await ctx.reply(
                "\u274c 禁止通过 .grant 授予 uid=0 (root)。"
                "root 只能在配置文件中设置。"
            )
            return

        # 二次确认机制
        confirm_arg = ctx.args[-1] if len(ctx.args) >= 3 else ""
        if confirm_arg != "--confirm":
            await ctx.reply(
                f"\u26a0\ufe0f 即将将用户 {target_qq} 授权为 UID {new_uid} "
                f"({uid_label(new_uid)})。\n"
                f"请追加 --confirm 确认操作。"
            )
            return

        self._set_user_uid(target_qq, new_uid)
        label = uid_label(new_uid)

        # 审计日志
        audit_log(
            sender=str(ctx.user_id),
            action="grant",
            target=str(target_qq),
            detail=f"new_uid={new_uid} label={label}",
            level=AuditLevel.WARNING,
            group_id=ctx.group_id,
        )

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
        """root 直接调用已加载模块的方法。

        用法: .exec <模块名.方法名> [参数...]
        例如: .exec auth.cmd_uid
              .exec config_repair.cmd_status

        仅 root(0) 可用。目标方法必须标记 @exec_exposed 装饰器。
        root 的调用权限不被被调用方法阻止。
        """
        user_uid = self._get_user_uid(ctx.user_id)
        if user_uid > TIER_KERNEL:
            await ctx.reply(f"\u274c 仅 root(0) 可使用此命令。你的 UID: {user_uid}")
            return

        args = ctx.args
        if not args:
            loaded = []
            try:
                host = self.services.get("_host")
                for name, mod in host.module_mgr._loaded_modules.items():
                    mod_uid = getattr(mod, 'uid', 400)
                    if mod_uid > 0:
                        # 只列出有 exec_exposed 方法的模块
                        exposed = [
                            m for m in dir(mod)
                            if is_exec_exposed(getattr(mod, m, None))
                        ]
                        if exposed:
                            loaded.append(
                                f"  {name} (uid={mod_uid}) "
                                f"[{', '.join(exposed[:3])}]"
                            )
            except Exception:
                pass
            hint = f"\U0001f6e0\ufe0f UID: {user_uid} | .exec <模块.方法> [参数]"
            if loaded:
                hint += "\n可调用模块 (标记 @exec_exposed 的方法):\n" + "\n".join(loaded[:15])
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
        if target_uid <= TIER_KERNEL:
            await ctx.reply(f"\u274c 禁止调用 root 级模块 '{mod_name}'")
            return

        method = getattr(target_mod, method_name, None)
        if method is None or not callable(method):
            await ctx.reply(
                f"\u274c '{method_name}' 在 '{mod_name}' 中不存在或不可调用"
            )
            return

        # ★ @exec_exposed 白名单检查
        if not is_exec_exposed(method):
            audit_log(
                sender=str(ctx.user_id),
                action="exec_blocked_not_exposed",
                target=f"{mod_name}.{method_name}",
                detail="方法未标记 @exec_exposed",
                level=AuditLevel.WARNING,
                group_id=ctx.group_id,
            )
            await ctx.reply(
                f"\u274c '{mod_name}.{method_name}' 未标记 @exec_exposed，"
                f"不可通过 .exec 调用。"
            )
            return

        # 审计日志：记录 .exec 调用（合并为一条）
        exec_args = args[1:] if len(args) > 1 else []
        audit_log_exec(
            caller_uid=ctx.user_id,
            module_name=mod_name,
            method_name=method_name,
            args=exec_args,
        )

        from ...core.kernel.context import CommandContext
        sub_ctx = CommandContext(
            user_id=ctx.user_id,
            group_id=ctx.group_id,
            nickname=ctx.nickname,
            message=ctx.message,
            args=exec_args,
            adapter=ctx.adapter,
            message_mgr=ctx._message_mgr,
        )

        try:
            await method(sub_ctx)
        except Exception as e:
            await ctx.reply(f"\u274c {mod_name}.{method_name}: {e}")

    # ── 内部 ──

    def _get_user_uid(self, user_id: int) -> int:
        """获取用户的 UID 等级。

        逻辑与 host._lookup_uid() 一致（权威实现）:
          1. 查 权限管理.UID授权 表
          2. 查 管理员.管理员QQ 列表 → uid=100
          4. 否则 nobody (400)
        """
        uid_map = self.config.get("权限管理.UID授权", {})
        if isinstance(uid_map, dict):
            for uid_str, qq_list in uid_map.items():
                try:
                    uid_level = int(uid_str)
                except ValueError:
                    continue
                if isinstance(qq_list, list) and user_id in qq_list:
                    return uid_level
        admin_list = self.config.get("管理员.管理员QQ", [])
        if isinstance(admin_list, list):
            try:
                if user_id in [int(q) for q in admin_list if q]:
                    return 100
            except (TypeError, ValueError):
                pass
            except (TypeError, ValueError):
                pass
        return UID_NOBODY

    def _set_user_uid(self, user_id: int, new_uid: int):
        """设置用户的 UID 等级（持久化到 config.json）。"""
        persist_user_uid(self.config, self.services, user_id, new_uid)

    def _get_admin_list(self) -> list:
        """获取管理员 QQ 列表。

        若为空或非 list 类型，回退到 管理员.管理员QQ。
        """
        try:
            admin_list = self.config.get("管理员.管理员QQ", [])
            if not isinstance(admin_list, list):
                return []
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
