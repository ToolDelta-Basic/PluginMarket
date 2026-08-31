"""双层帮助服务 — v2.2 HelpService + HelpModule。

提供：
  .帮助              → 按模块分组的命令列表
  .帮助 <命令>       → 命令详细信息
  .帮助 <命令> --root→ 命令详细信息 + 归属/层级
  .帮助 规则         → 规则引擎 DSL 完整参考
"""

import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

from ...core.module import Module
from ...core.kernel.decorators import command, listen
from ...core.kernel.events import GroupMessageEvent

_log = logging.getLogger(__name__)

_CQ_RE = re.compile(r'\[CQ:[^\]]+\]')

PAGE_SIZE = 8
SESSION_TIMEOUT = 120
CLEANUP_INTERVAL = 60


class HelpService:
    """双层帮助服务核心逻辑。

    模块通过 register_help() 注册命令详细帮助，
    帮助指令通过 format_list() / format_detail() / format_rule_help() 格式化输出。

    约定：command_manager 参数为 CommandManager 实例（提供 get_group_commands）。
    """

    def __init__(self, command_manager=None):
        self._command_mgr = command_manager
        # 已注册的帮助详情: cmd_trigger → detail
        self._help_details: Dict[str, dict] = {}
        # 模块名 → 子命令帮助列表（用于自动发现）
        self._module_helps: Dict[str, List[Tuple[str, dict]]] = {}

    def set_command_manager(self, command_manager):
        """设置命令管理器引用（延迟注入）。"""
        self._command_mgr = command_manager

    def register_help(self, cmd_trigger: str, detail: dict) -> None:
        """注册命令详细帮助。

        Args:
            cmd_trigger: 命令触发词（如 ".规则"）。
            detail: 帮助详情字典，可包含:
                - description: 简短描述
                - usage: 用法格式
                - examples: 示例列表
                - sub_commands: 子命令列表 [(触发词, 描述), ...]
                - aliases: 别名列表
                - module: 归属模块名
                - see_also: 相关命令列表
                - registered_at: 字符串表示注册时间
                - min_uid: 最低权限层级名
        """
        self._help_details[cmd_trigger] = detail

    def format_list(self, caller_uid: int = 400, is_admin: bool = False) -> str:
        """生成 .帮助 的按模块分组的命令列表。

        Args:
            caller_uid: 调用者 UID（用于过滤不可用命令）。
            is_admin: 是否管理员。

        Returns:
            格式化的帮助列表字符串。
        """
        if not self._command_mgr:
            return "命令系统未就绪。"

        all_commands = self._command_mgr.get_group_commands()

        # 过滤：隐藏的、超出权限的
        visible = []
        for cmd in all_commands:
            if cmd.get("hidden", False):
                continue
            if cmd.get("op_only", False) and not is_admin:
                continue
            min_uid = cmd.get("min_uid", 400)
            if min_uid > 0 and caller_uid > 0 and caller_uid > min_uid:
                continue
            visible.append(cmd)

        if not visible:
            return "当前没有任何可用命令。"

        # 按模块分组
        groups: Dict[str, List[dict]] = {}
        for cmd in visible:
            module = cmd.get("plugin", "未分类")
            if module == "core":
                module = "系统"
            groups.setdefault(module, []).append(cmd)

        # 模块排序
        module_order = ["系统", "rule_engine", "game_admin", "orion_bridge",
                        "ai_core", "未分类"]

        lines: List[str] = []
        for mod_name in module_order:
            if mod_name in groups:
                cmds = groups.pop(mod_name)
                lines.append(f"\n【{mod_name}】")
                for cmd_info in sorted(cmds, key=lambda c: c.get("trigger", "")):
                    trigger = cmd_info.get("trigger", "?")
                    desc = cmd_info.get("description", "")
                    hint = cmd_info.get("argument_hint", "")
                    line = f"  {trigger}"
                    if hint:
                        line += f" {hint}"
                    if desc:
                        line += f" — {desc}"
                    if cmd_info.get("op_only"):
                        line += " (管理)"
                    lines.append(line)

        # 剩余模块
        for mod_name in sorted(groups.keys()):
            cmds = groups[mod_name]
            lines.append(f"\n【{mod_name}】")
            for cmd_info in sorted(cmds, key=lambda c: c.get("trigger", "")):
                trigger = cmd_info.get("trigger", "?")
                desc = cmd_info.get("description", "")
                hint = cmd_info.get("argument_hint", "")
                line = f"  {trigger}"
                if hint:
                    line += f" {hint}"
                if desc:
                    line += f" — {desc}"
                if cmd_info.get("op_only"):
                    line += " (管理)"
                lines.append(line)

        return "".join(lines)

    def format_detail(self, trigger: str, show_root: bool = False) -> str:
        """生成 .帮助 <命令> 的详细信息。

        Args:
            trigger: 命令触发词。
            show_root: 是否显示归属模块/注册时间/权限层级。

        Returns:
            详细的帮助文本。
        """
        # 先查已注册的帮助
        detail = self._help_details.get(trigger)
        if not detail and self._command_mgr:
            # 从 CommandManager 构建基本信息
            cmd_info = self._command_mgr.find_command(trigger)
            if cmd_info:
                detail = {
                    "description": cmd_info.get("description", ""),
                    "usage": trigger + (f" {cmd_info.get('argument_hint', '')}"
                                       if cmd_info.get("argument_hint") else ""),
                }

        if not detail:
            return f"未找到命令 '{trigger}' 的帮助信息。"

        lines = [f"📋 {trigger}"]

        # 描述
        if detail.get("description"):
            lines.append(f"\n  {detail['description']}")

        # 别名
        aliases = detail.get("aliases", [])
        if aliases:
            lines.append(f"\n  别名: {', '.join(aliases)}")

        # 用法
        usage = detail.get("usage", "")
        if usage:
            lines.append(f"\n  用法: {usage}")

        # 示例
        examples = detail.get("examples", [])
        if examples:
            lines.append("\n  示例:")
            for ex in examples:
                lines.append(f"    → {ex}")

        # 子命令
        sub_cmds = detail.get("sub_commands", [])
        if sub_cmds:
            lines.append("\n  子命令:")
            for sub_name, sub_desc in sub_cmds:
                lines.append(f"    · {sub_name} — {sub_desc}")

        # 相关命令
        see_also = detail.get("see_also", [])
        if see_also:
            lines.append(f"\n  参见: {', '.join(see_also)}")

        # root 模式额外信息
        if show_root:
            module = detail.get("module", "未知")
            lines.append(f"\n  ── 元数据 ──")
            lines.append(f"  归属模块: {module}")
            if detail.get("registered_at"):
                lines.append(f"  注册时间: {detail['registered_at']}")
            if detail.get("min_uid"):
                lines.append(f"  权限层级: {detail['min_uid']}")

        return "\n".join(lines)

    def format_rule_help(self) -> str:
        """生成 .帮助 规则 的 DSL 完整参考。

        优先使用 rule_engine 注册的帮助，否则返回内置版本。
        """
        detail = self._help_details.get(".规则")
        if detail and detail.get("usage", "").startswith("详细参考见"):
            # 规则引擎已注册，使用其 help 方法
            return (
                "📐 规则引擎 DSL 完整参考 (v1.7)\n"
                "\n"
                "━━━ 动作类型 ━━━\n"
                "支持在动作链中使用字符串或 JSON 对象：\n"
                "  纯文本          → 直接发送到群\n"
                "  .命令 参数      → 路由到对应命令\n"
                "  .输出 文本      → 直接发送（不走命令路由）\n"
                '  {"发送群消息": "..."}   → 发送群消息\n'
                '  {"发送私聊": "..."}     → 发送私聊消息\n'
                '  {"触发命令": ".cmd"}   → 触发指定命令\n'
                "\n"
                "━━━ 变量系统 ━━━\n"
                '  {"设变量": "count", "命令": ".在线人数"}\n'
                "      → 执行命令并将返回文本存入变量\n"
                '  {"设变量": "num", "命令": ".count", "转为": "数字"}\n'
                "      → 转换为数字（int）存入\n"
                '  {"设变量": "items", "命令": ".list", "转为": "列表", "分隔符": ","}\n'
                "      → 按分隔符拆分为列表\n"
                '  {"设变量": "flag", "命令": ".status", "转为": "布尔"}\n'
                "      → 转为布尔（true/是/1 → True）\n"
                '  {"设变量": "field", "命令": ".status", "取字段": "online"}\n'
                "      → 从 JSON 返回中提取字段\n"
                "\n"
                "  支持的类型转换: 数字 / 列表 / 布尔\n"
                "\n"
                "━━━ 条件动作（如果/否则）━━━\n"
                '  {"如果": {"变量": "count", ">": 3},\n'
                '   "则": [...],\n'
                '   "否则": [...]}\n'
                "\n  支持的运算符: > < >= <= == != 包含 不包含\n"
                "  最大嵌套层级: 3\n"
                "\n"
                "━━━ 循环与延迟 ━━━\n"
                '  {"循环": 3, "动作": [...]}  → 重复 N 次 (最大 10)\n'
                '  {"延迟": 30, "动作": [...]} → 延迟 N 秒 (最大 300)\n'
                "\n"
                "━━━ 规则引用 ━━━\n"
                '  {"调用规则": "other_rule_name"}\n'
                "      → 调用另一个规则 (最大深度 5, 含循环检测)\n"
                "\n"
                "━━━ 事件上下文变量 ━━━\n"
                "  {user_id} {group_id} {nickname} {message} {match} {msg_id} {time}\n"
                "\n"
                "━━━ 安全限制 ━━━\n"
                "  · 最大动作数: 20 条/规则\n"
                "  · 条件嵌套: 最多 3 层\n"
                "  · 循环次数: 最多 10 次\n"
                "  · 延迟时间: 最多 300 秒\n"
                "  · 规则调用: 最多 5 层深度\n"
            )

        # 内置完整参考
        return (
            "📐 规则引擎 DSL 完整参考 (v1.7)\n"
            "\n"
            "━━━ 动作类型 ━━━\n"
            "  纯文本          → 直接发送到群\n"
            "  .命令 参数      → 路由到对应命令\n"
            "  .输出 文本      → 直接发送（不走命令路由）\n"
            '  {"发送群消息": "..."}   → 发送群消息\n'
            '  {"发送私聊": "..."}     → 发送私聊消息\n'
            '  {"触发命令": ".cmd"}   → 触发指定命令\n'
            '  {"设变量": "name", "命令": ".cmd"} → 设置变量\n'
            '  {"如果": {...}, "则": [...], "否则": [...]} → 条件\n'
            '  {"循环": 3, "动作": [...]} → 循环 (最大 10)\n'
            '  {"延迟": 30, "动作": [...]} → 延迟 (最大 300s)\n'
            '  {"调用规则": "name"} → 调用规则 (最大深度 5)\n'
            "\n"
            "━━━ 类型转换 ━━━\n"
            '  数字: {"转为": "数字"} → int()\n'
            '  列表: {"转为": "列表", "分隔符": ","} → split\n'
            '  布尔: {"转为": "布尔"} → "true"/"是"/"1" → True\n'
            "\n"
            "━━━ 条件运算符 ━━━\n"
            "  > < >= <= == != 包含 不包含\n"
            "  嵌套上限: 3 层\n"
            "\n"
            "━━━ 事件上下文变量 ━━━\n"
            "  {user_id} {group_id} {nickname} {message} {match} {msg_id} {time}\n"
            "\n"
            "━━━ 安全限制 ━━━\n"
            "  最大动作数: 20 | 条件嵌套: 3 | 循环: 10 | 延迟: 300s | 调用深度: 5\n"
        )


