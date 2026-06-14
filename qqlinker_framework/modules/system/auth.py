"""身份认证模块 — .uid 查看等级、.sudo 提权申请、.approve 批准。

sudo/approve 提供用户→管理员的提权通道。root 和 daemon 的授权由内核模块 kernel_auth 处理。
"""
import logging
import time
from ...core.module import Module
from ...core.kernel.decorators import command
from ...core.kernel.services import uid_label, TIER_KERNEL, UID_NOBODY
from ...core.kernel.audit import audit_log, AuditLevel

_log = logging.getLogger(__name__)

# .sudo 冷却时间（秒）
_SUDO_COOLDOWN = 30


def _normalize_qq_list(qq_list: list) -> list:
    """将 QQ 号列表统一转为 int，剔除无效值（兼容 OneBot 协议 string 和 int）。"""
    result = []
    for q in qq_list:
        if not q:
            continue
        try:
            result.append(int(q))
        except (TypeError, ValueError):
            continue
    return result


def persist_user_uid(config, services, user_id: int, new_uid: int):
    """持久化用户的 UID 等级到 config.json（模块级共享函数）。

    供 auth.AuthModule 和 kernel_auth.KernelAuthModule 共用，
    避免两处重复实现导致修复不同步。
    """
    uid_map = config.get("权限管理.UID授权", {})
    if not isinstance(uid_map, dict):
        uid_map = {}

    uid_int = int(user_id) if not isinstance(user_id, int) else user_id
    for uid_str in list(uid_map.keys()):
        qq_list = uid_map.get(uid_str, [])
        if isinstance(qq_list, list) and uid_int in _normalize_qq_list(qq_list):
            qq_list_normalized = _normalize_qq_list(qq_list)
            qq_list_normalized.remove(uid_int)
            if not qq_list_normalized:
                del uid_map[uid_str]
            else:
                uid_map[uid_str] = qq_list_normalized

    key = str(new_uid)
    if key not in uid_map:
        uid_map[key] = []
    if uid_int not in _normalize_qq_list(uid_map[key]):
        uid_map[key].append(uid_int)

    config.set("权限管理.UID授权", uid_map)
    try:
        services.get("config").save()
    except Exception:
        pass


