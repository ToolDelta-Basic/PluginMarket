# modules/help.py
"""帮助命令模块，提供自动生成的命令列表。"""
from ..core.module import Module
from ..core.decorators import command

class HelpModule(Module):
    """提供 .help 命令，列出所有可用命令及其描述。"""
    name = "help"
    version = (1, 0, 0)
    required_services = ["command", "message", "config"]

    async def on_init(self):
        """注册 .help 命令。"""
        self.register_command(".help", self._cmd_help, description="显示命令帮助")

    @command(".help")
    async def _cmd_help(self, ctx):
        """生成并回复帮助信息，自动区分管理员/普通用户可见命令。"""
        # 获取当前用户是否为管理员
        is_admin = False
        try:
            is_admin = self.config.get("管理员.管理员QQ", []).count(ctx.user_id) > 0
        except:
            pass

        lines = ["📋 可用命令列表："]
        # 获取所有已注册的命令
        all_commands = self.command.get_group_commands()
        if not all_commands:
            await ctx.reply("当前没有任何可用命令。")
            return

        for cmd_info in all_commands:
            # 跳过管理命令如果用户不是管理员
            if cmd_info.get("op_only", False) and not is_admin:
                continue
            trigger = cmd_info["trigger"]
            desc = cmd_info.get("description", "")
            hint = cmd_info.get("argument_hint", "")
            line = f"• {trigger}"
            if hint:
                line += f" {hint}"
            if desc:
                line += f" —— {desc}"
            if cmd_info.get("op_only"):
                line += " (管理员)"
            lines.append(line)

        if len(lines) == 1:
            lines.append("(空)")

        await ctx.reply("\n".join(lines))