"""游戏管理指令模块：玩家列表、指令执行、脚本串联、白名单校验。

提供命令:
  .在线 — 查看在线玩家列表
  .指令   — 执行单条游戏指令（管理员）
  .执行   — 批量执行多条指令（管理员）

所有指令通过白名单+危险参数过滤实现安全控制。
所有管理员命令执行写入审计日志。
"""
from ...core.module import Module
from ...core.kernel.decorators import command
from ...core.kernel.audit import audit_log, AuditLevel

import logging

_log = logging.getLogger(__name__)

DEFAULT_DANGEROUS_ARGS = (
    "op", "deop", "stop", "restart", "reload",
    "whitelist", "ban", "pardon", "kick", "banlist",
    "save", "save-all", "save-off", "save-on",
    "debug", "seed", "defaultgamemode", "difficulty"
)


class GameAdmin(Module):
    """游戏管理模块：.在线 查看在线玩家，.指令/.执行 执行游戏指令。"""

    name = "game_admin"
    tier = 100  # TIER_DAEMON  # daemon: 系统守护
    version = (1, 0, 0)
    required_services = ["config", "adapter"]

    default_config = {
        "游戏管理": {
            "是否启用": True,
            "允许查看玩家列表": True,
            "管理员QQ": [0],
            "允许执行的命令列表": [
                "list", "say", "tell", "msg", "w", "tellraw",
                "scoreboard", "title", "playsound", "particle",
                "gamemode", "time", "weather", "tp", "kill",
                "give", "clear", "effect", "enchant", "xp",
                "spawnpoint", "setworldspawn", "gamerule",
                "difficulty", "defaultgamemode", "seed"
            ],
            "危险参数": DEFAULT_DANGEROUS_ARGS,
            "允许脚本串联": True,
            "脚本最大指令数": 10
        }
    }

    async def on_init(self):
        """框架已自动注册 default_config 配置节，模块只注册命令。"""

        async def _dbg_stats():
            """调试端点。"""
            return str({
                "online_players": len(self.adapter.get_online_players())
            })

        async def _dbg_config():
            """调试端点。"""
            return str(self._get_cfg())

        try:
            debug = self.services.get("debug")
            await debug.register_module(
                self.name,
                {"stats": _dbg_stats, "config": _dbg_config},
            )
        except KeyError:
            pass

        self.register_command(
            ".在线", self.cmd_list, description="查看在线玩家列表"
        )
        self.register_command(
            ".指令", self.cmd_exec,
            description="执行游戏指令（管理员）",
            op_only=True, argument_hint="<指令>"
        )
        self.register_command(
            ".执行", self.cmd_run,
            description="执行多条游戏指令，用 / 分隔（管理员）",
            op_only=True, argument_hint="<指令1/指令2/...>"
        )

    def _get_cfg(self):
        """获取游戏管理配置节。"""
        return self.config.get("游戏管理", {})

    def _validate_command(self, cmd: str) -> tuple[bool, str]:
        """验证指令是否在允许列表且不含危险参数。

        强制将指令小写化执行（不只是验证），防止大小写绕过。

        Args:
            cmd: 完整的指令字符串。

        Returns:
            (合法标志, 错误信息)
        """
        cfg = self._get_cfg()
        allowed = [
            c.lower() for c in cfg.get("允许执行的命令列表", [])
        ]
        if not allowed:
            return False, "管理员未配置允许执行的命令列表"
        dangerous_args = [
            a.lower() for a in cfg.get("危险参数", DEFAULT_DANGEROUS_ARGS)
        ]
        cmd_clean = cmd.strip().lstrip("/")
        parts_lower = cmd_clean.lower().split()
        if not parts_lower:
            return False, "指令为空"
        root = parts_lower[0]
        if root not in allowed:
            return False, f"禁止执行的命令: {root}"
        for arg in parts_lower[1:]:
            if arg in dangerous_args:
                return False, f"参数包含敏感项: {arg}"
        # 返回小写化版本
        return True, cmd_clean.lower()

    @command(".在线")
    async def cmd_list(self, ctx):
        """查看在线玩家列表。"""
        if not self._get_cfg().get("允许查看玩家列表", True):
            await ctx.reply("此功能已禁用")
            return
        players = self.adapter.get_online_players()
        if not players:
            await ctx.reply("当前无人在线")
        else:
            msg = f"在线玩家 ({len(players)}人)：" + "、".join(players)
            await ctx.reply(msg)

    @command(".指令", op_only=True)
    async def cmd_exec(self, ctx):
        """执行单条游戏指令（管理员）。"""
        if not ctx.args:
            await ctx.reply("用法：.指令 <指令>")
            return
        cmd = " ".join(ctx.args)
        valid, sanitized = self._validate_command(cmd)
        if not valid:
            await ctx.reply(f"❌ {sanitized}")
            return

        # 审计日志
        audit_log(
            sender=str(ctx.user_id),
            action="game_command",
            target=sanitized[:200],
            detail=f"by_{ctx.nickname}_in_group_{ctx.group_id}",
            level=AuditLevel.INFO,
            group_id=ctx.group_id,
        )

        try:
            self.adapter.send_game_command(sanitized)
            await ctx.reply(f"✅ 已执行: /{sanitized}")
        except Exception as e:
            await ctx.reply(f"❌ 执行失败: {str(e)}")

    @command(".执行", op_only=True)
    async def cmd_run(self, ctx):
        """执行多条游戏指令（用 / 分隔）。"""
        cfg = self._get_cfg()
        if not cfg.get("允许脚本串联", True):
            await ctx.reply("脚本功能已禁用")
            return
        if not ctx.args:
            await ctx.reply("用法：.执行 <指令1/指令2/...>")
            return
        raw = " ".join(ctx.args)
        commands = [c.strip() for c in raw.split("/") if c.strip()]
        max_cmds = cfg.get("脚本最大指令数", 10)
        if len(commands) > max_cmds:
            await ctx.reply(
                f"脚本包含 {len(commands)} 条指令，超过上限 {max_cmds}"
            )
            return
        results = []
        for cmd in commands:
            valid, sanitized = self._validate_command(cmd)
            if valid:
                try:
                    self.adapter.send_game_command(sanitized)
                    results.append(f"✅ /{sanitized}")
                except Exception as e:
                    results.append(f"❌ /{sanitized} (异常: {str(e)})")
            else:
                results.append(f"❌ /{cmd} ({sanitized})")

        # 审计日志（批量）
        audit_log(
            sender=str(ctx.user_id),
            action="game_script",
            target=f"{len(commands)} commands",
            detail=f"by_{ctx.nickname}_results={len([r for r in results if r.startswith('✅')])}",
            level=AuditLevel.INFO,
            group_id=ctx.group_id,
        )

        await ctx.reply("脚本执行结果：\n" + "\n".join(results))
