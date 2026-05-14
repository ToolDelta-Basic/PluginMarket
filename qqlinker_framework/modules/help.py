"""帮助命令模块，提供自动生成的命令列表，支持分页浏览与超时自动关闭。"""
import time
import logging
from typing import Dict, List
from ..core.module import Module
from ..core.decorators import command, listen

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)

PAGE_SIZE = 8
SESSION_TIMEOUT = 120


class HelpModule(Module):
    """提供 .help 命令，分页列出所有可用命令及其描述。"""

    name = "help"
    version = (1, 0, 2)
    required_services = ["command", "message", "config"]

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        # 翻页会话：user_id -> {
        #     "lines": list, "current": int,
        #     "total": int, "last_active": float
        # }
        self._sessions: Dict[int, dict] = {}

    async def on_init(self):
        """注册 .help 命令。"""
        self.register_command(
            ".help", self._cmd_help,
            description="显示命令帮助（支持翻页）",
        )

    @command(".help")
    async def _cmd_help(self, ctx):
        """生成帮助页面并发送第一页，若多页则启动翻页会话。"""
        is_admin = self._is_admin(ctx.user_id)
        all_lines = self._build_command_lines(is_admin)
        if not all_lines:
            await ctx.reply("当前没有任何可用命令。")
            return

        total_pages = (len(all_lines) - 1) // PAGE_SIZE + 1
        page_lines = all_lines[:PAGE_SIZE]
        msg = self._format_page(page_lines, 1, total_pages)
        await ctx.reply(msg)

        if total_pages > 1:
            self._sessions[ctx.user_id] = {
                "lines": all_lines,
                "current": 1,
                "total": total_pages,
                "last_active": time.time(),
            }

    @listen("GroupMessageEvent", priority=-20)
    async def _on_group_msg(self, event):
        """检测翻页指令，处理翻页或退出。"""
        user_id = event.user_id
        session = self._sessions.get(user_id)
        if not session:
            return

        if time.time() - session["last_active"] > SESSION_TIMEOUT:
            del self._sessions[user_id]
            await self.message.send_group(
                event.group_id, "帮助会话已超时自动关闭。"
            )
            return

        text = event.message.strip()
        if text not in ("+", "-", "q"):
            return

        event.handled = True
        session["last_active"] = time.time()

        if text == "q":
            del self._sessions[user_id]
            await self.message.send_group(event.group_id, "帮助菜单已关闭。")
            return

        if text == "+":
            new_page = min(session["current"] + 1, session["total"])
        else:
            new_page = max(session["current"] - 1, 1)

        if new_page != session["current"]:
            session["current"] = new_page
            start = (new_page - 1) * PAGE_SIZE
            page_lines = session["lines"][start : start + PAGE_SIZE]
            msg = self._format_page(page_lines, new_page, session["total"])
            await self.message.send_group(event.group_id, msg)

    def _build_command_lines(self, is_admin: bool) -> List[str]:
        """构建当前用户可见的所有命令行。"""
        lines: List[str] = []
        all_commands = self.command.get_group_commands()
        for cmd_info in all_commands:
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
        return lines

    @staticmethod
    def _format_page(
        page_lines: List[str], current: int, total: int
    ) -> str:
        """格式化单页帮助文本。"""
        header = f"📋 可用命令列表 ({current}/{total})"
        body = "\n".join(page_lines) if page_lines else "(空)"
        footer = "输入 + 下一页，- 上一页，q 结束"
        return f"{header}\n{body}\n{footer}"

    def _is_admin(self, user_id: int) -> bool:
        """判断用户是否为管理员。"""
        try:
            admin_list = self.config.get("管理员.管理员QQ", [])
            return user_id in [int(q) for q in admin_list]
        except (TypeError, ValueError):
            return False
