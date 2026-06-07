"""配置修复模块 — 自动检测并修复群子配置的类型错误

═══════════════════════════════════════════════════════════════════════════
 功能
═══════════════════════════════════════════════════════════════════════════
 · 终端启动时，群配置加载过程中类型校验失败 → 自动备份 + fallback
 · 管理员可通过 .修复配置 <群号> 手动修复某群配置
 · .配置状态 查看所有群的子配置状态
 · .配置预览 <群号> <节名> 预览某群某节合并后的配置
 · 备份文件存放至 data/repair_backups/，路径模式下按模块约定

 安全：.修复配置 会校验操作人是否属于目标群
═══════════════════════════════════════════════════════════════════════════
"""
import logging
import os
from datetime import datetime

from ...core.module import Module
from ...core.kernel.decorators import command
from ...core.kernel.audit import audit_log, AuditLevel

_log = logging.getLogger(__name__)


class ConfigRepairModule(Module):
    """配置修复与诊断模块。"""

    name = "config_repair"
    tier = 200  # TIER_SERVICE  # service: 内核服务级
    version = (1, 0, 0)
    dependencies: list[str] = []
    required_services = ["config", "group_config", "message", "command"]

    default_config = {
        "配置修复": {
            "管理员QQ": [],
            "自动修复通知": True,
            "备份保留天数": 30,
        }
    }
    config_scope = {"配置修复": "global"}  # 管理员QQ 只在主配置

    async def on_init(self) -> None:
        """模块就绪。命令通过 @command 装饰器自动注册。"""
        _log.info("[config_repair] 配置修复模块已就绪")

    @command(".修复配置", op_only=True, argument_hint="<群号>", description="修复指定群的子配置（管理员）")
    async def _cmd_repair(self, ctx):
        """手动修复指定群的子配置。

        校验操作人是否属于目标群，防止越权操作。
        """
        args = ctx.args
        if not args:
            await ctx.reply("用法: .修复配置 <群号>\n例: .修复配置 114514")
            return

        try:
            group_id = int(args[0])
        except ValueError:
            await ctx.reply(f"❌ 无效的群号: {args[0]}")
            return

        # 校验操作人是否属于目标群
        if ctx.group_id and ctx.group_id != group_id:
            await ctx.reply(
                f"❌ 操作拒绝：你当前在群 {ctx.group_id}，"
                f"不能修复群 {group_id} 的配置。"
                f"请切换到目标群后操作。"
            )
            _log.warning(
                "[config_repair] 用户 %d 尝试跨群修复配置 "
                "(当前群=%d, 目标群=%d)，已拒绝。",
                ctx.user_id, ctx.group_id, group_id,
            )
            return

        # 审计日志
        audit_log(
            sender=str(ctx.user_id),
            action="config_repair",
            target=f"group_{group_id}",
            detail=f"by_{ctx.nickname}",
            level=AuditLevel.WARNING,
            group_id=group_id,
        )

        try:
            self.group_config.repair_group_config(group_id, backup_first=True)
            await ctx.reply(
                f"✅ 群 {group_id} 配置已修复。\n"
                f"   旧配置已备份至 data/repair_backups/ 目录。\n"
                f"   当前使用主配置默认值。请用 .配置预览 {group_id} <节名> 确认。"
            )
            _log.info("[config_repair] 管理员 %d 修复了群 %d 配置",
                      ctx.user_id, group_id)
        except Exception as e:
            _log.error("[config_repair] 修复群 %d 失败: %s", group_id, e)
            await ctx.reply(f"❌ 修复失败: {e}")

    @command(".配置状态", op_only=True, description="查看所有群子配置状态（管理员）")
    async def _cmd_status(self, ctx):
        """查看所有群子配置的状态。"""
        configs = self.group_config.list_group_configs()
        if not configs:
            await ctx.reply("📋 暂无群子配置。群在首次使用时自动创建。")
            return

        lines = ["📋 群子配置状态:"]
        for entry in configs:
            gid = entry["group_id"]
            has = "✅" if entry["has_config"] else "⚠️"
            size_kb = entry["file_size"] / 1024
            lines.append(f"  {has} 群 {gid} (子配置 {size_kb:.1f}KB)")

        # 显示备份数
        repair_dir = self.group_config.repair_dir
        backup_count = 0
        if os.path.isdir(repair_dir):
            backup_count = len([
                f for f in os.listdir(repair_dir)
                if f.endswith('.json')
            ])
        lines.append(f"\n📦 备份文件: {backup_count} 个")

        if ctx.group_id:
            # 同时显示当前群的配置预览
            cfg = self.group_config.get(ctx.group_id, "配置修复.自动修复通知", True)
            lines.append(f"\n📍 当前群 {ctx.group_id} 自动修复通知: {'开启' if cfg else '关闭'}")

        await ctx.reply("\n".join(lines))

    @command(".配置预览", op_only=True, argument_hint="<群号> <节名>", description="预览某群某节配置（管理员）")
    async def _cmd_preview(self, ctx):
        """预览某群某配置节的值。"""
        args = ctx.args
        if len(args) < 2:
            await ctx.reply(
                "用法: .配置预览 <群号> <节名>\n"
                "例: .配置预览 114514 acg_image\n"
                "     .配置预览 114514 acg_image.冷却秒"
            )
            return

        try:
            group_id = int(args[0])
        except ValueError:
            await ctx.reply(f"❌ 无效的群号: {args[0]}")
            return

        key = args[1]

        try:
            value = self.group_config.get(group_id, key)
            if value is None:
                await ctx.reply(f"❌ 群 {group_id} 中没有配置项: {key}")
                return

            import json
            formatted = json.dumps(value, ensure_ascii=False, indent=2)
            if len(formatted) > 1500:
                formatted = formatted[:1500] + "\n... (截断)"
            await ctx.reply(
                f"📋 群 {group_id} 配置 [{key}]:\n{formatted}"
            )
        except Exception as e:
            await ctx.reply(f"❌ 读取失败: {e}")