class AuthModule(Module):
    """认证模块。"""
    background = True
    """UID 身份认证与提权申请模块。"""

    name = "auth"
    mid = 100  # TIER_DAEMON  # daemon: 系统守护（身份管理）
    tier = 100  # deprecated, use mid
    version = (1, 2, 0)
    required_services = ["config", "message"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._sudo_cooldowns: dict[int, float] = {}

    async def on_init(self):
        """初始化：注册命令（装饰器自动扫描）。"""

    # ── 命令 ──

    @command(".uid", description="查看你的 UID 接口等级")
    async def cmd_uid(self, ctx):
        """返回当前用户的 UID 等级。"""
        user_uid = self._get_user_uid(ctx.user_id)
        label = uid_label(user_uid)
        tier_names = {
            0: "root (全部接口可用)",
            100: "daemon (系统守护)",
            1000: "service (服务引擎)",
            2000: "app (业务模块)",
            400:  "nobody (三方模块)",
        }
        tier = 0
        for t in sorted(tier_names.keys(), reverse=True):
            if user_uid >= t:
                tier = t
                break
        desc = tier_names.get(tier, "用户")
        await ctx.reply(f"\U0001faaa 你的 UID: {user_uid} ({label}) \u2014 {desc}")

    @command(".sudo", description="申请提权到 daemon（需管理员批准）",
             argument_hint="<原因>")
    async def cmd_sudo(self, ctx):
        """用户申请提权到 daemon 级别，通知管理员。

        包含 30 秒冷却速率限制，防止滥用。
        """
        if self._get_user_uid(ctx.user_id) <= 100:
            await ctx.reply("你已拥有 daemon 或更高级别权限，无需提权。")
            return

        # 冷却检查
        now = time.time()
        last_sudo = self._sudo_cooldowns.get(ctx.user_id, 0.0)
        if now - last_sudo < _SUDO_COOLDOWN:
            remain = int(_SUDO_COOLDOWN - (now - last_sudo))
            await ctx.reply(
                f"\u23f3 请等待 {remain} 秒后再申请提权。"
                f"(冷却 {_SUDO_COOLDOWN} 秒)"
            )
            return
        self._sudo_cooldowns[ctx.user_id] = now

        reason = " ".join(ctx.args) if ctx.args else "未说明原因"
        pending = self.config.get("权限管理.提权待审", {})
        if not isinstance(pending, dict):
            pending = {}
        pending[str(ctx.user_id)] = {
            "qq": ctx.user_id, "nickname": ctx.nickname,
            "reason": reason, "time": int(time.time()),
        }
        self.config.set("权限管理.提权待审", pending)
        try:
            self.services.get("config").save()
        except Exception:
            pass

        # 审计日志
        audit_log(
            sender=str(ctx.user_id),
            action="sudo_request",
            target="daemon",
            detail=f"reason={reason[:200]}",
            group_id=ctx.group_id,
        )

        await ctx.reply("\u23f3 提权申请已提交，等待管理员批准。\n管理员可使用 .approve <QQ号> 批准。")
        for admin_qq in self._get_admin_list()[:3]:
            try:
                await self.message.send_private(
                    admin_qq,
                    f"\U0001f514 提权请求\n用户: {ctx.nickname}({ctx.user_id})\n"
                    f"原因: {reason}\n批准: .approve {ctx.user_id}"
                )
            except Exception:
                pass

    @command(".approve", description="批准提权申请（管理员）", op_only=True,
             argument_hint="<QQ号> [--confirm]", min_uid=100)
    async def cmd_approve(self, ctx):
        """管理员批准 .sudo 提权请求，将用户提升到 daemon(100)。

        需要追加 --confirm 进行二次确认。
        """
        if len(ctx.args) < 1:
            await ctx.reply("用法: .approve <QQ号> --confirm")
            return
        try:
            target_qq = int(ctx.args[0])
        except ValueError:
            await ctx.reply("\u274c QQ号格式错误")
            return

        # 二次确认
        if len(ctx.args) < 2 or ctx.args[1] != "--confirm":
            await ctx.reply(
                f"\u26a0\ufe0f 即将批准用户 {target_qq} 提权为 daemon (uid=100)。\n"
                f"请追加 --confirm 确认操作。"
            )
            return

        pending = self.config.get("权限管理.提权待审", {})
        if not isinstance(pending, dict):
            pending = {}
        key = str(target_qq)
        if key not in pending:
            await ctx.reply(f"\u274c 用户 {target_qq} 没有待审的提权申请")
            return

        self._set_user_uid(target_qq, 100)
        self._ensure_admin(target_qq)
        del pending[key]
        self.config.set("权限管理.提权待审", pending)
        try:
            self.services.get("config").save()
        except Exception:
            pass

        # 审计日志
        audit_log(
            sender=str(ctx.user_id),
            action="approve_sudo",
            target=str(target_qq),
            detail=f"approved_by_{ctx.user_id}_to_daemon",
            level=AuditLevel.WARNING,
            group_id=ctx.group_id,
        )

        await ctx.reply(f"\u2705 已批准用户 {target_qq} 提权为 daemon (uid=100) 并加入管理员列表")
        try:
            await self.message.send_private(target_qq,
                "\u2705 你的提权申请已被管理员批准！你现在拥有 daemon 级别权限。")
        except Exception:
            pass

    @command(".revoke", description="降级用户权限（管理员）", op_only=True,
             argument_hint="<QQ号> [--confirm]", min_uid=100)
    async def cmd_revoke(self, ctx):
        """管理员降级用户权限。将指定用户降回 nobody(400)。

        需要追加 --confirm 进行二次确认。
        """
        if len(ctx.args) < 1:
            await ctx.reply("用法: .revoke <QQ号> --confirm")
            return
        try:
            target_qq = int(ctx.args[0])
        except ValueError:
            await ctx.reply("\u274c QQ号格式错误")
            return

        current_uid = self._get_user_uid(target_qq)
        if current_uid <= TIER_KERNEL:
            await ctx.reply("\u274c 无法降级 root 用户")
            return
        if current_uid >= UID_NOBODY:
            await ctx.reply(f"用户 {target_qq} 已经是普通用户")
            return

        # 二次确认
        if len(ctx.args) < 2 or ctx.args[1] != "--confirm":
            await ctx.reply(
                f"\u26a0\ufe0f 即将将用户 {target_qq} "
                f"(当前 {uid_label(current_uid)}) 降级为 nobody。\n"
                f"请追加 --confirm 确认操作。"
            )
            return

        self._set_user_uid(target_qq, UID_NOBODY)
        self._remove_admin(target_qq)

        # 审计日志
        audit_log(
            sender=str(ctx.user_id),
            action="revoke",
            target=str(target_qq),
            detail=f"from_{current_uid}_to_nobody",
            level=AuditLevel.WARNING,
            group_id=ctx.group_id,
        )

        await ctx.reply(f"\u2705 已降级用户 {target_qq} 为普通用户 (nobody)")

    # ── 内部（与 kernel_auth 共享逻辑，两者独立实现以保证 uid=100 不依赖 uid=0）──

    def _get_user_uid(self, user_id: int) -> int:
        """获取用户的 UID 等级。

        逻辑与 host._lookup_uid() 一致（权威实现）:
          1. 查 权限管理.UID授权 表
          2. 查 管理员.管理员QQ 列表 → uid=100
          4. 否则 nobody (400)
        """
        uid_int = int(user_id) if not isinstance(user_id, int) else user_id
        uid_map = self.config.get("权限管理.UID授权", {})
        if isinstance(uid_map, dict):
            for uid_str, qq_list in uid_map.items():
                try:
                    uid_level = int(uid_str)
                except ValueError:
                    continue
                if isinstance(qq_list, list) and uid_int in _normalize_qq_list(qq_list):
                    return uid_level
        admin_list = self.config.get("管理员.管理员QQ", [])
        if isinstance(admin_list, list):
            try:
                if uid_int in [int(q) for q in admin_list if q]:
                    return 100
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

    def _is_admin(self, user_id: int) -> bool:
        """判断用户是否具有管理员权限。"""
        if user_id in self._get_admin_list():
            return True
        return self._get_user_uid(user_id) <= 100

    def _ensure_admin(self, user_id: int) -> None:
        """确保用户在管理员列表中。"""
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
        """从管理员列表移除用户。"""
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