class HelpModule(Module):
    """帮助模块 v2.2。

    提供 .帮助 命令，支持：
      - 按模块分组列出所有非隐藏命令
      - .帮助 <命令> 显示详细信息
      - .帮助 <命令> --root 显示元数据
      - .帮助 规则 显示规则引擎 DSL 参考
      - 翻页支持（命令列表多页时）

    注册为 help_service 服务供其他模块通过 register_help() 添加命令帮助。
    """

    name = "help"
    mid = 300
    tier = 300
    version = (2, 2, 0)
    required_services = ["command", "message", "config"]

    default_config = {
        "管理员": {
            "管理员QQ": [0]
        }
    }

    def __init__(self, services, event_bus):
        super().__init__(services, event_bus)
        self._help_service = HelpService()
        self._sessions: Dict[int, dict] = {}
        self._session_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def on_init(self):
        """初始化帮助服务并注册为全局服务。"""
        # 延迟注入 command_manager
        self._help_service.set_command_manager(self.command)

        # 注册基础命令
        self._help_service.register_help(".帮助", {
            "description": "显示帮助菜单",
            "usage": ".帮助 [命令|规则] [--root]",
            "examples": [".帮助", ".帮助 .规则", ".帮助 规则", ".帮助 .规则 --root"],
            "module": "help",
            "see_also": [".帮助 规则"],
        })

        # 注册为全局服务
        self._root_services.register("help_service", self._help_service, mid=300,
                                     _caller="modules.system.help")

        # 注册 .帮助 命令
        self.register_command(
            ".帮助", self._cmd_help,
            description="显示帮助信息",
            argument_hint="[命令|规则] [--root]",
        )

        # 注册 /帮助 别名
        self.register_command(
            "/帮助", self._cmd_help,
            description="显示帮助信息（别名）",
            argument_hint="[命令|规则] [--root]",
            hidden=True,
        )

    async def on_start(self):
        """启动后台过期会话清理任务。"""
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def on_stop(self):
        """停止后台清理任务。"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _periodic_cleanup(self):
        """后台清理过期会话。"""
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL)
                now = time.time()
                async with self._session_lock:
                    expired = [
                        uid
                        for uid, session in self._sessions.items()
                        if now - session.get("last_active", 0) > SESSION_TIMEOUT
                    ]
                    for uid in expired:
                        self._sessions.pop(uid, None)
                if expired:
                    _log.debug("后台清理: 移除 %d 个过期帮助会话", len(expired))
            except asyncio.CancelledError:
                break
            except Exception:
                _log.exception("帮助会话后台清理异常")

    @command(".帮助")
    async def _cmd_help(self, ctx):
        """.帮助 [命令|规则] [--root] — 显示帮助信息。"""
        args = ctx.args if ctx.args else []
        is_admin = self._is_admin(ctx.user_id)
        user_uid = self._get_user_uid(ctx.user_id)

        # .帮助 → 命令列表
        if not args:
            await self._show_cmd_list(ctx, is_admin, user_uid)
            return

        # .帮助 规则 → 规则 DSL
        if args[0] == "规则":
            rule_help = self._help_service.format_rule_help()
            await ctx.reply(rule_help)
            return

        # .帮助 <命令> [--root]
        show_root = "--root" in args
        cmd_trigger = args[0]
        detail = self._help_service.format_detail(cmd_trigger, show_root=show_root)
        await ctx.reply(detail)

    async def _show_cmd_list(self, ctx, is_admin: bool, user_uid: int):
        """显示命令列表（支持翻页）。"""
        all_text = self._help_service.format_list(
            caller_uid=user_uid, is_admin=is_admin,
        )
        all_lines = all_text.strip().split("\n")
        # 移除空行
        all_lines = [l for l in all_lines if l.strip()]

        if not all_lines:
            await ctx.reply("当前没有任何可用命令。")
            return

        total_pages = (len(all_lines) - 1) // PAGE_SIZE + 1
        page_lines = all_lines[:PAGE_SIZE]
        msg = self._format_page(page_lines, 1, total_pages)

        if total_pages > 1:
            async with self._session_lock:
                if ctx.user_id in self._sessions:
                    await ctx.reply(
                        "你已有帮助菜单进行中，请先输入 q 退出或等待超时。"
                    )
                    return
                self._sessions[ctx.user_id] = {
                    "lines": all_lines,
                    "current": 1,
                    "total": total_pages,
                    "last_active": time.time(),
                }
            await ctx.reply(msg)
        else:
            await ctx.reply(msg)

    @listen(GroupMessageEvent, priority=-20)
    async def _on_group_msg(self, event):
        """检测翻页指令。"""
        user_id = event.user_id
        text = _CQ_RE.sub('', event.message or '').strip()
        if text not in ("+", "-", "q"):
            return

        send_msg: Optional[str] = None
        async with self._session_lock:
            session = self._sessions.get(user_id)
            if session is None:
                return

            now = time.time()
            last_active = session.get("last_active", 0)

            if now - last_active > SESSION_TIMEOUT:
                self._sessions.pop(user_id, None)
                send_msg = "帮助会话已超时自动关闭。"
            elif text == "q":
                self._sessions.pop(user_id, None)
                send_msg = "帮助菜单已关闭。"
            elif text == "+":
                new_page = min(session["current"] + 1, session["total"])
                if new_page != session["current"]:
                    session["current"] = new_page
                    session["last_active"] = now
                    start = (new_page - 1) * PAGE_SIZE
                    page_lines = list(session["lines"][start: start + PAGE_SIZE])
                    send_msg = self._format_page(page_lines, new_page, session["total"])
                else:
                    session["last_active"] = now
            else:  # "-"
                new_page = max(session["current"] - 1, 1)
                if new_page != session["current"]:
                    session["current"] = new_page
                    session["last_active"] = now
                    start = (new_page - 1) * PAGE_SIZE
                    page_lines = list(session["lines"][start: start + PAGE_SIZE])
                    send_msg = self._format_page(page_lines, new_page, session["total"])
                else:
                    session["last_active"] = now

        if send_msg is not None:
            event.handled = True
            await self.message.send_group(event.group_id, send_msg)

    @staticmethod
    def _format_page(page_lines: List[str], current: int, total: int) -> str:
        """格式化单页帮助文本。"""
        header = f"📋 可用命令列表 ({current}/{total})"
        body = "\n".join(page_lines) if page_lines else "(空)"
        footer = "输入 + 下一页，- 上一页，q 结束"
        return f"{header}\n{body}\n{footer}"

    def _is_admin(self, user_id: int) -> bool:
        try:
            admin_list = self.config.get("管理员.管理员QQ", [])
            uid_int = int(user_id) if not isinstance(user_id, int) else user_id
            return uid_int in [int(q) for q in admin_list]
        except (TypeError, ValueError):
            return False

    def _get_user_uid(self, user_id: int) -> int:
        try:
            return self.services.get("uid_lookup")(user_id)
        except Exception:
            return 400
