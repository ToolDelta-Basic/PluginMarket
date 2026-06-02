"""身份认证模块 — .uid 查看等级、.sudo 提权申请、.approve 批准。

sudo/approve 提供用户→管理员的提权通道。root 和 daemon 的授权由内核模块 kernel_auth 处理。
"""
import logging
import time
from ...core.module import Module
from ...core.decorators import command
from ...core.services import uid_label, UID_ROOT, UID_NOBODY

_log = logging.getLogger(__name__)


class AuthModule(Module):
    """UID 身份认证与提权申请模块。"""

    name = "auth"
    uid = 100  # daemon: 系统守护（身份管理）
    version = (1, 2, 0)
    required_services = ["config", "message"]

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
            3000: "nobody (三方模块)",
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
        """用户申请提权到 daemon 级别，通知管理员。"""
        if self._get_user_uid(ctx.user_id) <= 100:
            await ctx.reply("你已拥有 daemon 或更高级别权限，无需提权。")
            return
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
             argument_hint="<QQ号>", min_uid=100)
    async def cmd_approve(self, ctx):
        """管理员批准 .sudo 提权请求，将用户提升到 daemon(100)。"""
        if len(ctx.args) < 1:
            await ctx.reply("用法: .approve <QQ号>")
            return
        try:
            target_qq = int(ctx.args[0])
        except ValueError:
            await ctx.reply("\u274c QQ号格式错误")
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
        await ctx.reply(f"\u2705 已批准用户 {target_qq} 提权为 daemon (uid=100) 并加入管理员列表")
        try:
            await self.message.send_private(target_qq,
                "\u2705 你的提权申请已被管理员批准！你现在拥有 daemon 级别权限。")
        except Exception:
            pass

    # ── 内部（与 kernel_auth 共享逻辑，两者独立实现以保证 uid=100 不依赖 uid=0）──

    def _get_user_uid(self, user_id: int) -> int:
        """获取用户的 UID 等级。先查授权表再查管理员列表。"""
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
        """设置用户的 UID 等级（持久化到 config.json）。"""
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
        """获取管理员 QQ 列表。"""
        try:
            admin_list = self.config.get("游戏管理.管理员QQ", [])
            if not isinstance(admin_list, list):
                admin_list = self.config.get("管理员.管理员QQ", [])
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
