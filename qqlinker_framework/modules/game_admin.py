# modules/game_admin.py
from ..core.module import Module
from ..core.decorators import command

DEFAULT_DANGEROUS_ARGS = [
    "op", "deop", "stop", "restart", "reload",
    "whitelist", "ban", "pardon", "kick", "banlist",
    "save", "save-all", "save-off", "save-on",
    "debug", "seed", "defaultgamemode", "difficulty"
]

class GameAdmin(Module):
    name = "game_admin"
    version = (1, 0, 0)
    required_services = ["config", "adapter"]

    async def on_init(self):
        self.config.register_section("游戏管理", {
            "是否启用": True,
            "允许查看玩家列表": True,
            "管理员QQ": [0],
            "允许执行的命令列表": [
                "list", "say", "tell", "msg", "w", "tellraw", "scoreboard",
                "title", "playsound", "particle", "gamemode", "time", "weather",
                "tp", "kill", "give", "clear", "effect", "enchant", "xp",
                "spawnpoint", "setworldspawn", "gamerule", "difficulty",
                "defaultgamemode", "seed"
            ],
            "危险参数": DEFAULT_DANGEROUS_ARGS,
            "允许脚本串联": True,
            "脚本最大指令数": 10
        })
        self.register_command(".list", self.cmd_list, description="查看在线玩家列表")
        self.register_command(".cmd", self.cmd_exec, description="执行游戏指令（管理员）", op_only=True,
                              argument_hint="<指令>")
        self.register_command(".run", self.cmd_run, description="执行多条游戏指令，用 ;; 分隔", op_only=True,
                              argument_hint="<指令1;; 指令2;; ...>")

    def _get_cfg(self):
        return self.config.get("游戏管理", {})

    def _validate_command(self, cmd: str) -> tuple[bool, str]:
        cfg = self._get_cfg()
        allowed = [c.lower() for c in cfg.get("允许执行的命令列表", [])]
        dangerous_args = [a.lower() for a in cfg.get("危险参数", DEFAULT_DANGEROUS_ARGS)]
        # 规范化：去除前导斜杠，合并多余空格，全部小写
        cmd_clean = cmd.strip().lstrip("/").lower()
        parts = cmd_clean.split()
        if not parts:
            return False, "指令为空"
        root = parts[0]
        if root not in allowed:
            return False, f"禁止执行的命令: {root}"
        for arg in parts[1:]:
            if arg in dangerous_args:
                return False, f"参数包含敏感项: {arg}"
        return True, ""

    @command(".list")
    async def cmd_list(self, ctx):
        if not self._get_cfg().get("允许查看玩家列表", True):
            await ctx.reply("此功能已禁用")
            return
        players = self.adapter.get_online_players()
        if not players:
            await ctx.reply("当前无人在线")
        else:
            msg = f"在线玩家 ({len(players)}人)：" + "、".join(players)
            await ctx.reply(msg)

    @command(".cmd", op_only=True)
    async def cmd_exec(self, ctx):
        if not ctx.args:
            await ctx.reply("用法：.cmd <指令>")
            return
        cmd = " ".join(ctx.args)
        valid, err = self._validate_command(cmd)
        if not valid:
            await ctx.reply(f"❌ {err}")
            return
        self.adapter.send_game_command(cmd)
        await ctx.reply(f"已执行: /{cmd}")

    @command(".run", op_only=True)
    async def cmd_run(self, ctx):
        cfg = self._get_cfg()
        if not cfg.get("允许脚本串联", True):
            await ctx.reply("脚本功能已禁用")
            return
        if not ctx.args:
            await ctx.reply("用法：.run <指令1;; 指令2;; ...>")
            return
        raw = " ".join(ctx.args)
        commands = [c.strip() for c in raw.split(";;") if c.strip()]
        max_cmds = cfg.get("脚本最大指令数", 10)
        if len(commands) > max_cmds:
            await ctx.reply(f"脚本包含 {len(commands)} 条指令，超过上限 {max_cmds}")
            return
        results = []
        for cmd in commands:
            valid, err = self._validate_command(cmd)
            if valid:
                self.adapter.send_game_command(cmd)
                results.append(f"✅ /{cmd}")
            else:
                results.append(f"❌ {cmd} ({err})")
        await ctx.reply("脚本执行结果：\n" + "\n".join(results))